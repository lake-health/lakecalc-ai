
# ...existing code...


# ...existing code...




# ...existing code...

from fastapi import FastAPI, File, UploadFile, HTTPException, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from pathlib import Path
import logging, uuid, shutil

from .config import settings
from .logging_conf import configure_logging
from .models.api import UploadResponse, ExtractResult, ReviewPayload, SuggestQuery, SuggestResponse
from .storage import UPLOADS, TEXT_DIR
from .ocr import ocr_file
from .parser import parse_text
from .audit import write_audit
from .suggest import load_families, toric_decision

configure_logging()
log = logging.getLogger(__name__)

templates = Jinja2Templates(directory="templates")

# Serve static assets (CSS/JS) from app/static at /static
app = FastAPI(title="Lakecalc-AI IOL Agent")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.allow_origin] if settings.allow_origin != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

app.add_middleware(RequestIdMiddleware)

@app.get("/")
def root():
    return {"ok": True, "service": "lakecalc-ai", "uploads_dir": settings.uploads_dir}

@app.post("/upload", response_model=UploadResponse)
async def upload(file: UploadFile = File(...)):
    if file.content_type not in {"application/pdf", "image/png", "image/jpeg"}:
        raise HTTPException(status_code=400, detail="Only pdf|png|jpg|jpeg accepted")
    # size cap
    body = await file.read()
    mb = len(body) / (1024 * 1024)
    if mb > settings.max_upload_mb:
        raise HTTPException(status_code=413, detail=f"File too large: {mb:.1f} MB")

    fid = str(uuid.uuid4())
    ext = Path(file.filename).suffix.lower() or ".bin"
    dest = UPLOADS / f"{fid}{ext}"
    with open(dest, "wb") as f:
        f.write(body)

    write_audit("upload", {"file_id": fid, "filename": file.filename, "content_type": file.content_type, "size_mb": mb})
    return UploadResponse(file_id=fid, filename=file.filename)



from app.utils import llm_extract_missing_fields

@app.get("/extract/{file_id}", response_model=ExtractResult)
async def extract(file_id: str, debug: bool = False):
    # find file by prefix
    matches = list(UPLOADS.glob(file_id + "*"))
    if not matches:
        raise HTTPException(status_code=404, detail="file_id not found")
    file_path = matches[0]

    text, err = ocr_file(file_path)
    if not text:
        # OCR failed, but we can still try LLM fallback with file metadata
        # Create a basic text representation for LLM processing
        text = f"Medical document: {file_path.name} - File type: {file_path.suffix} - OCR failed: {err}"
        log.warning("OCR failed for %s, using LLM fallback with minimal context", file_path.name)

    parsed = parse_text(file_id, text)
    result = parsed.model_dump()

    # Identify missing/low-confidence fields for LLM fallback
    def get_missing_fields(eye):
        fields = ["axial_length", "lt", "cct", "ak", "axis", "k1", "k2", "k1_axis", "k2_axis", "acd", "wtw"]
        return [k for k in fields if not getattr(parsed, eye).__dict__.get(k)]
    missing_fields = {
        "od": get_missing_fields("od"),
        "os": get_missing_fields("os"),
    }

    # If OCR failed, be more aggressive with LLM fallback
    ocr_failed = bool(err)
    if ocr_failed:
        # When OCR fails, request all important fields from LLM
        missing_fields = {
            "od": ["axial_length", "lt", "cct", "ak", "k1", "k2", "k1_axis", "k2_axis", "acd", "wtw"],
            "os": ["axial_length", "lt", "cct", "ak", "k1", "k2", "k1_axis", "k2_axis", "acd", "wtw"]
        }

    # Only call LLM if any fields are missing
    if missing_fields["od"] or missing_fields["os"]:
        llm_results = llm_extract_missing_fields(text, missing_fields)
        for eye in ("od", "os"):
            eye_llm = llm_results.get(eye, {})
            for k, v in eye_llm.items():
                # support both simple values and {value, axis} objects for k1/k2
                if k in ("k1", "k2") and isinstance(v, dict):
                    if v.get("value") and not result[eye].get(k):
                        result[eye][k] = v.get("value")
                        result["confidence"][f"{eye}.{k}"] = 0.7
                    # merge axis into k1_axis/k2_axis
                    axis_key = f"{k}_axis"
                    if v.get("axis") and not result[eye].get(axis_key):
                        result[eye][axis_key] = v.get("axis")
                        result["confidence"][f"{eye}.{axis_key}"] = 0.7
                else:
                    if v and not result[eye].get(k):
                        result[eye][k] = v
                        result["confidence"][f"{eye}.{k}"] = 0.7
        result["llm_fallback"] = True
        if ocr_failed:
            result["notes"] = f"OCR failed: {err}. Used LLM fallback for data extraction."
    else:
        result["llm_fallback"] = False

    write_audit("extract_ok", result)
    if debug:
        result["ocr_text"] = text
    return JSONResponse(result)

@app.post("/review")
async def review(payload: ReviewPayload):
    # Validate numeric ranges on edited values if keys match known fields
    from .utils import to_float, check_range

    flags = []
    for key, value in payload.edits.items():
        base_key = key.split(".")[-1]
        if base_key in {"axial_length", "acd", "lt", "cct", "wtw"}:
            ok, msg = check_range(base_key, to_float(str(value)))
            if not ok and msg:
                flags.append(f"{key}: {msg}")

    write_audit("review", {"file_id": payload.file_id, "edits": payload.edits, "flags": flags})
    return {"ok": True, "file_id": payload.file_id, "flags": flags}

@app.get("/review", response_class=HTMLResponse)
async def review_form(request: Request, file_id: str):
    return templates.TemplateResponse("review.html", {"request": request, "file_id": file_id})

@app.post("/suggest", response_model=SuggestResponse)
async def suggest(q: SuggestQuery):
    recommend, effective, th = toric_decision(q.deltaK, q.sia)
    fams = load_families()
    rationale = (
        f"effective_astig = deltaK - |SIA| = {q.deltaK:.2f} - {abs(q.sia) if q.sia is not None else settings.sia_default:.2f} = {effective:.2f}; "
        f"threshold = {th:.2f} → {'RECOMMEND TORIC' if recommend else 'NON‑TORIC OK'}"
    )
    return SuggestResponse(
        recommend_toric=recommend,
        effective_astig=effective,
        threshold=th,
        rationale=rationale,
        families=fams,
    )

@app.get("/suggest/families")
async def get_families():
    return load_families()

# Debug endpoint to fetch raw OCR text by file hash
@app.get("/debug/ocr_text/{file_hash}", response_class=PlainTextResponse)
async def get_ocr_text(file_hash: str):
    fpath = TEXT_DIR / f"{file_hash}.txt"
    if not fpath.exists():
        return PlainTextResponse("Not found", status_code=404)
    return fpath.read_text(encoding="utf-8")
