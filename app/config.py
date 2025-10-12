import os
from pydantic import BaseModel

class Settings(BaseModel):
    uploads_dir: str = os.getenv("UPLOADS_DIR", "uploads")
    allow_origin: str = os.getenv("ALLOW_ORIGIN", "*")
    ocr_provider: str = os.getenv("OCR_PROVIDER", "google")
    google_creds: str | None = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    google_creds_json: str | None = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON") or os.getenv("GOOGLE_CREDENTIALS_JSON")
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "30"))
    toric_threshold: float = float(os.getenv("TORIC_THRESHOLD", "1.0"))
    sia_default: float = float(os.getenv("SIA_DEFAULT", "0.3"))
    strict_text_extraction: bool = os.getenv("STRICT_TEXT_EXTRACTION", "false").lower() in ("1", "true", "yes")

settings = Settings()
