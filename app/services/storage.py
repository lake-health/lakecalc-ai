import uuid
from typing import Optional
from pathlib import Path
from app.settings import settings

# Directory for uploads
UPLOADS_DIR = Path(settings.uploads_dir or "uploads")
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

def save_upload(file_obj, original_name: str) -> tuple[str, Path]:
    """
    Save an uploaded file to the uploads directory.

    Args:
        file_obj: File-like object (from FastAPI's UploadFile.file).
        original_name: Original filename from the upload.

    Returns:
        file_id: Unique hex ID for the saved file.
        path: Full Path where the file was stored.
    """
    file_id = uuid.uuid4().hex
    ext = Path(original_name).suffix.lower() or ".bin"
    path = UPLOADS_DIR / f"{file_id}{ext}"
    with open(path, "wb") as out:
        out.write(file_obj.read())
    return file_id, path

def resolve_path(file_id: str) -> Optional[Path]:
    """
    Given a file_id, return the corresponding file path if it exists.
    """
    for p in UPLOADS_DIR.iterdir():
        if p.name.startswith(file_id):
            return p
    return None
