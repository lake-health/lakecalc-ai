# app/settings.py
import os

class Settings:
    openai_api_key = os.getenv("OPENAI_API_KEY")
    ocr_provider = os.getenv("OCR_PROVIDER", "google")
    allow_origin = os.getenv("ALLOW_ORIGIN", "*")
    uploads_dir = os.getenv("UPLOADS_DIR", "uploads")
    iol_families_path = os.getenv("IOL_FAMILIES_PATH", "iol_families.json")

settings = Settings()

