#!/usr/bin/env python3

import os
import json
import base64
import requests
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from pdf2image import convert_from_path
import PyPDF2
import io
import pytesseract
from PIL import Image
import re

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# RunPod LLaVA endpoint
LLAVA_ENDPOINT = "http://127.0.0.1:11434/api/generate"

def extract_patient_info_with_ocr(image_path):
    """Extract patient name and age using OCR with simple regex patterns"""
    try:
        # Use pytesseract to extract text
        text = pytesseract.image_to_string(Image.open(image_path))
        print(f"DEBUG: OCR extracted text: {text[:300]}...")
        
        # Extract patient name using simple patterns
        patient_name = None
        name_patterns = [
            r'PATIENT[:\s]+([A-Z\s,]+)',
            r'NAME[:\s]+([A-Z\s,]+)',
            r'NOME[:\s]+([A-Z\s,]+)',
            r'([A-Z]+,?\s+[A-Z]+(?:\s+[A-Z]+)*)',  # Simple name pattern
        ]
        
        for pattern in name_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                patient_name = match.group(1).strip()
                # Clean up the name
                patient_name = re.sub(r'[^\w\s,]', '', patient_name)
                if len(patient_name) > 3:  # Basic validation
                    break
        
        # Extract age using improved patterns
        age = None
        age_patterns = [
            r'AGE[:\s]+(\d+)',
            r'ETÀ[:\s]+(\d+)',
            r'(\d+)\s*YEARS?',
            r'(\d+)\s*ANOS?',
            r'BIRTH[:\s]+(\d{4})',  # Birth year
            r'(\d{1,2})/(\d{1,2})/(\d{4})',  # Date format DD/MM/YYYY
            r'(\d{4})-(\d{1,2})-(\d{1,2})',  # Date format YYYY-MM-DD
        ]
        
        for pattern in age_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if 'BIRTH' in pattern.upper():
                    # Calculate age from birth year
                    birth_year = int(match.group(1))
                    age = 2024 - birth_year
                elif '/' in pattern or '-' in pattern:
                    # Date format - calculate age from birth date
                    if '/' in pattern:  # DD/MM/YYYY
                        day, month, year = match.groups()
                        birth_year = int(year)
                        age = 2024 - birth_year
                    else:  # YYYY-MM-DD
                        year, month, day = match.groups()
                        birth_year = int(year)
                        age = 2024 - birth_year
                else:
                    age = int(match.group(1))
                
                # Validate age is reasonable (18-100)
                if age and 18 <= age <= 100:
                    break
                else:
                    age = None
        
        print(f"DEBUG: OCR extracted - Name: {patient_name}, Age: {age}")
        return patient_name, age, text
        
    except Exception as e:
        print(f"Error with OCR: {e}")
        return None, None, ""

def call_llava_biometry_only(text_content):
    """Call LLaVA model for biometry data only (no patient info)"""
    
    prompt = f"""Extract ONLY biometry measurements from this text in JSON format:

{text_content}

Return ONLY valid JSON with biometry data:
- od (object with: axial_length, k1, k2, k_axis_1, k_axis_2, acd, lt, wtw, cct)
- os (object with: axial_length, k1, k2, k_axis_1, k_axis_2, acd, lt, wtw, cct)

Example format:
{{
  "od": {{"axial_length": 23.5, "k1": 42.0, "k2": 43.5, "k_axis_1": 90, "k_axis_2": 0, "acd": 3.0, "lt": 4.5, "wtw": 11.0, "cct": 550}},
  "os": {{"axial_length": 23.7, "k1": 41.8, "k2": 43.2, "k_axis_1": 85, "k_axis_2": 175, "acd": 2.9, "lt": 4.6, "wtw": 11.2, "cct": 545}}
}}"""

    payload = {
        "model": "llava:latest",
        "prompt": prompt,
        "stream": False
    }
    
    try:
        response = requests.post(LLAVA_ENDPOINT, json=payload, timeout=60)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error calling LLaVA: {e}")
        return {"error": str(e)}

def call_llama_text(text_content):
    """Call Llama 7B for text-based PDFs"""
    
    prompt = f"""Extract biometry data from this text in JSON format:

{text_content}

Return ONLY valid JSON with:
- patient_name (string)
- age (number)
- od (object with: axial_length, k1, k2, k_axis_1, k_axis_2, acd, lt, wtw, cct)
- os (object with: axial_length, k1, k2, k_axis_1, k_axis_2, acd, lt, wtw, cct)

Example format:
{{
  "patient_name": "John Doe",
  "age": 65,
  "od": {{"axial_length": 23.5, "k1": 42.0, "k2": 43.5, "k_axis_1": 90, "k_axis_2": 0, "acd": 3.0, "lt": 4.5, "wtw": 11.0, "cct": 550}},
  "os": {{"axial_length": 23.7, "k1": 41.8, "k2": 43.2, "k_axis_1": 85, "k_axis_2": 175, "acd": 2.9, "lt": 4.6, "wtw": 11.2, "cct": 545}}
}}"""

    payload = {
        "model": "llama3.1:8b",
        "prompt": prompt,
        "stream": False
    }
    
    try:
        response = requests.post("http://127.0.0.1:11434/api/generate", json=payload, timeout=60)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error calling Llama: {e}")
        return {"error": str(e)}

def is_text_based_pdf(pdf_path):
    """Check if PDF contains extractable text"""
    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            text_content = ""
            for page in pdf_reader.pages:
                text_content += page.extract_text()
            return len(text_content.strip()) > 100  # If we have substantial text
    except Exception as e:
        print(f"Error checking PDF text: {e}")
        return False

@app.post("/parse")
async def parse_document(file: UploadFile = File(...)):
    try:
        # Save uploaded file
        file_path = f"temp_{file.filename}"
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        print(f"Processing file: {file.filename}")
        
        # Check if it's a text-based PDF
        if file.filename.lower().endswith('.pdf'):
            if is_text_based_pdf(file_path):
                print("Text-based PDF detected, using Llama 7B")
                # Extract text and use Llama
                with open(file_path, 'rb') as f:
                    pdf_reader = PyPDF2.PdfReader(f)
                    text_content = ""
                    for page in pdf_reader.pages:
                        text_content += page.extract_text()
                
                result = call_llama_text(text_content)
            else:
                print("Image-based PDF detected, using hybrid OCR + LLaVA")
                # Convert PDF to image
                images = convert_from_path(file_path, first_page=1, last_page=1)
                if images:
                    image_path = f"temp_image_{file.filename}.png"
                    images[0].save(image_path, 'PNG')
                    
                    # Step 1: Extract patient info with OCR
                    patient_name, age, ocr_text = extract_patient_info_with_ocr(image_path)
                    
                    # Step 2: Extract biometry data with LLaVA
                    llava_result = call_llava_biometry_only(ocr_text)
                    
                    # Step 3: Combine results
                    if "error" not in llava_result:
                        # Parse LLaVA response
                        llava_response = llava_result.get("response", "")
                        print(f"DEBUG: LLaVA response: {llava_response[:500]}...")
                        
                        try:
                            # Try multiple JSON extraction methods
                            biometry_json = None
                            
                            # Method 1: Look for JSON between curly braces
                            json_start = llava_response.find('{')
                            json_end = llava_response.rfind('}') + 1
                            if json_start != -1 and json_end != -1:
                                json_str = llava_response[json_start:json_end]
                                # Fix escaped underscores
                                json_str = json_str.replace('\\_', '_')
                                biometry_json = json.loads(json_str)
                            
                            # Method 2: Look for JSON in code blocks
                            if not biometry_json:
                                import re
                                json_match = re.search(r'```json\s*(\{.*?\})\s*```', llava_response, re.DOTALL)
                                if json_match:
                                    json_str = json_match.group(1)
                                    json_str = json_str.replace('\\_', '_')
                                    biometry_json = json.loads(json_str)
                            
                            # Method 3: Look for JSON without code blocks
                            if not biometry_json:
                                json_match = re.search(r'(\{.*?\})', llava_response, re.DOTALL)
                                if json_match:
                                    json_str = json_match.group(1)
                                    json_str = json_str.replace('\\_', '_')
                                    biometry_json = json.loads(json_str)
                            
                            if biometry_json:
                                # Add patient info
                                biometry_json["patient_name"] = patient_name or "Not found"
                                biometry_json["age"] = age or "Not found"
                                
                                result = {"response": json.dumps(biometry_json)}
                            else:
                                result = {"error": f"Could not extract JSON from LLaVA response: {llava_response[:200]}"}
                                
                        except json.JSONDecodeError as e:
                            result = {"error": f"Invalid JSON from LLaVA: {str(e)}. Response: {llava_response[:200]}"}
                    else:
                        result = llava_result
                    
                    os.remove(image_path)
                else:
                    return {"error": "Failed to convert PDF to image"}
        else:
            # For non-PDF files, assume text content
            content = await file.read()
            text_content = content.decode('utf-8')
            result = call_llama_text(text_content)
        
        # Clean up
        os.remove(file_path)
        
        return result
        
    except Exception as e:
        return {"error": str(e)}

@app.get("/")
async def root():
    return {"message": "LakeCalc AI Parser API - Hybrid OCR + LLaVA Version"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8003)
