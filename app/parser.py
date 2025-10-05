import re, logging, json, os
from typing import Dict, Tuple, List
from pathlib import Path
from .utils import to_float, check_range, hash_text, llm_extract_missing_fields
from .config import settings
from .models.api import ExtractResult, EyeData

log = logging.getLogger(__name__)

# Common helpers
NUM = r"(?P<val>-?\d{1,3}[\.,]?\d{0,3})"
MM = r"(?:\s*mm)"
UM = r"(?:\s*(?:µm|um))"
DIOP = r"(?:\s*D)"
DEG = r"(?:\s*°)"


def sanitize_axis(raw_candidate: str) -> str | None:
    """Sanitize a raw numeric axis candidate: take rightmost 1-3 digits and validate 0-180."""
    if not raw_candidate:
        return None
    groups = re.findall(r"(\d{1,3})", raw_candidate)
    if not groups:
        return None
    candidate = groups[-1]
    try:
        iv = int(candidate)
    except Exception:
        return None
    if 0 <= iv <= 180:
        return str(iv)
    return None

# Device-specific patterns (extend as needed)
PATTERNS = {
    "IOLMaster700": {
        "axial_length": re.compile(r"Axial\s*Length\s*:?\s*" + NUM + MM, re.I),
        "acd": re.compile(r"ACD\s*:?\s*" + NUM + MM, re.I),
        "lt": re.compile(r"Lens\s*Thickness\s*:?\s*" + NUM + MM, re.I),
        "wtw": re.compile(r"WTW\s*:?\s*" + NUM + MM, re.I),
        "k1": re.compile(r"K1\s*:?\s*" + NUM + DIOP, re.I),
        "k2": re.compile(r"K2\s*:?\s*" + NUM + DIOP, re.I),
        "ak": re.compile(r"Astig(?:matism)?\s*:?\s*" + NUM + DIOP, re.I),
        "axis": re.compile(r"Axis\s*:?\s*(?P<val>\d{1,3})" + DEG + "?", re.I),
    },
    "Pentacam": {
        "cct": re.compile(r"CCT\s*:?\s*" + NUM + UM, re.I),
        "k1": re.compile(r"K1\s*\(Front\)?:?\s*" + NUM + DIOP, re.I),
        "k2": re.compile(r"K2\s*\(Front\)?:?\s*" + NUM + DIOP, re.I),
        "ak": re.compile(r"Astig(?:matism)?\s*\(Front\)?:?\s*" + NUM + DIOP, re.I),
        "axis": re.compile(r"Axis\s*\(Front\)?:?\s*(?P<val>\d{1,3})" + DEG + "?", re.I),
    },
    "Generic": {
        "axial_length": re.compile(r"Axial\s*Length\s*:?\s*" + NUM + MM, re.I),
        "acd": re.compile(r"ACD\s*:?\s*" + NUM + MM, re.I),
        "lt": re.compile(r"Lens\s*Thickness\s*:?\s*" + NUM + MM, re.I),
        "wtw": re.compile(r"WTW\s*:?\s*" + NUM + MM, re.I),
        "cct": re.compile(r"CCT\s*:?\s*" + NUM + UM, re.I),
        "k1": re.compile(r"K1\s*:?\s*" + NUM + DIOP, re.I),
        "k2": re.compile(r"K2\s*:?\s*" + NUM + DIOP, re.I),
        "ak": re.compile(r"(Astig(?:matism)?|AK|DeltaK)\s*:?\s*" + NUM + DIOP, re.I),
        "axis": re.compile(r"Axis\s*:?\s*(?P<val>\d{1,3})" + DEG + "?", re.I),
    }
}

DEVICE_ORDER = ["IOLMaster700", "Pentacam", "Generic"]


def _grab(rx: re.Pattern, text: str) -> tuple[str, float | None]:
    m = rx.search(text)
    if not m:
        return "", None
    raw = m.group("val")
    return raw, to_float(raw)


def detect_device(text: str) -> str:
    if re.search(r"IOL\s*Master\s*700", text, re.I):
        return "IOLMaster700"
    if re.search(r"Pentacam", text, re.I):
        return "Pentacam"
    return "Generic"


def parse_text(file_id: str, text: str, llm_func=None) -> ExtractResult:
    # Optionally use layout-aware pairing if flag enabled and layout was provided
    use_layout = os.getenv("USE_LAYOUT_PAIRING", "false").lower() in ("1", "true", "yes")
    strict_text = settings.strict_text_extraction
    layout_data = None  # Ensure layout_data is initialized

    dev = detect_device(text)
    patterns = PATTERNS.get(dev, PATTERNS["Generic"])

    # Device-specific normalization for messy text exports
    def normalize_for_device(dev_name: str, raw_text: str) -> str:
        t = raw_text
        if dev_name == "IOLMaster700":
            # common issues in device export: tokens glued like '43,80 D88875°' or 'K1: 41,45 D @K2:'
            # 1) ensure degree symbol separated: '75°' or '@ 75°' -> keep degree but add space before '@' and '°'
            t = re.sub(r"\s*@\s*", " @ ", t)
            t = re.sub(r"(\d)°", r"\1 °", t)
            # 2) ensure 'D@' and 'D@' variants are spaced: 'D@' -> 'D @'
            t = re.sub(r"D\s*@", "D @", t)
            t = re.sub(r"D@", "D @", t)
            # 3) ensure K1/K2/AK tokens have a separating space if collapsed (do NOT force newlines)
            t = re.sub(r"\b(K1:|K2:|AK:|K1|K2|AK)\s*", lambda m: m.group(1) + " ", t)
            # 4) remove repeated digit garbage before degrees (e.g., '88875 °' -> '75 °')
            t = re.sub(r"(\d{3,})(\d{1,3})\s*°", lambda m: m.group(2) + " °", t)
            # 4b) if an axis appears alone on its own line (e.g., '\n@ 100°\n'), merge it onto the previous line
            t = re.sub(r"\n\s*(@\s*\d{1,3}\s*°)\s*\n", lambda m: " " + m.group(1) + "\n", t)
            # 5) collapse multiple spaces to single
            t = re.sub(r"[ \t]+", " ", t)
        return t

    text = normalize_for_device(dev, text)

    result = ExtractResult(file_id=file_id, text_hash=hash_text(text))

    fields = {
        "od": EyeData(source=f"Ref: {dev}"),
        "os": EyeData(source=f"Ref: {dev}"),
    }

    # Split text into OD/OS segments using headings or page breaks, robust to OS-only or OD-only files
    od_text = ""
    os_text = ""
    # Try to split by 'OD' and 'OS' headings, but also search for OS block anywhere in text
    od_match = re.search(r"(?m)^\s*OD\b[:\-]?[\s\S]{0,800}?Valores biométricos[\s\S]{0,400}", text, re.I)
    os_match = re.search(r"(?m)^\s*OS\b[:\-]?[\s\S]{0,800}?Valores biométricos[\s\S]{0,400}", text, re.I)
    if od_match:
        od_text = od_match.group(0)
    # For OS, if not found at top level, search for any block starting with 'OS' and containing 'Valores biométricos' or 'AL:'
    if os_match:
        os_text = os_match.group(0)
    else:
        os_block = re.search(r"OS[\s\S]{0,2000}?(Valores biométricos|AL:)\s*[:\-]?[\s\S]{0,400}", text, re.I)
        if os_block:
            os_text = os_block.group(0)
    # Fallback: try splitting by first/second page markers (\nPágina)
    pages = re.split(r"\nPágina\s+\d+\s+de\s+\d+", text)
    if not od_text and not os_text:
        if len(pages) == 1:
            # Single page: ambiguous. Prefer to treat it as OD if the text contains 'OD' markers,
            # otherwise as OS. This avoids blindly copying OD values into OS later.
            if re.search(r"\bOD\b", text, re.I):
                od_text = text
                os_text = ""
            else:
                od_text = ""
                os_text = text
        elif len(pages) >= 2:
            od_text = pages[0]
            os_text = pages[1]
    # If still empty, default od_text to empty and os_text to full text
    # If one side has explicit detections, do not mirror the same full-text into the other side.
    if not od_text and os_text:
        od_text = ""
    if not os_text and od_text:
        # keep os_text empty to avoid leaking OD values into OS
        os_text = ""
    if not od_text and not os_text:
        od_text = ""
        os_text = text
    # Determine if there's a separate OS page: if we split into multiple pages, use second page
    os_present = False
    if os_match:
        os_present = True
    elif len(pages) >= 2 and pages[1].strip():
        os_text = pages[1]
        os_present = True
    elif os_text and not od_text:
        # OS-only file: treat as OS present
        os_present = True
    # Determine whether OD segment was detected (if od_text is non-empty)
    od_present = bool(od_text and od_text.strip())
    # If os_text is identical to od_text, treat OS as not present (avoid duplication)
    if os_text and od_text and os_text.strip() == od_text.strip():
        os_text = ""
        os_present = False
    # log detected presence
    if not os_present:
        log.debug("OS segment not detected; will not populate OS fields or merge LLM results")

    def extract_for_eye(eye_text: str) -> Dict[str, Tuple[str, float | None]]:
        scalars: Dict[str, Tuple[str, float | None]] = {}
        for key, rx in patterns.items():
            raw, val = _grab(rx, eye_text)
            if raw:
                scalars[key] = (raw, val)
        return scalars

    od_scalars = extract_for_eye(od_text) if od_text else {}
    os_scalars = extract_for_eye(os_text) if os_text else {}

    log.debug("Parsed scalars sizes: od=%d os=%d", len(od_scalars), len(os_scalars))
    log.debug("os_present=%s; od_text_len=%d os_text_len=%d", os_present, len(od_text or ""), len(os_text or ""))

    # Heuristic pairing for K1/K2 axes if axis lines are on separate lines with @ notation
    def pair_k_values(scalars: Dict[str, Tuple[str, float | None]], eye_text: str) -> Dict[str, str]:
        out: Dict[str, str] = {}
        lines = eye_text.splitlines()
        k_results = {"K1": {"val": None, "axis": None}, "K2": {"val": None, "axis": None}}

        def sanitize_axis(raw_candidate: str) -> str | None:
            if not raw_candidate:
                return None
            groups = re.findall(r"(\d{1,3})", raw_candidate)
            if not groups:
                return None
            candidate = groups[-1]
            try:
                iv = int(candidate)
            except Exception:
                return None
            if 0 <= iv <= 180:
                return str(iv)
            return None

        # Primary pass: scan lines for explicit K1/K2 numeric values and try to locate an axis nearby
        for i, line in enumerate(lines):
            m = re.search(r"\b(K1|K2)\b\s*[:\-]?\s*(\d{1,3}[\.,]\d{1,3})\s*D", line, re.I)
            if not m:
                continue
            kname = m.group(1).upper()
            kval = m.group(2)

            # 1) same-line '@ N°'
            axis_m = re.search(r"@\s*(\d{1,3})\s*°", line)
            kaxis = axis_m.group(1) if axis_m else None

            # 2) trailing-degree after the numeric match
            if not kaxis:
                kval_pos = m.end()
                tail = line[kval_pos:]
                m2 = re.search(r"@?\s*(\d{1,3})\s*°", tail)
                if m2:
                    kaxis = sanitize_axis(m2.group(1))
                else:
                    m3 = list(re.finditer(r"(\d{1,3})\s*°", line))
                    if m3:
                        kaxis = sanitize_axis(m3[-1].group(1))

            # 3) forward small-window axis-only lines (e.g., '@ 100°')
            if not kaxis:
                window = 6 if dev == "IOLMaster700" else 3
                for j in range(1, window):
                    if i + j >= len(lines):
                        break
                    next_line = lines[i + j].strip()
                    if not next_line:
                        continue
                    axis_only = re.fullmatch(r"@?\s*(\d{1,3})\s*°", next_line)
                    if axis_only:
                        kaxis = sanitize_axis(axis_only.group(1))
                        if kaxis:
                            break
                        break
                    if re.search(r"(CW[- ]?Chord|AL|WTW|CCT|ACD|LT|AK|SE|SD|TK|TSE|ATK|P|Ix|ly|Fixação|Comentário|mm|μm|D|VA|Status de olho|Resultado|Paciente|Médico|Operador|Data|Versão|Página)", next_line, re.I):
                        break
                    if re.fullmatch(r"\s*\d{1,4}\s*", next_line):
                        break

            # 4) backward small-window axis-only lines
            if not kaxis:
                window = 6 if dev == "IOLMaster700" else 3
                for j in range(1, window):
                    if i - j < 0:
                        break
                    prev_line = lines[i - j].strip()
                    if not prev_line:
                        continue
                    axis_only = re.fullmatch(r"@?\s*(\d{1,3})\s*°", prev_line)
                    if axis_only:
                        if re.search(r"(CW[- ]?Chord|AL|WTW|CCT|ACD|LT|AK|SE|SD|TK|TSE|ATK|P|Ix|ly|Fixação|Comentário|mm|μm|D|VA|Status de olho|Resultado|Paciente|Médico|Operador|Data|Versão|Página)", prev_line, re.I):
                            break
                        kaxis = axis_only.group(1)
                        break

            k_results[kname]["val"] = kval
            k_results[kname]["axis"] = kaxis if kaxis else ""

        # Assign K values and any axes found
        if k_results["K1"]["val"]:
            out["k1"] = k_results["K1"]["val"]
            if k_results["K1"]["axis"]:
                out["k1_axis"] = k_results["K1"]["axis"]
        if k_results["K2"]["val"]:
            out["k2"] = k_results["K2"]["val"]
            if k_results["K2"]["axis"]:
                out["k2_axis"] = k_results["K2"]["axis"]

        # scalar fallbacks
        if "k1" not in out and scalars.get("k1"):
            out["k1"] = scalars.get("k1")[0]
        if "k2" not in out and scalars.get("k2"):
            out["k2"] = scalars.get("k2")[0]

        # Layout-based nearest-axis matching (unique assignment)
        if layout_data and not strict_text:
            try:
                words = []
                for p in layout_data.get("pages", []):
                    for b in p.get("blocks", []):
                        for par in b.get("paragraphs", []):
                            for w in par.get("words", []):
                                txt = w.get("text", "").strip()
                                bbox = w.get("bbox", [])
                                if not txt or not bbox:
                                    continue
                                xs = [v.get("x", 0) for v in bbox]
                                ys = [v.get("y", 0) for v in bbox]
                                cx = sum(xs) / len(xs)
                                cy = sum(ys) / len(ys)
                                words.append({"text": txt, "cx": cx, "cy": cy})

                axis_cands = []
                for i_w, w in enumerate(words):
                    if "°" in w["text"] or "@" in w["text"] or re.fullmatch(r"\d{1,3}", w["text"]):
                        mnum = re.search(r"(\d{1,3})", w["text"])
                        if mnum:
                            val = sanitize_axis(mnum.group(1))
                            if val:
                                axis_cands.append({"idx": i_w, "cx": w["cx"], "cy": w["cy"], "val": val, "used": False})

                k_anchors = {"K1": [], "K2": []}
                for i_w, w in enumerate(words):
                    if re.fullmatch(r"K1", w["text"], re.I):
                        k_anchors["K1"].append({"cx": w["cx"], "cy": w["cy"], "idx": i_w})
                    if re.fullmatch(r"K2", w["text"], re.I):
                        k_anchors["K2"].append({"cx": w["cx"], "cy": w["cy"], "idx": i_w})
                    if re.match(r"^\d{1,2}[,\.]\d{1,2}$", w["text"]) or re.match(r"^\d{1,2}[,\.]\d{1,2}D$", w["text"], re.I):
                        left = words[i_w - 1]["text"] if i_w - 1 >= 0 else ""
                        right = words[i_w + 1]["text"] if i_w + 1 < len(words) else ""
                        if re.search(r"\bD\b", left + right, re.I) or re.fullmatch(r"(K1|K2)", left, re.I) or re.fullmatch(r"(K1|K2)", right, re.I):
                            k_anchors["K1"].append({"cx": w["cx"], "cy": w["cy"], "idx": i_w})
                            k_anchors["K2"].append({"cx": w["cx"], "cy": w["cy"], "idx": i_w})

                def pick_anchor(klist, prefer_left=True):
                    if not klist:
                        return None
                    if len(klist) == 1:
                        return klist[0]
                    sorted_by_x = sorted(klist, key=lambda a: a["cx"])
                    return sorted_by_x[0] if prefer_left else sorted_by_x[-1]

                anchor_k1 = pick_anchor(k_anchors["K1"], prefer_left=True)
                anchor_k2 = pick_anchor(k_anchors["K2"], prefer_left=False)

                import math
                def dist(a, b):
                    return math.hypot(a["cx"] - b["cx"], a["cy"] - b["cy"])

                if anchor_k1 and "k1_axis" not in out:
                    best = None
                    best_d = None
                    for a in axis_cands:
                        if a["used"]:
                            continue
                        d = dist(anchor_k1, a)
                        if best is None or d < best_d:
                            best = a
                            best_d = d
                    if best:
                        out["k1_axis"] = best["val"]
                        best["used"] = True

                if anchor_k2 and "k2_axis" not in out:
                    best = None
                    best_d = None
                    for a in axis_cands:
                        if a["used"]:
                            continue
                        d = dist(anchor_k2, a)
                        if best is None or d < best_d:
                            best = a
                            best_d = d
                    if best:
                        out["k2_axis"] = best["val"]
                        best["used"] = True

            except Exception:
                # preserve prior fallbacks if layout matching errors
                pass

        # Generic regex fallback ensuring unique assignment
        if ("k1_axis" not in out or "k2_axis" not in out):
            axis_occurrences: List[Tuple[int, str]] = []
            for m in re.finditer(r"@\s*(\d{1,3})\s*°", eye_text):
                s = m.start()
                line_start = eye_text.rfind('\n', 0, s) + 1
                line_end = eye_text.find('\n', s)
                line = eye_text[line_start: line_end if line_end != -1 else None]
                if re.search(r"\bmm\b|CW[- ]?Chord|Chord\b|\bTSE\b|\bSD\b|TK\d*", line, re.I):
                    continue
                if re.fullmatch(r"\s*\d{1,4}\s*", line):
                    continue
                clean = sanitize_axis(m.group(1))
                if clean:
                    axis_occurrences.append((s, clean))

            anchors = {}
            for klabel in ("K1", "K2"):
                m = re.search(rf"\b{klabel}\b\s*[:\-]?\s*\d{{1,3}}[\.,]\d{{1,3}}\s*D", eye_text, re.I)
                if m:
                    anchors[klabel.lower()] = m.start()

            used_positions = set()
            for kkey, apos in anchors.items():
                if f"{kkey}_axis" in out:
                    continue
                best = None
                best_dist = None
                for idx, (pos, val) in enumerate(axis_occurrences):
                    if idx in used_positions:
                        continue
                    distp = abs(pos - apos)
                    if best is None or distp < best_dist:
                        best = (idx, val)
                        best_dist = distp
                if best:
                    out[f"{kkey}_axis"] = best[1]
                    used_positions.add(best[0])

            if "k1_axis" not in out and len(axis_occurrences) >= 1:
                out["k1_axis"] = axis_occurrences[0][1]
            if "k2_axis" not in out and len(axis_occurrences) >= 2:
                out["k2_axis"] = axis_occurrences[1][1]

    # Compute paired-axis heuristics for each eye
    od_pairs = pair_k_values(od_scalars, od_text) if od_scalars else {}
    os_pairs = pair_k_values(os_scalars, os_text) if os_scalars else {}

    # Populate fields with extracted scalars and paired axes
    for eye, scalars, pairs in (("od", od_scalars, od_pairs), ("os", os_scalars, os_pairs)):
        fld = fields[eye]
        # If no scalars for this eye and the eye segment wasn't present, skip populating to avoid duplication
        if eye == "os" and not os_present:
            # leave OS empty and low confidence
            for key in ("axial_length", "acd", "lt", "cct", "wtw", "k1", "k2", "k1_axis", "k2_axis", "ak", "axis"):
                result.confidence[f"{eye}.{key}"] = 0.0
            continue
        for key in ("axial_length", "acd", "lt", "cct", "wtw"):
            raw, val = scalars.get(key, ("", None))
            setattr(fld, key, raw)
            ok, msg = check_range(key, val)
            result.confidence[f"{eye}.{key}"] = 0.9 if ok else 0.3
            if not ok and msg:
                result.flags.append(f"{eye}: {msg}")

        # K values: keep raw value, axis from paired heuristics if available
        k1_raw, _ = scalars.get("k1", ("", None))
        k2_raw, _ = scalars.get("k2", ("", None))
        setattr(fld, "k1", k1_raw)
        setattr(fld, "k2", k2_raw)
        # axis per K: populate k1_axis/k2_axis from paired heuristics only
        k1_ax = pairs.get("k1_axis") or ""
        k2_ax = pairs.get("k2_axis") or ""
        fld.k1_axis = k1_ax
        fld.k2_axis = k2_ax

        # ak
        ak_raw = scalars.get("ak", ("", None))[0] if scalars.get("ak") else ""
        fld.ak = ak_raw

        # confidences for keratometry
        for key in ("k1", "k2", "ak", "k1_axis", "k2_axis"):
            result.confidence[f"{eye}.{key}"] = 0.8 if getattr(fld, key) else 0.2

    result.od = fields["od"]
    result.os = fields["os"]

    log.debug("debug: os_present=%s od_scalars=%d os_scalars=%d od_match=%s os_match=%s",
              os_present, len(od_scalars), len(os_scalars), 'yes' if od_match else 'no', 'yes' if os_match else 'no')

    # If important fields like axes are missing, call LLM fallback to try to fill gaps
    missing = {"od": [], "os": []}
    for eye in ("od", "os"):
        eye_obj = getattr(result, eye)
        # consider axis missing if neither per-K axis is present
        if not (getattr(eye_obj, "k1_axis", None) or getattr(eye_obj, "k2_axis", None)):
            missing[eye].append("axis")
        if not getattr(eye_obj, "axial_length"):
            missing[eye].append("axial_length")

    # If an eye segment wasn't present in the text, don't request LLM output for it
    if not od_present:
        missing["od"] = []
    if not os_present:
        missing["os"] = []

    if missing["od"] or missing["os"]:
        try:
            # use injected llm_func if provided (for testing), else default util
            if llm_func is None:
                llm_func = llm_extract_missing_fields
            llm_out = llm_func(text, missing)
            if llm_out is None:
                llm_out = {}
            log.debug("LLM output: %s", llm_out)
            # merge LLM outputs carefully
            for eye in ("od", "os"):
                # skip merging LLM outputs for an eye if its segment wasn't present
                if eye == "os" and not os_present:
                    log.debug("Skipping LLM merge for OS because OS not present")
                    continue
                if eye == "od" and not od_present:
                    log.debug("Skipping LLM merge for OD because OD not present")
                    continue
                eye_obj = getattr(result, eye)
                eye_llm = llm_out.get(eye, {})
                for k, v in eye_llm.items():
                    if k in ("k1", "k2") and isinstance(v, dict):
                        # respect value/axis pairs
                        if v.get("value") and not getattr(eye_obj, k):
                            setattr(eye_obj, k, v.get("value"))
                        if v.get("axis"):
                            if k == "k1" and not getattr(eye_obj, "k1_axis"):
                                eye_obj.k1_axis = v.get("axis")
                            if k == "k2" and not getattr(eye_obj, "k2_axis"):
                                eye_obj.k2_axis = v.get("axis")
                    else:
                        if v and not getattr(eye_obj, k):
                            setattr(eye_obj, k, v)
        except Exception as e:
            log.exception("LLM fallback failed: %s", e)

    result.od = fields["od"]
    result.os = fields["os"]

    if not od_scalars and not os_scalars:
        result.notes = "Parsing found no matches; consider LLM fallback"

    # Final deterministic proximity assignment: if K values exist but per-K axes are empty,
    # try a last-pass proximity match within the same eye_text using sanitized '@ N°' tokens.
    def final_proximity_assign(eye_name: str, eye_text: str):
        eye_obj = getattr(result, eye_name)
        # only apply when K values exist but axes missing
        if not (getattr(eye_obj, "k1") or getattr(eye_obj, "k2")):
            return
        need_k1 = bool(getattr(eye_obj, "k1")) and not getattr(eye_obj, "k1_axis")
        need_k2 = bool(getattr(eye_obj, "k2")) and not getattr(eye_obj, "k2_axis")
        if not (need_k1 or need_k2):
            return
        # collect sanitized axis occurrences with positions
        occ: List[Tuple[int, str]] = []
        for m in re.finditer(r"@\s*(\d{1,3})\s*°", eye_text):
            clean = sanitize_axis(m.group(1))
            if clean:
                occ.append((m.start(), clean))
        if not occ:
            return
        # anchors
        anchors: Dict[str, int] = {}
        if getattr(eye_obj, "k1"):
            m1 = re.search(r"\bK1\b\s*[:\-]?\s*\d{1,3}[\.,]\d{1,3}\s*D", eye_text, re.I)
            if m1:
                anchors["k1"] = m1.start()
        if getattr(eye_obj, "k2"):
            m2 = re.search(r"\bK2\b\s*[:\-]?\s*\d{1,3}[\.,]\d{1,3}\s*D", eye_text, re.I)
            if m2:
                anchors["k2"] = m2.start()

        for kkey, apos in anchors.items():
            best = None
            best_dist = None
            for pos, val in occ:
                d = abs(pos - apos)
                if best is None or d < best_dist:
                    best = val
                    best_dist = d
            if best:
                setattr(eye_obj, f"{kkey}_axis", best)

    # apply per-eye final proximity assignment
    try:
        final_proximity_assign("od", od_text)
        final_proximity_assign("os", os_text)
    except Exception:
        log.exception("final_proximity_assign failed")

    return result
