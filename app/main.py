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
