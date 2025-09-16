from pathlib import Path
from .config import settings

UPLOADS = Path(settings.uploads_dir)
UPLOADS.mkdir(parents=True, exist_ok=True)

AUDIT_DIR = UPLOADS / "audit"
AUDIT_DIR.mkdir(exist_ok=True)

TEXT_DIR = UPLOADS / "ocr"
TEXT_DIR.mkdir(exist_ok=True)

PARSE_DIR = UPLOADS / "parsed"
PARSE_DIR.mkdir(exist_ok=True)
