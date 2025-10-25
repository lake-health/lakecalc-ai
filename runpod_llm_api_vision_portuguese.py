#!/usr/bin/env python3
"""
RunPod LLM API with Vision Support - Portuguese/Italian Medical Document Version
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
    title="LakeCalc LLM Vision API",
    description="Universal biometry parsing service with vision support",
    version="2.0.0"
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
    return {"message": "LakeCalc LLM Vision API", "status": "running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "llm-vision-api"}

@app.post("/parse", response_model=ParseResponse)
async def parse_biometry(file: UploadFile = File(...)):
    """Parse biometry file using appropriate model with vision support"""
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
                # Use LLaVA for image-based PDFs with PDF-to-image conversion
                result = await call_llava_vision_pdf(tmp_path)
                method = "llava_vision_pdf"
        else:
            # Other files: use LLaVA
            result = await call_llava_vision_direct(tmp_path)
            method = "llava_vision_direct"
        
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

async def call_llava_vision_pdf(file_path: str) -> Dict[str, Any]:
    """Call LLaVA vision model for PDF files with PDF-to-image conversion"""
    try:
        # Convert PDF to image first
        from pdf2image import convert_from_path
        import io
        
        logger.info("Converting PDF to image for LLaVA processing...")
        images = convert_from_path(file_path, first_page=1, last_page=1)
        img = images[0]
        
        # Convert to base64
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        image_data = base64.b64encode(buf.getvalue()).decode('utf-8')
        
        logger.info(f"PDF converted to image, base64 length: {len(image_data)}")
        
        # Very specific prompt for Portuguese/Italian medical documents
        prompt = """Look at this medical document image and extract the biometry data.

CRITICAL: This is a Portuguese/Italian medical document. Look for patient information using these specific terms:
- "Paciente:" or "Paziente:" or "Patient:" or "Nome:" or "Name:"
- "Data de nascim." or "Data di nascita" or "Birth date" or "Date of birth"
- "Idade:" or "Età:" or "Age:" 
- Look for birth dates like "17/12/1943" and calculate age

For biometry measurements, look for:
- OD (right eye) and OS (left eye) measurements
- AL (Axial Length), K1, K2 values with axis information
- ACD (Anterior Chamber Depth), LT (Lens Thickness), WTW (White-to-White), CCT (Central Corneal Thickness)

Return ONLY valid JSON in this exact format:
{
  "patient_name": "extract the actual patient name from the document",
  "age": extract_the_actual_age_number,
  "od": {"axial_length": number, "k1": number, "k2": number, "k_axis_1": number, "k_axis_2": number, "acd": number, "lt": number, "wtw": number, "cct": number},
  "os": {"axial_length": number, "k1": number, "k2": number, "k_axis_1": number, "k_axis_2": number, "acd": number, "lt": number, "wtw": number, "cct": number}
}

IMPORTANT: 
- Look for "Paciente:" followed by the patient name
- Look for "Data de nascim." followed by birth date and calculate age
- Extract the REAL patient name from the document, not examples
- Extract the REAL age from the document, not examples
- If you cannot find patient name or age, use null"""

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
        
        # Log the full response for debugging
        logger.info(f"LLaVA full response: {response_text}")
        
        # Parse JSON response - handle markdown formatting
        try:
            # Remove markdown formatting if present
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                if json_end > json_start:
                    json_str = response_text[json_start:json_end].strip()
                else:
                    raise ValueError("No closing ``` found")
            else:
                json_start = response_text.find('{')
                json_end = response_text.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = response_text[json_start:json_end]
                else:
                    raise ValueError("No valid JSON found in response")
            
            extracted_data = json.loads(json_str)
            
            # Calculate confidence based on data completeness
            confidence = calculate_confidence(extracted_data)
            
            return {
                "success": True,
                "extracted_data": extracted_data,
                "confidence": confidence
            }
            
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"JSON parsing error: {str(e)}")
            return {
                "success": False,
                "extracted_data": {},
                "confidence": 0.0,
                "error": f"Failed to parse JSON: {str(e)}"
            }
        
    except Exception as e:
        logger.error(f"LLaVA vision PDF API error: {str(e)}")
        return {
            "success": False,
            "extracted_data": {},
            "confidence": 0.0,
            "error": str(e)
        }

async def call_llava_vision_direct(file_path: str) -> Dict[str, Any]:
    """Call LLaVA vision model for direct image files"""
    try:
        # Convert file to base64
        with open(file_path, "rb") as image_file:
            image_data = base64.b64encode(image_file.read()).decode('utf-8')
        
        # Very specific prompt for Portuguese/Italian medical documents
        prompt = """Look at this medical document image and extract the biometry data.

CRITICAL: This is a Portuguese/Italian medical document. Look for patient information using these specific terms:
- "Paciente:" or "Paziente:" or "Patient:" or "Nome:" or "Name:"
- "Data de nascim." or "Data di nascita" or "Birth date" or "Date of birth"
- "Idade:" or "Età:" or "Age:" 
- Look for birth dates like "17/12/1943" and calculate age

For biometry measurements, look for:
- OD (right eye) and OS (left eye) measurements
- AL (Axial Length), K1, K2 values with axis information
- ACD (Anterior Chamber Depth), LT (Lens Thickness), WTW (White-to-White), CCT (Central Corneal Thickness)

Return ONLY valid JSON in this exact format:
{
  "patient_name": "extract the actual patient name from the document",
  "age": extract_the_actual_age_number,
  "od": {"axial_length": number, "k1": number, "k2": number, "k_axis_1": number, "k_axis_2": number, "acd": number, "lt": number, "wtw": number, "cct": number},
  "os": {"axial_length": number, "k1": number, "k2": number, "k_axis_1": number, "k_axis_2": number, "acd": number, "lt": number, "wtw": number, "cct": number}
}

IMPORTANT: 
- Look for "Paciente:" followed by the patient name
- Look for "Data de nascim." followed by birth date and calculate age
- Extract the REAL patient name from the document, not examples
- Extract the REAL age from the document, not examples
- If you cannot find patient name or age, use null"""

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
        
        # Log the full response for debugging
        logger.info(f"LLaVA full response: {response_text}")
        
        # Parse JSON response - handle markdown formatting
        try:
            # Remove markdown formatting if present
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                if json_end > json_start:
                    json_str = response_text[json_start:json_end].strip()
                else:
                    raise ValueError("No closing ``` found")
            else:
                json_start = response_text.find('{')
                json_end = response_text.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = response_text[json_start:json_end]
                else:
                    raise ValueError("No valid JSON found in response")
            
            extracted_data = json.loads(json_str)
            
            # Calculate confidence based on data completeness
            confidence = calculate_confidence(extracted_data)
            
            return {
                "success": True,
                "extracted_data": extracted_data,
                "confidence": confidence
            }
            
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"JSON parsing error: {str(e)}")
            return {
                "success": False,
                "extracted_data": {},
                "confidence": 0.0,
                "error": f"Failed to parse JSON: {str(e)}"
            }
        
    except Exception as e:
        logger.error(f"LLaVA vision direct API error: {str(e)}")
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
    for field in ["axial_length", "k1", "k2", "k_axis_1", "k_axis_2", "acd", "lt", "wtw", "cct"]:
        if od_data.get(field):
            filled_fields += 1
        total_fields += 1
    
    # Check OS data
    os_data = data.get("os", {})
    for field in ["axial_length", "k1", "k2", "k_axis_1", "k_axis_2", "acd", "lt", "wtw", "cct"]:
        if os_data.get(field):
            filled_fields += 1
        total_fields += 1
    
    return filled_fields / total_fields if total_fields > 0 else 0.0

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003, log_level="info")
