from fastapi import FastAPI, File, UploadFile, HTTPException, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from pathlib import Path
import logging, uuid, shutil

from .config import settings
from .logging_conf import configure_logging
from .models.api import UploadResponse, ExtractResult, ReviewPayload, SuggestQuery, SuggestResponse
from .storage import UPLOADS
from .ocr import ocr_file
from .parser import parse_text
from .audit import write_audit
from .suggest import load_families, toric_decision

configure_logging()
log = logging.getLogger(__name__)

templates = Jinja2Templates(directory="app/templates")

# Serve static assets (CSS/JS) from app/static at /static
app = FastAPI(title="Lakecalc-AI IOL Agent")
app.mount("/static", StaticFiles(directory="app/static"), name="static")


app = FastAPI(title="Lakecalc-AI IOL Agent")

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

@app.get("/extract/{file_id}", response_model=ExtractResult)
async def extract(file_id: str):
    # find file by prefix
    matches = list(UPLOADS.glob(file_id + "*"))
    if not matches:
        raise HTTPException(status_code=404, detail="file_id not found")
    file_path = matches[0]

    text, err = ocr_file(file_path)
    if not text:
        res = ExtractResult(file_id=file_id, text_hash="", notes=f"OCR failed: {err}")
        write_audit("extract_fail", res.model_dump())
        return res

    parsed = parse_text(file_id, text)
    write_audit("extract_ok", parsed.model_dump())
    return JSONResponse(parsed.model_dump())

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
