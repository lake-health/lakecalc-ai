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
