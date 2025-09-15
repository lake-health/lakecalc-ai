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
