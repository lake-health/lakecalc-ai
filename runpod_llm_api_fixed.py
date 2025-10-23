#!/usr/bin/env python3
"""
Fixed RunPod LLM API with proper model routing
Text files → Llama 7B, Image files → LLaVA
"""
import os
import json
import logging
import time
import base64
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
    title="LakeCalc LLM Fixed API",
    description="Fixed biometry parsing service with proper model routing",
    version="1.0.0"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
OLLAMA_BASE_URL = "http://localhost:11434"
TIMEOUT = 120

class ParseResponse(BaseModel):
    success: bool
    data: Dict[str, Any]
    confidence: float
    processing_time: float
    method: str
    error: Optional[str] = None

@app.get("/")
async def root():
    return {"message": "LakeCalc LLM Fixed API", "status": "running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "llm-fixed-api"}

@app.post("/parse", response_model=ParseResponse)
async def parse_biometry(file: UploadFile = File(...)):
    """Parse biometry file using appropriate model"""
    start_time = time.time()
    
    try:
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file.filename.split('.')[-1]}") as tmp_file:
            shutil.copyfileobj(file.file, tmp_file)
            tmp_path = tmp_file.name
        
        # Determine processing method based on file type
        if file.filename.lower().endswith('.txt'):
            # Text files: use Llama 7B
            with open(tmp_path, 'r', encoding='utf-8') as f:
                text = f.read()
            result = await call_llama_7b(text)
            method = "llama_7b_text"
        elif file.filename.lower().endswith('.pdf'):
            # PDF files: try text extraction first, then vision
            text = extract_text_from_pdf(tmp_path)
            if text and len(text.strip()) > 50:
                # Use Llama 7B for text-based PDFs
                result = await call_llama_7b(text)
                method = "llama_7b_text"
            else:
                # Use LLaVA for image-based PDFs
                result = await call_llava_vision(tmp_path)
                method = "llava_vision"
        else:
            # Other files: use LLaVA
            result = await call_llava_vision(tmp_path)
            method = "llava_vision"
        
        # Clean up temp file
        os.unlink(tmp_path)
        
        processing_time = time.time() - start_time
        
        return ParseResponse(
            success=result["success"],
            data=result.get("extracted_data", {}),
            confidence=result.get("confidence", 0.0),
            processing_time=processing_time,
            method=method,
            error=result.get("error")
        )
        
    except Exception as e:
        logger.error(f"Parse error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

def extract_text_from_pdf(file_path: str) -> str:
    """Extract text from PDF using PyPDF2"""
    try:
        import PyPDF2
        with open(file_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            text = ""
            for page in reader.pages:
                text += page.extract_text()
            return text
    except Exception as e:
        logger.error(f"PDF text extraction error: {str(e)}")
        return ""

async def call_llama_7b(text: str) -> Dict[str, Any]:
    """Call Llama 7B for text-based processing"""
    try:
        prompt = f"""Extract biometry data from this text in JSON format:

{text}

Return ONLY valid JSON with:
- patient_name (string)
- age (number)
- od (object with: axial_length, k1, k2, k_axis_1, k_axis_2, acd, lt, wtw, cct)
- os (object with: axial_length, k1, k2, k_axis_1, k_axis_2, acd, lt, wtw, cct)

IMPORTANT: Extract axis values (k_axis_1, k_axis_2) from patterns like "K1: 40.95 D @ 100°" where 100° is the axis.

Example format:
{{
  "patient_name": "John Doe",
  "age": 65,
  "od": {{"axial_length": 23.5, "k1": 42.0, "k2": 43.5, "k_axis_1": 90, "k_axis_2": 0, "acd": 3.0, "lt": 4.5, "wtw": 11.0, "cct": 550}},
  "os": {{"axial_length": 23.7, "k1": 41.8, "k2": 43.2, "k_axis_1": 85, "k_axis_2": 175, "acd": 2.9, "lt": 4.6, "wtw": 11.2, "cct": 545}}
}}"""

        url = f"{OLLAMA_BASE_URL}/api/generate"
        payload = {
            "model": "codellama:7b",
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "top_p": 0.9
            }
        }
        
        response = requests.post(url, json=payload, timeout=TIMEOUT)
        response.raise_for_status()
        
        result = response.json()
        response_text = result.get("response", "")
        
        # Parse JSON response
        try:
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                extracted_data = json.loads(json_str)
                
                # Calculate confidence based on data completeness
                confidence = calculate_confidence(extracted_data)
                
                return {
                    "success": True,
                    "extracted_data": extracted_data,
                    "confidence": confidence
                }
            else:
                raise ValueError("No valid JSON found in response")
                
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"JSON parsing error: {str(e)}")
            return {
                "success": False,
                "extracted_data": {},
                "confidence": 0.0,
                "error": f"Failed to parse JSON: {str(e)}"
            }
        
    except Exception as e:
        logger.error(f"Llama 7B API error: {str(e)}")
        return {
            "success": False,
            "extracted_data": {},
            "confidence": 0.0,
            "error": str(e)
        }

async def call_llava_vision(file_path: str) -> Dict[str, Any]:
    """Call LLaVA vision model for image-based processing"""
    try:
        # Convert file to base64
        with open(file_path, "rb") as image_file:
            image_data = base64.b64encode(image_file.read()).decode('utf-8')
        
        # Create vision prompt for biometry parsing
        prompt = """Extract biometry data from this image in JSON format:

Return ONLY valid JSON with:
- patient_name (string)
- age (number)
- od (object with: axial_length, k1, k2, k_axis_1, k_axis_2, acd, lt, wtw, cct)
- os (object with: axial_length, k1, k2, k_axis_1, k_axis_2, acd, lt, wtw, cct)

IMPORTANT: Extract axis values (k_axis_1, k_axis_2) from patterns like "K1: 40.95 D @ 100°" where 100° is the axis.

Example format:
{
  "patient_name": "John Doe",
  "age": 65,
  "od": {"axial_length": 23.5, "k1": 42.0, "k2": 43.5, "k_axis_1": 90, "k_axis_2": 0, "acd": 3.0, "lt": 4.5, "wtw": 11.0, "cct": 550},
  "os": {"axial_length": 23.7, "k1": 41.8, "k2": 43.2, "k_axis_1": 85, "k_axis_2": 175, "acd": 2.9, "lt": 4.6, "wtw": 11.2, "cct": 545}
}"""

        # Call LLaVA with vision
        url = f"{OLLAMA_BASE_URL}/api/generate"
        payload = {
            "model": "llava:latest",
            "prompt": prompt,
            "images": [image_data],
            "stream": False,
            "options": {
                "temperature": 0.1,
                "top_p": 0.9
            }
        }
        
        response = requests.post(url, json=payload, timeout=TIMEOUT)
        response.raise_for_status()
        
        result = response.json()
        response_text = result.get("response", "")
        
        # Parse JSON response
        try:
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                extracted_data = json.loads(json_str)
                
                # Calculate confidence based on data completeness
                confidence = calculate_confidence(extracted_data)
                
                return {
                    "success": True,
                    "extracted_data": extracted_data,
                    "confidence": confidence
                }
            else:
                raise ValueError("No valid JSON found in response")
                
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"JSON parsing error: {str(e)}")
            return {
                "success": False,
                "extracted_data": {},
                "confidence": 0.0,
                "error": f"Failed to parse JSON: {str(e)}"
            }
        
    except Exception as e:
        logger.error(f"LLaVA vision API error: {str(e)}")
        return {
            "success": False,
            "extracted_data": {},
            "confidence": 0.0,
            "error": str(e)
        }

def calculate_confidence(data: Dict[str, Any]) -> float:
    """Calculate confidence based on data completeness"""
    total_fields = 0
    filled_fields = 0
    
    # Check patient info
    if data.get("patient_name"):
        filled_fields += 1
    total_fields += 1
    
    if data.get("age"):
        filled_fields += 1
    total_fields += 1
    
    # Check OD data
    od_data = data.get("od", {})
    for field in ["axial_length", "k1", "k2"]:
        if od_data.get(field):
            filled_fields += 1
        total_fields += 1
    
    # Check OS data
    os_data = data.get("os", {})
    for field in ["axial_length", "k1", "k2"]:
        if os_data.get(field):
            filled_fields += 1
        total_fields += 1
    
    return filled_fields / total_fields if total_fields > 0 else 0.0

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003, log_level="info")
