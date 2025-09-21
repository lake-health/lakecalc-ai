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
    # Optionally use layout-aware pairing if a layout cache exists and flag enabled
    use_layout = os.getenv("USE_LAYOUT_PAIRING", "false").lower() in ("1", "true", "yes")
    strict_text = settings.strict_text_extraction
    layout_data = None
    if use_layout:
        try:
            fhash = hash_text(text)
            layout_path = Path(settings.uploads_dir) / "ocr" / f"{fhash}.json"
            if layout_path.exists():
                layout_data = json.loads(layout_path.read_text(encoding="utf-8"))
        except Exception:
            layout_data = None
    dev = detect_device(text)
    patterns = PATTERNS.get(dev, PATTERNS["Generic"])

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
            # Single page: could be OD or OS only, use full text for OS, leave OD empty
            od_text = ""
            os_text = text
        elif len(pages) >= 2:
            od_text = pages[0]
            os_text = pages[1]
    # If still empty, default od_text to empty and os_text to full text
    if not od_text and os_text:
        od_text = ""
    if not os_text and od_text:
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
        out = {}
        # Split into lines for robust lookahead/backward matching
        lines = eye_text.splitlines()
        k_results = {"K1": {"val": None, "axis": None}, "K2": {"val": None, "axis": None}}
        for i, line in enumerate(lines):
            m = re.search(r"\b(K1|K2)\b\s*[:\-]?\s*(\d{1,3}[\.,]\d{1,3})\s*D", line, re.I)
            if m:
                kname = m.group(1).upper()
                kval = m.group(2)
                # Try to find axis on same line
                axis_m = re.search(r"@\s*(\d{1,3})\s*°", line)
                kaxis = axis_m.group(1) if axis_m else None
                # If not found, look at the next non-empty line for axis, but only if it is just an axis (e.g., '@ 100°')
                if not kaxis:
                    for j in range(1, 3):
                        if i + j < len(lines):
                            next_line = lines[i + j].strip()
                            if not next_line:
                                continue
                            axis_only = re.fullmatch(r"@\s*(\d{1,3})\s*°", next_line)
                            if axis_only:
                                kaxis = axis_only.group(1)
                                break
                            # If next line contains any known measurement or label, break (do not assign axis)
                            if re.search(r"(CW-Chord|AL|WTW|CCT|ACD|LT|AK|SE|SD|TK|ATK|P|Ix|ly|Fixação|Comentário|mm|μm|D|VA|Status de olho|Resultado|Paciente|Médico|Operador|Data|Versão|Página)", next_line, re.I):
                                break
                k_results[kname]["val"] = kval
                # Only assign axis if found in correct context, else leave blank
                k_results[kname]["axis"] = kaxis if kaxis else ""
        # Assign results
        if k_results["K1"]["val"]:
            out["k1"] = k_results["K1"]["val"]
            if k_results["K1"]["axis"]:
                out["k1_axis"] = k_results["K1"]["axis"]
        if k_results["K2"]["val"]:
            out["k2"] = k_results["K2"]["val"]
            if k_results["K2"]["axis"]:
                out["k2_axis"] = k_results["K2"]["axis"]
        # Fallback: if no K1/K2 found via dedicated pattern, use scalars
        if "k1" not in out and scalars.get("k1"):
            out["k1"] = scalars.get("k1")[0]
        if "k2" not in out and scalars.get("k2"):
            out["k2"] = scalars.get("k2")[0]
        # Axis generic fallback: prefer axes that are near K1/K2 occurrences
        # If strict_text extraction is enabled, skip generic axis fallback entirely
        if not strict_text:
            # 1) Try to find an axis token within ~180 chars after each K1/K2 match
            for key_label in (("k1", "K1"), ("k2", "K2")):
                kkey, klabel = key_label
                if f"{kkey}_axis" in out:
                    continue
                m = re.search(rf"\b{klabel}\b\s*[:\-]?\s*\d{{1,3}}[\.,]\d{{1,3}}\s*D", eye_text, re.I)
                if m:
                    tail = eye_text[m.end():m.end()+180]
                    # iterate possible axis matches in the tail and choose the first one
                    # whose line context does not look like another measurement (e.g., CW-Chord, TK, AK)
                    found_axis = None
                    for m2 in re.finditer(r"@\s*(\d{1,3})\s*°", tail):
                        # compute absolute position of axis in eye_text
                        abs_pos = m.end() + m2.start()
                        line_start = eye_text.rfind('\n', 0, abs_pos) + 1
                        line_end = eye_text.find('\n', abs_pos)
                        line = eye_text[line_start: line_end if line_end != -1 else None]
                        # skip if the axis line includes tokens that indicate non-keratometry measurements
                        if re.search(r"\b(TK1|TK2|TK|ATK|AK|CW[- ]?Chord|Chord|mm|μm)\b", line, re.I):
                            continue
                        found_axis = m2.group(1)
                        break
                    if found_axis:
                        out[f"{kkey}_axis"] = found_axis
        # end of generic axis fallback
        # 2) If still missing, try layout-based pairing (if available) before falling back to raw axis tokens
        if ("k1_axis" not in out or "k2_axis" not in out) and layout_data and not strict_text:
            try:
                # build a flat list of words with approximate centers and text
                words = []
                for p in layout_data.get("pages", []):
                    for b in p.get("blocks", []):
                        for par in b.get("paragraphs", []):
                            for w in par.get("words", []):
                                txt = w.get("text", "")
                                bbox = w.get("bbox", [])
                                if not bbox:
                                    continue
                                # compute center
                                xs = [v.get("x", 0) for v in bbox]
                                ys = [v.get("y", 0) for v in bbox]
                                cx = sum(xs) / len(xs)
                                cy = sum(ys) / len(ys)
                                words.append({"text": txt, "cx": cx, "cy": cy})
                # find k1/k2 word positions (matching tokens like 'K1' or numeric K values nearby)
                k_positions = {"K1": [], "K2": []}
                for w in words:
                    if re.fullmatch(r"K1", w["text"], re.I):
                        k_positions["K1"].append(w)
                    if re.fullmatch(r"K2", w["text"], re.I):
                        k_positions["K2"].append(w)
                # Try to locate axis tokens like '@' followed by number in neighboring words
                axis_words = []
                for i, w in enumerate(words):
                    # axis may be represented as '@' token followed by '100' or '@100' or '@' in same word
                    if re.search(r"@|°", w["text"]):
                        # try to extract number from this word or next word
                        mnum = re.search(r"(\d{1,3})", w["text"])
                        candidate = None
                        if mnum:
                            candidate = {"cx": w["cx"], "cy": w["cy"], "val": mnum.group(1)}
                        else:
                            # look ahead for a numeric word
                            if i + 1 < len(words) and re.fullmatch(r"\d{1,3}", words[i+1]["text"]):
                                candidate = {"cx": words[i+1]["cx"], "cy": words[i+1]["cy"], "val": words[i+1]["text"]}
                        if candidate:
                            # filter out candidates that are spatially close to words indicating CW-Chord or mm
                            skip = False
                            for other in words:
                                if re.search(r"\b(CW[- ]?Chord|Chord|mm)\b", other["text"], re.I):
                                    dy = abs(other["cy"] - candidate["cy"])
                                    dx = abs(other["cx"] - candidate["cx"])
                                    if dy < 20 and dx < 200:
                                        skip = True
                                        break
                            if not skip:
                                axis_words.append(candidate)
                # For each K, find nearest axis by vertical distance and reasonable horizontal proximity
                for klabel in ("K1", "K2"):
                    if f"{klabel.lower()}_axis" in out:
                        continue
                    candidates = k_positions.get(klabel, [])
                    if not candidates:
                        continue
                    # pick the first k token position as anchor
                    anchor = candidates[0]
                    best = None
                    best_dist = 1e12
                    for a in axis_words:
                        dy = abs(a["cy"] - anchor["cy"])
                        dx = abs(a["cx"] - anchor["cx"])
                        # penalize very distant vertical distances
                        score = dy + (dx * 0.2)
                        if score < best_dist and dy < 200:  # 200px vertical threshold empiric
                            best_dist = score
                            best = a
                    if best:
                        out[f"{klabel.lower()}_axis"] = best["val"]
            except Exception:
                # fallback to raw axis tokens below
                pass

        # fallback to any axis tokens but FILTER OUT axes that appear on lines with 'mm' or 'CW-Chord' (likely chord/measurement axes)
        if "k1_axis" not in out or "k2_axis" not in out:
            axis_list = []
            for m in re.finditer(r"@\s*(\d{1,3})\s*°", eye_text):
                s = m.start()
                # extract the full line containing this axis
                line_start = eye_text.rfind('\n', 0, s) + 1
                line_end = eye_text.find('\n', s)
                line = eye_text[line_start: line_end if line_end != -1 else None]
                # skip axes that are part of measurements in mm or explicitly CW-Chord
                if re.search(r"\bmm\b|CW[- ]?Chord|Chord\b", line, re.I):
                    continue
                axis_list.append(m.group(1))
            if "k1_axis" not in out and len(axis_list) >= 1:
                out["k1_axis"] = axis_list[0]
            if "k2_axis" not in out and len(axis_list) >= 2:
                out["k2_axis"] = axis_list[1]
        return out

    od_pairs = pair_k_values(od_scalars, od_text)
    os_pairs = pair_k_values(os_scalars, os_text)

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
        # Do NOT use any standalone/generic 'axis' scalar fallback to avoid leakage
        k1_ax = pairs.get("k1_axis") or ""
        k2_ax = pairs.get("k2_axis") or ""
        fld.k1_axis = k1_ax
        fld.k2_axis = k2_ax
        # Deprecated single-axis kept for backward compat: prefer k1_axis only if present
        fld.axis = fld.k1_axis if fld.k1_axis else (fld.k2_axis if fld.k2_axis else "")
        # ak
        ak_raw = scalars.get("ak", ("", None))[0] if scalars.get("ak") else ""
        fld.ak = ak_raw
        # confidences for keratometry
        for key in ("k1", "k2", "ak", "k1_axis", "k2_axis"):
            result.confidence[f"{eye}.{key}"] = 0.8 if getattr(fld, key) else 0.2

    result.od = fields["od"]
    result.os = fields["os"]

    # previously we appended debug entries to result.flags for debugging
    # switch to logging so flags remain clean for production
    log.debug("debug: os_present=%s od_scalars=%d os_scalars=%d od_match=%s os_match=%s", os_present, len(od_scalars), len(os_scalars), 'yes' if od_match else 'no', 'yes' if os_match else 'no')

    # If important fields like axes are missing, call LLM fallback to try to fill gaps
    missing = {"od": [], "os": []}
    for eye in ("od", "os"):
        if not getattr(getattr(result, eye), "axis"):
            missing[eye].append("axis")
        if not getattr(getattr(result, eye), "axial_length"):
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
                        # only set per-eye axis fields if specific k1/k2 axis keys are provided
                        if v.get("axis"):
                            # prefer assigning to k1_axis/k2_axis, not the deprecated single 'axis'
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
    return result
