
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
from .suggest import toric_decision
from .services.iol_database import get_iol_database

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

# Include routers
from .routes.suggest import router as suggest_router
from .routes.calculate import router as calculate_router
from .routes.parser import router as parser_router
from .routes.parse import router as parse_router
from .routes.extract import router as extract_router
app.include_router(suggest_router, prefix="/suggest", tags=["suggest"])
app.include_router(calculate_router, prefix="/calculate", tags=["calculate"])
app.include_router(parser_router, tags=["parser"])
app.include_router(parse_router, prefix="/parse", tags=["parse"])
app.include_router(extract_router, prefix="/extract", tags=["extract"])

@app.get("/")
def root():
    return {"ok": True, "service": "lakecalc-ai", "uploads_dir": settings.uploads_dir}

@app.get("/health")
def health_check():
    """Health check endpoint for Railway deployment."""
    return {"status": "healthy", "service": "lakecalc-ai", "version": "1.0.0"}

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



# OLD /extract endpoint removed - now handled by app/routes/extract.py
# This uses the new universal biometry parser with RunPod Ollama

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
    """Advanced suggest endpoint using the new Advanced Toric Calculator."""
    try:
        from app.services.toric_calculator import ToricCalculator
        
        # Initialize Advanced Toric Calculator
        calculator = ToricCalculator()
        
        # For the legacy endpoint, we need to estimate some parameters
        # Use reasonable defaults for suggestion purposes
        k1 = 43.0  # Default K1
        k2 = k1 + q.deltaK  # Estimate K2 from deltaK
        k1_axis = 90  # Default steep axis
        k2_axis = 180  # Default flat axis
        
        # Use provided SIA values or eye-specific defaults
        # Note: For the legacy endpoint, we don't know which eye, so use OD default
        sia_magnitude = q.sia_magnitude or q.sia or 0.1  # Default to OD value (0.1D)
        sia_axis = q.sia_axis or 120.0  # Use provided axis or default
        
        # Calculate Haigis ELP for accurate toricity ratio
        from app.services.calculations import IOLCalculator, IOLCalculationInput
        
        # Create minimal biometry for Haigis ELP calculation
        calc_input = IOLCalculationInput(
            axial_length=23.77,  # Default AL for suggestion
            k_avg=(k1 + k2) / 2,  # Average K
            acd=2.83,  # Default ACD
            target_refraction=0.0,
            k1=k1,  # Explicit K1
            k2=k2,  # Explicit K2
            lt=None,  # Not required for Haigis
            wtw=None,  # Not required for Haigis
            cct=None  # Not required for Haigis
        )
        
        iol_calculator = IOLCalculator()
        haigis_result = iol_calculator._calculate_haigis(calc_input, {})
        elp_mm = haigis_result.formula_specific_data.get("ELP_mm", 5.0)
        
        log.info(f"Calculated Haigis ELP: {elp_mm}mm for K1={k1}, K2={k2}, deltaK={q.deltaK}")
        
        # Calculate advanced toric IOL recommendation
        toric_result = calculator.calculate_toric_iol(
            k1=k1, k2=k2, k1_axis=k1_axis, k2_axis=k2_axis,
            sia_magnitude=sia_magnitude, sia_axis=sia_axis,
            elp_mm=elp_mm, target_refraction=0.0,
            policy_key=q.toric_policy or "lifetime_atr"
        )
        
        # Use new IOL database
        db = get_iol_database()
        families_data = db.get_families_for_recommendation(recommend_toric=toric_result.recommend_toric)
        fams = [{"brand": f['brand'], "family": f['family'], "name": f"{f['brand']} {f['family']}"} for f in families_data]
        
        # Use the detailed rationale from the toric calculator
        if isinstance(toric_result.rationale, list):
            rationale = " | ".join(toric_result.rationale)
        else:
            rationale = toric_result.rationale
        
        return SuggestResponse(
            recommend_toric=toric_result.recommend_toric,
            effective_astig=toric_result.total_astigmatism,  # Use total astigmatism as effective
            threshold=1.25,  # Advanced calculator threshold
            rationale=rationale,
            families=fams,
        )
    except Exception as e:
        log.error(f"Error in advanced suggest endpoint: {e}")
        import traceback
        log.error(f"Full traceback: {traceback.format_exc()}")
        # Fallback to basic calculation
        recommend, effective, th = toric_decision(q.deltaK, q.sia)
        fams = [
            {"brand": "Alcon", "family": "AcrySof IQ", "name": "Alcon AcrySof IQ"},
            {"brand": "J&J", "family": "Tecnis", "name": "J&J Tecnis"}
        ]  # Basic fallback
        rationale = f"Fallback calculation: effective_astig = {effective:.2f}D"
        return SuggestResponse(
            recommend_toric=recommend,
            effective_astig=effective,
            threshold=th,
            rationale=rationale,
            families=fams,
        )

@app.get("/suggest/families")
async def get_families():
    """Get all available IOL families from the comprehensive database."""
    try:
        db = get_iol_database()
        families = db.get_all_families()
        return families
    except Exception as e:
        log.error(f"Error loading IOL families: {e}")
        # Fallback to legacy format for backward compatibility
        return [
            {"brand": "Alcon", "family": "AcrySof IQ", "variants": [{"name": "SN60WF", "type": "monofocal"}, {"name": "TORIC SN6ATx", "type": "toric"}]},
            {"brand": "J&J", "family": "Tecnis", "variants": [{"name": "ZCB00", "type": "monofocal"}, {"name": "ZCTx", "type": "toric"}]}
        ]

@app.get("/suggest/policies")
async def get_toric_policies():
    """Get available toric IOL policies."""
    try:
        from app.services.toric_policy import get_available_policies
        return {"policies": get_available_policies()}
    except Exception as e:
        log.error(f"Error getting toric policies: {e}")
        return {"policies": {}}

# Debug endpoint to fetch raw OCR text by file hash
@app.get("/debug/ocr_text/{file_hash}", response_class=PlainTextResponse)
async def get_ocr_text(file_hash: str):
    fpath = TEXT_DIR / f"{file_hash}.txt"
    if not fpath.exists():
        return PlainTextResponse("Not found", status_code=404)
    return fpath.read_text(encoding="utf-8")
