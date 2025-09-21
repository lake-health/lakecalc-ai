import io, json, logging, hashlib, os
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

MAX_OCR_PAGES = int(os.getenv("MAX_OCR_PAGES", "2"))  # Only process first 2 pages by default for ophthalmology docs
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
            images.append(pix.tobytes("png"))
    return images

def _make_creds():
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
    # keep backward-compatible simple return
    return resp.full_text_annotation.text or "", None


def _full_text_annotation_to_dict(fta) -> dict:
    """Convert Vision full_text_annotation to a compact JSON-serializable dict.
    We include pages -> blocks -> paragraphs -> words with bounding boxes and text.
    """
    out = {"pages": []}
    try:
        for p in getattr(fta, "pages", []):
            page = {"blocks": []}
            for b in getattr(p, "blocks", []):
                block = {"bbox": [], "paragraphs": []}
                # block bounding box
                try:
                    block["bbox"] = [
                        {"x": v.x, "y": v.y} for v in getattr(b.bounding_box, "vertices", [])
                    ]
                except Exception:
                    block["bbox"] = []
                for par in getattr(b, "paragraphs", []):
                    paragraph = {"words": []}
                    for w in getattr(par, "words", []):
                        # construct word text from symbols if available
                        try:
                            wt = "".join([s.text for s in getattr(w, "symbols", [])])
                        except Exception:
                            wt = getattr(w, "text", "") if hasattr(w, "text") else ""
                        try:
                            bbox = [
                                {"x": v.x, "y": v.y} for v in getattr(w.bounding_box, "vertices", [])
                            ]
                        except Exception:
                            bbox = []
                        paragraph["words"].append({"text": wt, "bbox": bbox})
                    block["paragraphs"].append(paragraph)
                page["blocks"].append(block)
            out["pages"].append(page)
    except Exception:
        # fallback: keep empty structure
        return {"pages": []}
    return out


def google_vision_image_bytes_with_layout(img_bytes: bytes) -> tuple[str, dict | None, str | None]:
    """Return (text, layout_dict, err) for an image bytes input."""
    if vision is None:
        return "", None, "Google Vision SDK not available"
    try:
        creds = _make_creds()
        if not creds:
            return "", None, "GOOGLE_APPLICATION_CREDENTIALS not set"
    except Exception as e:
        return "", None, f"Invalid Google credentials: {e}"

    client = vision.ImageAnnotatorClient(credentials=creds)
    image = vision.Image(content=img_bytes)
    resp = client.document_text_detection(image=image)
    if resp.error.message:
        return "", None, f"Vision error: {resp.error.message}"
    layout = _full_text_annotation_to_dict(resp.full_text_annotation)
    return resp.full_text_annotation.text or "", layout, None

def google_vision_ocr(file_path: Path) -> tuple[str, str | None]:
    if vision is None:
        return "", "Google Vision SDK not available"
    try:
        creds = _make_creds()
        if not creds:
            return "", "GOOGLE_APPLICATION_CREDENTIALS not set"
    except Exception as e:
        return "", f"Invalid Google credentials: {e}"

    # backward-compatible simple call
    client = vision.ImageAnnotatorClient(credentials=creds)
    content = file_path.read_bytes()
    image = vision.Image(content=content)
    response = client.document_text_detection(image=image)
    if response.error.message:
        return "", f"Vision error: {response.error.message}"
    text = response.full_text_annotation.text or ""
    return text, None


def google_vision_ocr_with_layout(file_path: Path) -> tuple[str, dict | None, str | None]:
    """Return (text, layout_dict, err) for a file (image or PDF).
    For PDF we perform a single document_text_detection on the bytes (batch logic can be added later).
    """
    if vision is None:
        return "", None, "Google Vision SDK not available"
    try:
        creds = _make_creds()
        if not creds:
            return "", None, "GOOGLE_APPLICATION_CREDENTIALS not set"
    except Exception as e:
        return "", None, f"Invalid Google credentials: {e}"

    client = vision.ImageAnnotatorClient(credentials=creds)
    content = file_path.read_bytes()
    image = vision.Image(content=content)
    response = client.document_text_detection(image=image)
    if response.error.message:
        return "", None, f"Vision error: {response.error.message}"
    text = response.full_text_annotation.text or ""
    layout = _full_text_annotation_to_dict(response.full_text_annotation)
    return text, layout, None

def ocr_file(file_path: Path) -> tuple[str, str | None]:
    # Cache by SHA256 of file bytes
    fhash = _file_hash(file_path)
    cached = TEXT_DIR / f"{fhash}.txt"
    layout_cached = TEXT_DIR / f"{fhash}.json"
    if cached.exists():
        # read existing cache; if a layout JSON exists, leave it as-is
        return cached.read_text(encoding="utf-8"), None

    ext = file_path.suffix.lower()
    text = ""
    err = None

    if ext in (".jpg", ".jpeg", ".png"):
        # use layout-capable function and cache the layout
        text, layout, err = google_vision_ocr_with_layout(file_path)
        if layout is not None:
            try:
                layout_cached.write_text(json.dumps(layout), encoding="utf-8")
            except Exception:
                log.exception("Failed writing layout cache for %s", file_path.name)

    elif ext == ".pdf":
        # Only process the first MAX_OCR_PAGES pages to avoid confusion from extra layouts
        pages = _render_pdf_pages(file_path, MAX_OCR_PAGES, OCR_DPI)
        if not pages:
            return "", "PDF render failed (no pages)"
        parts: list[str] = []
        # For PDFs we run OCR on each rendered page and also attempt to collect layout
        combined_layout = {"pages": []}
        for png in pages:
            t, layout, e = google_vision_image_bytes_with_layout(png)
            if e:
                err = e
            parts.append(t)
            if layout and layout.get("pages"):
                combined_layout["pages"].extend(layout.get("pages"))
        # cache combined layout
        if combined_layout.get("pages"):
            try:
                layout_cached.write_text(json.dumps(combined_layout), encoding="utf-8")
            except Exception:
                log.exception("Failed writing layout cache for pdf %s", file_path.name)
        text = "\n".join(parts).strip()

    else:
        return "", f"Unsupported file type: {ext}"

    if not text:
        log.error("OCR failed for %s: %s", file_path.name, err)
        return "", err or "OCR failed"

    cached.write_text(text, encoding="utf-8")
    return text, None
