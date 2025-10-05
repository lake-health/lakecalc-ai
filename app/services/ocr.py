from app.settings import settings

def google_ocr_image_or_pdf(path: str) -> str:
    from google.cloud import vision
    from google.cloud.vision_v1 import types as v1types
    from mimetypes import guess_type

    client = vision.ImageAnnotatorClient()
    mime, _ = guess_type(path)

    if mime and "pdf" in mime:
        with open(path, "rb") as f:
            content = f.read()
        feature = v1types.Feature(type=v1types.Feature.Type.DOCUMENT_TEXT_DETECTION)
        request = v1types.AnnotateFileRequest(
            input_config=v1types.InputConfig(content=content, mime_type="application/pdf"),
            features=[feature],
        )
        response = client.batch_annotate_files(requests=[request])
        text = []
        for r in response.responses:
            for p in r.responses:
                if p.full_text_annotation and p.full_text_annotation.text:
                    text.append(p.full_text_annotation.text)
        return "\n".join(text)
    else:
        with open(path, "rb") as image_file:
            content = image_file.read()
        image = vision.Image(content=content)
        resp = client.document_text_detection(image=image)
        if resp.error.message:
            raise RuntimeError(resp.error.message)
        return (resp.full_text_annotation.text or "").strip()

def run_ocr(path: str) -> str:
    provider = settings.ocr_provider.lower()
    if provider == "google":
        return google_ocr_image_or_pdf(path)
    raise RuntimeError(f"OCR provider not supported: {provider}")

from pathlib import Path
import json
import logging
import hashlib
from typing import Tuple, Optional

from .config import settings
from .storage import TEXT_DIR

logger = logging.getLogger(__name__)

def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def _save_layout_cache(text_hash: str, layout: dict) -> None:
    try:
        TEXT_DIR.mkdir(parents=True, exist_ok=True)
        p = TEXT_DIR / f"{text_hash}.json"
        p.write_text(json.dumps({"version": "1", "pages": layout.get("pages", [])}, ensure_ascii=False), encoding="utf-8")
    except Exception:
        logger.exception("failed to write layout cache")

def _build_layout_from_full_text_annotation(fta) -> dict:
    pages_out = []
    try:
        for page in getattr(fta, "pages", []):
            blocks_out = []
            for block in getattr(page, "blocks", []):
                paras_out = []
                for para in getattr(block, "paragraphs", []):
                    words_out = []
                    for word in getattr(para, "words", []):
                        # reconstruct word text
                        symbols = getattr(word, "symbols", [])
                        wtext = "".join(getattr(s, "text", "") for s in symbols)
                        # collect bbox vertices (x,y)
                        bbox = []
                        for v in getattr(word, "bounding_box", []).vertices:
                            bbox.append({"x": getattr(v, "x", 0), "y": getattr(v, "y", 0)})
                        words_out.append({"text": wtext, "bbox": bbox})
                    paras_out.append({"words": words_out})
                blocks_out.append({"paragraphs": paras_out})
            pages_out.append({"blocks": blocks_out})
    except Exception:
        logger.exception("error building layout from annotation")
    return {"pages": pages_out}

def _preprocess_image_bytes(img_bytes: bytes) -> bytes:
    """Attempt a lightweight preprocessing using Pillow. Returns JPEG bytes."""
    try:
        from PIL import Image, ImageOps
        import io
    except Exception:
        # Pillow not available; return original bytes
        return img_bytes
    try:
        buf = io.BytesIO(img_bytes)
        img = Image.open(buf).convert("L")  # grayscale
        img = ImageOps.autocontrast(img, cutoff=1)
        # upscale small images to improve OCR accuracy
        if max(img.size) < 1600:
            img = img.resize((int(img.size[0] * 2), int(img.size[1] * 2)), Image.LANCZOS)
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=90)
        return out.getvalue()
    except Exception:
        logger.exception("image preprocessing failed; returning original bytes")
        return img_bytes

def google_document_ocr(path: str) -> Tuple[Optional[str], Optional[dict]]:
    """
    Run Google Vision Document OCR on path.
    Returns (full_text or None, layout dict or None).
    """
    try:
        from google.cloud import vision_v1 as vision
        client = vision.ImageAnnotatorClient()
    except Exception:
        logger.exception("google cloud vision not available")
        return None, None

    try:
        from mimetypes import guess_type
        mime, _ = guess_type(path)
        with open(path, "rb") as f:
            content = f.read()
    except Exception:
        logger.exception("failed reading file for OCR")
        return None, None

    # If image, attempt lightweight preprocessing to improve OCR
    if not mime or "pdf" not in (mime or ""):
        content = _preprocess_image_bytes(content)

    try:
        if mime and "pdf" in mime:
            feature = vision.types.Feature(type=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)
            input_cfg = vision.types.InputConfig(content=content, mime_type="application/pdf")
            request = vision.types.AnnotateFileRequest(input_config=input_cfg, features=[feature])
            response = client.batch_annotate_files(requests=[request])
            # accumulate text + layout from responses
            text_parts = []
            layout_pages = []
            for resp in response.responses:
                for r in resp.responses:
                    fta = getattr(r, "full_text_annotation", None)
                    if fta and getattr(fta, "text", ""):
                        text_parts.append(fta.text)
                        layout_pages.extend(_build_layout_from_full_text_annotation(fta).get("pages", []))
            full_text = "\n".join(text_parts).strip() if text_parts else ""
            layout = {"pages": layout_pages} if layout_pages else None
            return full_text, layout
        else:
            image = vision.types.Image(content=content)
            resp = client.document_text_detection(image=image)
            fta = getattr(resp, "full_text_annotation", None)
            full_text = (fta.text or "").strip() if fta else ""
            layout = _build_layout_from_full_text_annotation(fta) if fta else None
            return full_text, layout
    except Exception:
        logger.exception("vision OCR call failed")
        return None, None

def run_ocr(path: str) -> Tuple[Optional[str], Optional[dict]]:
    """
    High-level OCR entrypoint used by the app.
    Returns (text, layout) where layout is a compact dict with pages->blocks->paragraphs->words (with bbox).
    If layout is produced, writes a cached JSON in TEXT_DIR/<hash>.json for reuse.
    """
    text, layout = google_document_ocr(path)
    if not text:
        # return empty text with None layout; caller should handle errors
        return None, None
    text_hash = _text_hash(text)
    if layout:
        try:
            _save_layout_cache(text_hash, layout)
        except Exception:
            logger.exception("saving layout cache failed")
    return text, layout

# ...staged changes present; ensure GOOGLE credentials available before testing
