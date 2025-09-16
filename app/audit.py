import json, time
from pathlib import Path
from .storage import AUDIT_DIR


def write_audit(name: str, payload: dict) -> None:
    ts = time.strftime("%Y%m%d-%H%M%S")
    p = AUDIT_DIR / f"{ts}-{name}.json"
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
