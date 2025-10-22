#!/usr/bin/env python3
"""
RunPod LLM API Service for LakeCalc-AI
Dedicated LLM processing service for biometry parsing
"""

import os
import json
import logging
import asyncio
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="LakeCalc-AI LLM API",
    description="Dedicated LLM processing service for biometry parsing",
    version="1.0.0"
)

class BiometryParseRequest(BaseModel):
    text: str
    device_type: Optional[str] = None
    confidence_threshold: float = 0.8

class BiometryParseResponse(BaseModel):
    success: bool
    extracted_data: Dict[str, Any]
    confidence: float
    processing_time: float
    method: str
    error: Optional[str] = None

class HealthResponse(BaseModel):
    status: str
    ollama_available: bool
    models_loaded: list
    timestamp: str

# Ollama configuration
OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3.1:8b"
FALLBACK_MODEL = "mistral:7b"

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Check service health and Ollama availability"""
    try:
        # Check Ollama status
        ollama_response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        ollama_available = ollama_response.status_code == 200
        
        models_loaded = []
        if ollama_available:
            models_data = ollama_response.json()
            models_loaded = [model["name"] for model in models_data.get("models", [])]
        
        return HealthResponse(
            status="healthy" if ollama_available else "unhealthy",
            ollama_available=ollama_available,
            models_loaded=models_loaded,
            timestamp=datetime.now().isoformat()
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return HealthResponse(
            status="unhealthy",
            ollama_available=False,
            models_loaded=[],
            timestamp=datetime.now().isoformat()
        )

@app.post("/parse", response_model=BiometryParseResponse)
async def parse_biometry(request: BiometryParseRequest):
    """Parse biometry text using LLM"""
    start_time = datetime.now()
    
    try:
        logger.info(f"Starting biometry parsing with model: {DEFAULT_MODEL}")
        
        # Build the prompt for biometry extraction
        prompt = build_biometry_prompt(request.text)
        
        # Try primary model first
        result = await call_ollama(DEFAULT_MODEL, prompt)
        
        if not result or result.get("confidence", 0) < request.confidence_threshold:
            logger.info(f"Primary model confidence too low, trying fallback: {FALLBACK_MODEL}")
            result = await call_ollama(FALLBACK_MODEL, prompt)
        
        if not result:
            raise HTTPException(status_code=500, detail="LLM processing failed")
        
        processing_time = (datetime.now() - start_time).total_seconds()
        
        return BiometryParseResponse(
            success=True,
            extracted_data=result.get("data", {}),
            confidence=result.get("confidence", 0.0),
            processing_time=processing_time,
            method="llm"
        )
        
    except Exception as e:
        logger.error(f"Biometry parsing failed: {e}")
        processing_time = (datetime.now() - start_time).total_seconds()
        
        return BiometryParseResponse(
            success=False,
            extracted_data={},
            confidence=0.0,
            processing_time=processing_time,
            method="llm",
            error=str(e)
        )

def build_biometry_prompt(text: str) -> str:
    """Build optimized prompt for biometry extraction"""
    return f"""You are a medical AI assistant specialized in extracting biometry data from ophthalmology reports.

Extract the following biometry measurements from the text below. Return ONLY valid JSON with the exact field names shown:

{{
  "patient_name": "Patient Name",
  "birth_date": "MM/DD/YYYY",
  "age": 75,
  "od": {{
    "axial_length": 25.25,
    "k1": 42.60,
    "k2": 43.52,
    "k_axis_1": 14,
    "k_axis_2": 104,
    "acd": 3.25,
    "lt": 4.50,
    "wtw": 12.25,
    "cct": 540
  }},
  "os": {{
    "axial_length": 24.85,
    "k1": 43.10,
    "k2": 44.25,
    "k_axis_1": 165,
    "k_axis_2": 75,
    "acd": 3.15,
    "lt": 4.65,
    "wtw": 12.30,
    "cct": 535
  }}
}}

Rules:
- Return ONLY the JSON object, no explanations
- Use null for missing values
- Ensure all numbers are properly formatted
- Extract both OD (right eye) and OS (left eye) data when available
- Patient name should be extracted if visible
- Calculate age from birth date if available

Text to analyze:
{text[:2000]}

JSON:"""

async def call_ollama(model: str, prompt: str) -> Optional[Dict[str, Any]]:
    """Call Ollama API with the given model and prompt"""
    try:
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "top_p": 0.9,
                "max_tokens": 1000
            }
        }
        
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json=payload,
            timeout=60
        )
        
        if response.status_code != 200:
            logger.error(f"Ollama API error: {response.status_code} - {response.text}")
            return None
        
        result = response.json()
        response_text = result.get("response", "").strip()
        
        # Try to extract JSON from response
        try:
            # Find JSON in the response
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            
            if start_idx != -1 and end_idx > start_idx:
                json_text = response_text[start_idx:end_idx]
                data = json.loads(json_text)
                
                # Calculate confidence based on data completeness
                confidence = calculate_confidence(data)
                
                return {
                    "data": data,
                    "confidence": confidence,
                    "raw_response": response_text
                }
            else:
                logger.error("No valid JSON found in response")
                return None
                
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            logger.error(f"Raw response: {response_text}")
            return None
            
    except Exception as e:
        logger.error(f"Ollama call failed: {e}")
        return None

def calculate_confidence(data: Dict[str, Any]) -> float:
    """Calculate confidence score based on data completeness"""
    if not isinstance(data, dict):
        return 0.0
    
    # Key fields to check
    key_fields = ["od", "os"]
    od_fields = ["axial_length", "k1", "k2"]
    os_fields = ["axial_length", "k1", "k2"]
    
    total_fields = 0
    filled_fields = 0
    
    # Check OD data
    if "od" in data and isinstance(data["od"], dict):
        for field in od_fields:
            total_fields += 1
            if data["od"].get(field) is not None:
                filled_fields += 1
    
    # Check OS data
    if "os" in data and isinstance(data["os"], dict):
        for field in os_fields:
            total_fields += 1
            if data["os"].get(field) is not None:
                filled_fields += 1
    
    # Check patient data
    patient_fields = ["patient_name", "age"]
    for field in patient_fields:
        total_fields += 1
        if data.get(field) is not None:
            filled_fields += 1
    
    if total_fields == 0:
        return 0.0
    
    return filled_fields / total_fields

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")
