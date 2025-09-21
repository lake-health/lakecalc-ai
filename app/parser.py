import re, logging
from typing import Dict, Tuple
from .utils import to_float, check_range, hash_text, llm_extract_missing_fields
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
    dev = detect_device(text)
    patterns = PATTERNS.get(dev, PATTERNS["Generic"])

    result = ExtractResult(file_id=file_id, text_hash=hash_text(text))

    fields = {
        "od": EyeData(source=f"Ref: {dev}"),
        "os": EyeData(source=f"Ref: {dev}"),
    }

    # Split text into OD/OS segments using simple headings or positional heuristics
    # If we can't split, keep full text for parsing
    od_text = ""
    os_text = ""
    # Try to split by 'OD' and 'OS' headings
    # anchor OD/OS headings to line starts to avoid matching Portuguese 'os' words
    od_match = re.search(r"(?m)^\s*OD\b[:\-]?[\s\S]{0,800}?Valores biométricos[\s\S]{0,400}", text, re.I)
    os_match = re.search(r"(?m)^\s*OS\b[:\-]?[\s\S]{0,800}?Valores biométricos[\s\S]{0,400}", text, re.I)
    if od_match:
        od_text = od_match.group(0)
    if os_match:
        os_text = os_match.group(0)
    # Fallback: try splitting by first/second page markers (\nPágina)
    if not od_text and not os_text:
        pages = re.split(r"\nPágina\s+\d+\s+de\s+\d+", text)
        if len(pages) >= 1:
            od_text = pages[0]
        if len(pages) >= 2:
            os_text = pages[1]
    # If still empty, default od_text to full text but leave os_text empty unless a second page exists
    pages = re.split(r"\nPágina\s+\d+\s+de\s+\d+", text)
    if not od_text:
        od_text = text
    # Determine if there's a separate OS page: if we split into multiple pages, use second page
    os_present = False
    if os_match:
        os_present = True
    elif len(pages) >= 2 and pages[1].strip():
        os_text = pages[1]
        os_present = True
    else:
        # leave os_text empty to avoid duplicating OD
        os_text = ""

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

    od_scalars = extract_for_eye(od_text)
    os_scalars = extract_for_eye(os_text) if os_text else {}

    log.debug("Parsed scalars sizes: od=%d os=%d", len(od_scalars), len(os_scalars))
    log.debug("os_present=%s; od_text_len=%d os_text_len=%d", os_present, len(od_text or ""), len(os_text or ""))

    # Heuristic pairing for K1/K2 axes if axis lines are on separate lines with @ notation
    def pair_k_values(scalars: Dict[str, Tuple[str, float | None]], eye_text: str) -> Dict[str, str]:
        out = {}
        # New: robustly extract K1/K2 and their axes from nearby text
        # Pattern matches lines like 'K1: 40,95 D @ 100°' or 'K1: 40,95 D\n@ 100°'
        k_rx = re.compile(r"\b(?P<k>K1|K2)\b\s*[:\-]?\s*(?P<val>\d{1,3}[\.,]\d{1,3})\s*D(?:\s*@\s*(?P<axis>\d{1,3})\s*°)?", re.I)
        # Search sequentially and assign k1/k2 and axes
        found_k = {"K1": None, "K2": None}
        for m in k_rx.finditer(eye_text):
            kname = m.group("k").upper()
            kval = m.group("val")
            kaxis = m.group("axis")
            # If axis missing, look ahead a short distance for '@ N°'
            if not kaxis:
                tail = eye_text[m.end():m.end()+120]
                m2 = re.search(r"@\s*(?P<axis>\d{1,3})\s*°", tail)
                if m2:
                    kaxis = m2.group("axis")
            found_k[kname] = (kval, kaxis)

        # Assign results
        if found_k.get("K1"):
            out["k1"] = found_k["K1"][0]
            if found_k["K1"][1]:
                out["k1_axis"] = found_k["K1"][1]
        if found_k.get("K2"):
            out["k2"] = found_k["K2"][0]
            if found_k["K2"][1]:
                out["k2_axis"] = found_k["K2"][1]

        # Fallback: if no K1/K2 found via dedicated pattern, use scalars
        if "k1" not in out and scalars.get("k1"):
            out["k1"] = scalars.get("k1")[0]
        if "k2" not in out and scalars.get("k2"):
            out["k2"] = scalars.get("k2")[0]

        # Axis generic fallback: find first axis token if none paired
        if "k1_axis" not in out and "k2_axis" not in out:
            axis_matches = re.findall(r"@\s*(\d{1,3})\s*°", eye_text)
            if axis_matches:
                if len(axis_matches) >= 1:
                    out.setdefault("k1_axis", axis_matches[0])
                if len(axis_matches) >= 2:
                    out.setdefault("k2_axis", axis_matches[1])

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
        # axis per K: populate k1_axis/k2_axis from paired heuristics or scalar axis
        k1_ax = pairs.get("k1_axis")
        k2_ax = pairs.get("k2_axis")
        # if a generic 'axis' scalar exists, use it for k1 if neither specific axis found
        generic_axis = scalars.get("axis", ("", None))[0] if scalars.get("axis") else ""
        if not k1_ax and generic_axis:
            k1_ax = generic_axis
        if not k2_ax and generic_axis:
            k2_ax = generic_axis
        fld.k1_axis = k1_ax or ""
        fld.k2_axis = k2_ax or ""
        # Deprecated single-axis kept for backward compat: prefer k1_axis
        fld.axis = fld.k1_axis or fld.k2_axis or ""
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
    if missing["od"] or missing["os"]:
        try:
            # use injected llm_func if provided (for testing), else default util
            if llm_func is None:
                llm_func = llm_extract_missing_fields
            llm_out = llm_func(text, missing)
            log.debug("LLM output: %s", llm_out)
            # merge LLM outputs carefully
            for eye in ("od", "os"):
                # skip merging LLM outputs for OS if OS segment wasn't present
                if eye == "os" and not os_present:
                    log.debug("Skipping LLM merge for OS because OS not present")
                    continue
                eye_obj = getattr(result, eye)
                eye_llm = llm_out.get(eye, {})
                for k, v in eye_llm.items():
                    if k in ("k1", "k2") and isinstance(v, dict):
                        # respect value/axis pairs
                        if v.get("value") and not getattr(eye_obj, k):
                            setattr(eye_obj, k, v.get("value"))
                        if v.get("axis") and not getattr(eye_obj, "axis"):
                            eye_obj.axis = v.get("axis")
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
