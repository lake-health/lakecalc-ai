import json, logging
from pathlib import Path
from .config import settings
from .storage import TEXT_DIR

log = logging.getLogger(__name__)

try:
    if settings.ocr_provider == "google":
        from google.cloud import vision
        from google.oauth2 import service_account
    else:
        vision = None
except Exception as e:
    vision = None
    log.exception("Failed importing Google Vision SDK: %s", e)


def google_vision_ocr(file_path: Path) -> tuple[str, str | None]:
    if vision is None:
        return "", "Google Vision SDK not available"
    if not settings.google_creds:
        return "", "GOOGLE_APPLICATION_CREDENTIALS not set"
    creds = service_account.Credentials.from_service_account_file(settings.google_creds)
    client = vision.ImageAnnotatorClient(credentials=creds)

    content = file_path.read_bytes()
    image = vision.Image(content=content)
    response = client.document_text_detection(image=image)
    if response.error.message:
        return "", f"Vision error: {response.error.message}"
    text = response.full_text_annotation.text or ""
    return text, None


def ocr_file(file_path: Path) -> tuple[str, str | None]:
    if settings.ocr_provider == "google":
        text, err = google_vision_ocr(file_path)
    else:
        text, err = "", "Unsupported OCR provider"

    if not text:
        log.error("OCR failed for %s: %s", file_path.name, err)
        return "", err or "OCR failed"
    # persist raw OCR text
    out = TEXT_DIR / (file_path.stem + ".txt")
    out.write_text(text, encoding="utf-8")
    return text, None
