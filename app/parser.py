import re, logging
from typing import Dict, Tuple
from .utils import to_float, check_range, hash_text
from .models import ExtractResult, EyeData

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


def parse_text(file_id: str, text: str) -> ExtractResult:
    dev = detect_device(text)
    patterns = PATTERNS.get(dev, PATTERNS["Generic"])

    result = ExtractResult(file_id=file_id, text_hash=hash_text(text))

    fields = {
        "od": EyeData(source=f"Ref: {dev}"),
        "os": EyeData(source=f"Ref: {dev}"),
    }

    # For now, we apply same pattern set to whole text (later: split OD/OS by page/labels)
    # Grab global values
    scalars: Dict[str, Tuple[str, float | None]] = {}
    for key, rx in patterns.items():
        raw, val = _grab(rx, text)
        if raw:
            scalars[key] = (raw, val)

    # Assign to both eyes if present (until we add robust OD/OS segmentation)
    for eye in ("od", "os"):
        for key in ("axial_length", "acd", "lt", "cct", "wtw", "k1", "k2", "ak", "axis"):
            raw, val = scalars.get(key, ("", None))
            setattr(fields[eye], key, raw)
            if key in ("axial_length", "acd", "lt", "cct", "wtw"):
                ok, msg = check_range(key, val)
                result.confidence[f"{eye}.{key}"] = 0.9 if ok else 0.3
                if not ok and msg:
                    result.flags.append(f"{eye}: {msg}")
            else:
                # keratometry fields: light heuristic confidence
                result.confidence[f"{eye}.{key}"] = 0.8 if raw else 0.2

    result.od = fields["od"]
    result.os = fields["os"]

    if not scalars:
        result.notes = "Parsing found no matches; consider LLM fallback"
    return result
