import re, hashlib

DECIMAL_RX = re.compile(r"(?P<num>\d{1,3}[\.,]\d{1,3})")
UNIT_RX = re.compile(r"(mm|µm|um|D|°)")

RANGES = {
    "axial_length": (20.0, 30.0, "mm"),
    "acd": (2.0, 5.0, "mm"),
    "cct": (400.0, 700.0, "µm"),
    "wtw": (10.0, 13.0, "mm"),
    "lt": (3.0, 6.0, "mm"),
}

UNIT_NORMAL = {"um": "µm"}

def to_float(s: str) -> float | None:
    if not s:
        return None
    s = s.strip().replace(",", ".")
    try:
        return float(re.findall(r"-?\d+(?:\.\d+)?", s)[0])
    except Exception:
        return None

def normalize_unit(u: str | None) -> str | None:
    if not u:
        return u
    return UNIT_NORMAL.get(u, u)

def check_range(name: str, value: float | None) -> tuple[bool, str | None]:
    if value is None:
        return False, f"{name} missing"
    lo, hi, unit = RANGES.get(name, (None, None, None))
    if lo is None:
        return True, None
    if not (lo <= value <= hi):
        return False, f"{name} out of range ({value} {unit}, expected {lo}-{hi})"
    return True, None

def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def safe_filename(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]", "_", s)
