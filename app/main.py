
# ...existing code...


# ...existing code...



# Minimal FastAPI app definition for debug endpoint
from fastapi import FastAPI
app = FastAPI()

# Temporary debug endpoint to fetch raw OCR text by file hash
from fastapi.responses import PlainTextResponse
from .storage import TEXT_DIR

@app.get("/debug/ocr_text/{file_hash}", response_class=PlainTextResponse)
async def get_ocr_text(file_hash: str):
    fpath = TEXT_DIR / f"{file_hash}.txt"
    if not fpath.exists():
        return PlainTextResponse("Not found", status_code=404)
    return fpath.read_text(encoding="utf-8")
