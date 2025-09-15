#!/usr/bin/env bash
set -euo pipefail

mkdir -p app/{routes,services,models} uploads

# --- init files ---
cat > app/__init__.py <<'PY'
"""LakeCalc AI FastAPI package."""
PY
cp app/__init__.py app/routes/__init__.py
cp app/__init__.py app/services/__init__.py
cp app/__init__.py app/models/__init__.py

# --- main.py ---
cat > app/main.py <<'PY'
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.settings import settings
from app.routes import ui, upload, extract, review, suggest

app = FastAPI(
    title="LakeCalc AI – IOL Agent",
    description="Upload → OCR → Parse → Review → Suggest",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.allow_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ui.router, tags=["ui"])
app.include_router(upload.router, prefix="/upload", tags=["upload"])
app.include_router(extract.router, prefix="/extract", tags=["extract"])
app.include_router(review.router, prefix="/review", tags=["review"])
app.include_router(suggest.router, prefix="/suggest", tags=["suggest"])

@app.get("/")
async def health():
    return {"status": "ok", "service": "lakecalc-ai"}
PY

# --- settings.py ---
if [ ! -f app/settings.py ]; then
cat > app/settings.py <<'PY'
import os

class Settings:
    openai_api_key = os.getenv("OPENAI_API_KEY")
    ocr_provider = os.getenv("OCR_PROVIDER", "google")
    allow_origin = os.getenv("ALLOW_ORIGIN", "*")
    uploads_dir = os.getenv("UPLOADS_DIR", "uploads")
    iol_families_path = os.getenv("IOL_FAMILIES_PATH", "iol_families.json")

settings = Settings()
PY
fi


# --- models/schema.py ---
cat > app/models/schema.py <<'PY'
from pydantic import BaseModel, Field, validator
from typing import Optional, Literal

Eye = Literal["OD", "OS"]

class ExtractedKs(BaseModel):
    k1_power: Optional[float] = Field(None, description="D")
    k1_axis: Optional[float] = Field(None, description="degrees")
    k2_power: Optional[float] = Field(None, description="D")
    k2_axis: Optional[float] = Field(None, description="degrees")
    delta_k: Optional[float] = Field(None, description="D")

class ExtractedBiometry(BaseModel):
    device: Optional[str]
    eye: Optional[Eye]
    al_mm: Optional[float]
    acd_mm: Optional[float]
    cct_um: Optional[int]
    wtw_mm: Optional[float]
    lt_mm: Optional[float]
    ks: ExtractedKs = ExtractedKs()
    notes: Optional[str]
    confidence: dict = {}

class UploadResponse(BaseModel):
    file_id: str
    filename: str

class ReviewPayload(ExtractedBiometry):
    pass

class SuggestionRequest(BaseModel):
    data: ExtractedBiometry
    sia_d: Optional[float] = 0.0

class SuggestionResponse(BaseModel):
    recommend_toric: bool
    rationale: str
    suggested_families: list[str] = []
    image_hint_url: Optional[str] = None

    @validator("suggested_families", pre=True, always=True)
    def default_families(cls, v):
        return v or []
PY

# --- services/storage.py ---
cat > app/services/storage.py <<'PY'
import uuid
from pathlib import Path
from app.settings import settings

UPLOADS = Path(settings.uploads_dir)
UPLOADS.mkdir(exist_ok=True, parents=True)

def save_upload(file_obj, original_name: str) -> tuple[str, Path]:
    file_id = uuid.uuid4().hex
    ext = Path(original_name).suffix.lower() or ".bin"
    path = UPLOADS / f"{file_id}{ext}"
    with open(path, "wb") as out:
        out.write(file_obj.read())
    return file_id, path

def resolve_path(file_id: str) -> Path | None:
    for p in UPLOADS.iterdir():
        if p.name.startswith(file_id):
            return p
    return None
PY

# --- services/ocr.py ---
cat > app/services/ocr.py <<'PY'
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
PY

# --- services/parsing.py ---
cat > app/services/parsing.py <<'PY'
import re
from typing import Tuple, Dict
from app.models.schema import ExtractedBiometry, ExtractedKs

MM = r"(?:(?:mm)|(?:\s?mm))"
UM = r"(?:(?:µm)|(?:um)|(?:microns?))"
D  = r"(?:D|diopters?)"
DEG = r"(?:°|deg|degrees?)"

def _find_float(pattern: str, text: str) -> Tuple[float | None, float]:
    m = re.search(pattern, text, flags=re.IGNORECASE)
    if not m:
        return None, 0.0
    try:
        return float(m.group(1).replace(',', '.')), 0.8
    except Exception:
        return None, 0.0

def parse_biometry(raw_text: str) -> ExtractedBiometry:
    device_match = re.search(r"(IOLMaster\s*700|NIDEK[-\s]?ALScan|Pentacam|Galilei|Atlas\s*9000|EyeSys)", raw_text, re.I)
    device = device_match.group(1) if device_match else None
    device_conf = 0.6 if device else 0.0

    eye_match = re.search(r"\b(OD|OS)\b", raw_text)
    eye = eye_match.group(1) if eye_match else None
    eye_conf = 0.7 if eye else 0.0

    al, al_c   = _find_float(r"AL[:\s]*([0-9]+(?:[.,][0-9]+)?)\s*" + MM, raw_text)
    acd, acd_c = _find_float(r"ACD[:\s]*([0-9]+(?:[.,][0-9]+)?)\s*" + MM, raw_text)
    lt, lt_c   = _find_float(r"LT[:\s]*([0-9]+(?:[.,][0-9]+)?)\s*" + MM, raw_text)
    wtw, wtw_c = _find_float(r"WTW[:\s]*([0-9]+(?:[.,][0-9]+)?)\s*" + MM, raw_text)
    cct, cct_c = _find_float(r"CCT[:\s]*([0-9]+)\s*" + UM, raw_text)

    k1_power, k1c = _find_float(r"K1[:\s]*([0-9]+(?:[.,][0-9]+)?)\s*" + D, raw_text)
    k2_power, k2c = _find_float(r"K2[:\s]*([0-9]+(?:[.,][0-9]+)?)\s*" + D, raw_text)
    k1_axis, k1ax_c = _find_float(r"K1[^@\n]*@\s*([0-9]+(?:[.,][0-9]+)?)\s*" + DEG, raw_text)
    k2_axis, k2ax_c = _find_float(r"K2[^@\n]*@\s*([0-9]+(?:[.,][0-9]+)?)\s*" + DEG, raw_text)

    delta_k = None
    if k1_power is not None and k2_power is not None:
        delta_k = round(abs(k2_power - k1_power), 2)

    ks = ExtractedKs(
        k1_power=k1_power,
        k1_axis=k1_axis,
        k2_power=k2_power,
        k2_axis=k2_axis,
        delta_k=delta_k,
    )

    confidence: Dict[str, float] = {
        "device": device_conf,
        "eye": eye_conf,
        "al_mm": al_c,
        "acd_mm": acd_c,
        "lt_mm": lt_c,
        "wtw_mm": wtw_c,
        "cct_um": cct_c,
        "k1_power": k1c,
        "k1_axis": k1ax_c,
        "k2_power": k2c,
        "k2_axis": k2ax_c,
    }

    return ExtractedBiometry(
        device=device,
        eye=eye,
        al_mm=al,
        acd_mm=acd,
        lt_mm=lt,
        wtw_mm=wtw,
        cct_um=int(cct) if cct is not None else None,
        ks=ks,
        confidence=confidence,
    )
PY

# --- routes/ui.py ---
cat > app/routes/ui.py <<'PY'
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/ui", response_class=HTMLResponse)
async def ui_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
PY

# --- routes/upload.py ---
cat > app/routes/upload.py <<'PY'
from fastapi import APIRouter, UploadFile, File, HTTPException
from app.services.storage import save_upload
from app.models.schema import UploadResponse

router = APIRouter()

@router.post("/", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Empty filename")
    file_id, path = save_upload(file.file, file.filename)
    return UploadResponse(file_id=file_id, filename=path.name)
PY

# --- routes/extract.py ---
cat > app/routes/extract.py <<'PY'
from fastapi import APIRouter, HTTPException
from app.services.storage import resolve_path
from app.services.ocr import run_ocr
from app.services.parsing import parse_biometry
from app.models.schema import ExtractedBiometry

router = APIRouter()

@router.get("/{file_id}", response_model=ExtractedBiometry)
async def extract_fields(file_id: str):
    path = resolve_path(file_id)
    if not path:
        raise HTTPException(status_code=404, detail="File not found")

    raw_text = run_ocr(str(path))
    data = parse_biometry(raw_text)

    if not any([data.al_mm, data.acd_mm, data.ks.k1_power, data.ks.k2_power, data.cct_um, data.wtw_mm, data.lt_mm]):
        data.notes = "Low-confidence extraction. Please enter values manually."
    return data
PY

# --- routes/review.py ---
cat > app/routes/review.py <<'PY'
from fastapi import APIRouter
from app.models.schema import ReviewPayload

router = APIRouter()

@router.post("/", response_model=ReviewPayload)
async def review_confirm(payload: ReviewPayload):
    return payload
PY

# --- routes/suggest.py ---
cat > app/routes/suggest.py <<'PY'
from fastapi import APIRouter
from app.models.schema import SuggestionRequest, SuggestionResponse

router = APIRouter()
TORIC_THRESHOLD_D = 1.0

@router.post("/", response_model=SuggestionResponse)
async def suggest_iol(req: SuggestionRequest):
    k = req.data.ks
    sia = req.sia_d or 0.0

    recommend_toric = False
    rationale_lines = []

    if k.delta_k is not None:
        effective_astig = max(0.0, (k.delta_k or 0.0) - abs(sia))
        recommend_toric = effective_astig >= TORIC_THRESHOLD_D
        rationale_lines.append(
            f"deltaK={k.delta_k:.2f}D; SIA={sia:.2f}D → effective ~{effective_astig:.2f}D"
        )
    else:
        rationale_lines.append("Insufficient K data to compute deltaK; defaulting to non-toric.")

    families = [
        "Alcon AcrySof IQ Toric / Non-Toric",
        "J&J Tecnis Toric / Non-Toric",
        "Rayner Toric / Non-Toric",
        "Hoya Toric / Non-Toric",
    ]

    return SuggestionResponse(
        recommend_toric=recommend_toric,
        rationale="; ".join(rationale_lines),
        suggested_families=families,
        image_hint_url=None,
    )
PY

# --- iol_families.json ---
cat > iol_families.json <<'PY'
[
  {"brand": "Alcon", "models": ["AcrySof IQ", "PanOptix", "Vivity"], "toric": true},
  {"brand": "Johnson & Johnson", "models": ["Tecnis", "Eyhance"], "toric": true},
  {"brand": "Rayner", "models": ["RayOne", "Sulcoflex"], "toric": true},
  {"brand": "Hoya", "models": ["iSert"], "toric": true}
]
PY

# --- .gitignore (ensure uploads ignored) ---
if [ ! -f .gitignore ]; then
  cat > .gitignore <<'PY'
__pycache__/
*.pyc
.env
uploads/
PY
else
  grep -qxF 'uploads/' .gitignore || echo 'uploads/' >> .gitignore
fi

# --- requirements.txt ensure deps ---
REQS=(
  "fastapi"
  "uvicorn[standard]"
  "python-multipart"
  "pydantic"
  "jinja2"
  "aiofiles"
  "google-cloud-vision"
  "openai"
)
if [ ! -f requirements.txt ]; then
  printf "%s\n" "${REQS[@]}" > requirements.txt
else
  for r in "${REQS[@]}"; do
    grep -qxF "$r" requirements.txt || echo "$r" >> requirements.txt
  done
fi

echo "Done ✅  Try: uvicorn app.main:app --reload"
