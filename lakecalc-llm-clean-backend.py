#!/usr/bin/env python3
"""
Clean LLM-only biometry parser backend
"""
import os
import json
import logging
import time
from typing import Dict, Any, Optional
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import tempfile
import shutil

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="LakeCalc LLM Parser",
    description="Clean LLM-only biometry parsing service",
    version="1.0.0"
)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# RunPod LLM API configuration
RUNPOD_BASE_URL = "https://nko8ymjws3px2s-8001.proxy.runpod.net"
TIMEOUT = 120

class ParseRequest(BaseModel):
    text: str

class ParseResponse(BaseModel):
    success: bool
    data: Dict[str, Any]
    confidence: float
    processing_time: float
    method: str
    error: Optional[str] = None

@app.get("/")
async def root():
    return {"message": "LakeCalc LLM Parser API", "status": "running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "llm-parser"}

@app.post("/parse", response_model=ParseResponse)
async def parse_biometry(file: UploadFile = File(...)):
    """Parse biometry file using RunPod LLM"""
    start_time = time.time()
    
    try:
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file.filename.split('.')[-1]}") as tmp_file:
            shutil.copyfileobj(file.file, tmp_file)
            tmp_path = tmp_file.name
        
        # Extract text from file
        text = extract_text_from_file(tmp_path)
        
        # Clean up temp file
        os.unlink(tmp_path)
        
        if not text:
            raise HTTPException(status_code=400, detail="Could not extract text from file")
        
        # Call RunPod LLM API
        result = await call_runpod_llm(text)
        
        processing_time = time.time() - start_time
        
        return ParseResponse(
            success=result["success"],
            data=result.get("extracted_data", {}),
            confidence=result.get("confidence", 0.0),
            processing_time=processing_time,
            method="runpod_llm",
            error=result.get("error")
        )
        
    except Exception as e:
        logger.error(f"Parse error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

def extract_text_from_file(file_path: str) -> str:
    """Extract text from various file types"""
    try:
        if file_path.lower().endswith('.pdf'):
            import PyPDF2
            with open(file_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                text = ""
                for page in reader.pages:
                    text += page.extract_text()
                return text
        elif file_path.lower().endswith(('.txt', '.csv')):
            with open(file_path, 'r', encoding='utf-8') as file:
                return file.read()
        else:
            # For images, we'd need OCR, but for now return empty
            return ""
    except Exception as e:
        logger.error(f"Text extraction error: {str(e)}")
        return ""

async def call_runpod_llm(text: str) -> Dict[str, Any]:
    """Call RunPod LLM API"""
    try:
        url = f"{RUNPOD_BASE_URL}/parse"
        payload = {
            "text": text,
            "device_type": "universal",
            "confidence_threshold": 0.3
        }
        
        response = requests.post(url, json=payload, timeout=TIMEOUT)
        response.raise_for_status()
        
        return response.json()
        
    except Exception as e:
        logger.error(f"RunPod LLM API error: {str(e)}")
        return {
            "success": False,
            "extracted_data": {},
            "confidence": 0.0,
            "error": str(e)
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
