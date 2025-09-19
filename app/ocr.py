import io, json, logging, hashlib, mimetypes, os
from pathlib import Path
import fitz  # PyMuPDF
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

MAX_OCR_PAGES = int(os.getenv("MAX_OCR_PAGES", "1"))
OCR_DPI = int(os.getenv("OCR_DPI", "200"))

def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def _render_pdf_pages(path: Path, max_pages: int = 1, dpi: int = 200) -> list[bytes]:
    images: list[bytes] = []
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    with fitz.open(path) as doc:
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            pix = page.get_pixmap(matrix=mat, alpha=False)
            buf = io.BytesIO(pix.tobytes("png"))
            images.append(buf.getvalue())
    return images

def _make_creds():
    from google.oauth2 import service_account
    if settings.google_creds:
        return service_account.Credentials.from_service_account_file(settings.google_creds)
    elif settings.google_creds_json:
        return service_account.Credentials.from_service_account_info(json.loads(settings.google_creds_json))
    else:
        return None

def google_vision_image_bytes(img_bytes: bytes) -> tuple[str, str | None]:
    if vision is None:
        return "", "Google Vision SDK not available"
    try:
        creds = _make_creds()
        if not creds:
            return "", "GOOGLE_APPLICATION_CREDENTIALS not set"
    except Exception as e:
        return "", f"Invalid Google credentials: {e}"

    client = vision.ImageAnnotatorClient(credentials=creds)
    image = vision.Image(content=img_bytes)
    resp = client.document_text_detection(image=image)
    if resp.error.message:
        return "", f"Vision error: {resp.error.message}"
    return resp.full_text_annotation.text or "", None

def google_vision_ocr(file_path: Path) -> tuple[str, str | None]:
    if vision is None:
        return "", "Google Vision SDK not available"
    try:
        creds = _make_creds()
        if not creds:
            return "", "GOOGLE_APPLICATION_CREDENTIALS not set"
    except Exception as e:
        return "", f"Invalid Google credentials: {e}"

    client = vision.ImageAnnotatorClient(credentials=creds)
    content = file_path.read_bytes()
    image = vision.Image(content=content)
    response = client.document_text_detection(image=image)
    if response.error.message:
        return "", f"Vision error: {response.error.message}"
    text = response.full_text_annotation.text or ""
    return text, None

def ocr_file(file_path: Path) -> tuple[str, str | None]:
    # Cache by hash
    fhash = _file_hash(file_path)
    cached = TEXT_DIR / f"{fhash}.txt"
    if cached.exists():
        return cached.read_text(encoding="utf-8"), None

    ext = file_path.suffix.lower()
    text = ""
    err = None

    if ext in (".jpg", ".jpeg", ".png"):
        text, err = google_vision_ocr(file_path)

    elif ext == ".pdf":
        pages = _render_pdf_pages(file_path, MAX_OCR_PAGES, OCR_DPI)
        if not pages:
            return "", "PDF render failed (no pages)"
        parts = []
        for idx, png in enumerate(pages, start=1):
            t, e = google_vision_image_bytes(png)
            if e: err = e
            parts.append(t)
        text = "\n".join(parts).strip()

    else:
        return "", f"Unsupported file type: {ext}"

    if not text:
        log.error("OCR failed for %s: %s", file_path.name, err)
        return "", err or "OCR failed"

    cached.write_text(text, encoding="utf-8")
    return text, None
```
