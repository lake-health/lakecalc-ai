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
