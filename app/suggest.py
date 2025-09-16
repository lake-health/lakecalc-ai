import json
from pathlib import Path
from .config import settings

FAMILIES_PATH = Path("iol_families.json")


def load_families() -> list[dict]:
    if FAMILIES_PATH.exists():
        return json.loads(FAMILIES_PATH.read_text(encoding="utf-8"))
    return []


def toric_decision(deltaK: float, sia: float | None = None, threshold: float | None = None):
    th = threshold if threshold is not None else settings.toric_threshold
    s = settings.sia_default if sia is None else abs(sia)
    effective = max(0.0, deltaK - s)
    return (effective >= th), effective, th
