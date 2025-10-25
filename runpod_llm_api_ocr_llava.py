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

def call_llava_text(text_content):
    """Call LLaVA model with TEXT input (bypasses vision privacy issues)"""
    
    print(f"DEBUG: Using LLaVA with OCR text: {text_content[:200]}...")
    
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

def extract_text_with_ocr(image_path):
    """Extract text from image using OCR"""
    try:
        # Use pytesseract to extract text
        text = pytesseract.image_to_string(Image.open(image_path))
        print(f"DEBUG: OCR extracted text: {text[:200]}...")
        return text
    except Exception as e:
        print(f"Error with OCR: {e}")
        return ""

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
                print("Image-based PDF detected, using OCR + LLaVA")
                # Convert PDF to image and use OCR + LLaVA
                images = convert_from_path(file_path, first_page=1, last_page=1)
                if images:
                    image_path = f"temp_image_{file.filename}.png"
                    images[0].save(image_path, 'PNG')
                    
                    # Extract text using OCR
                    ocr_text = extract_text_with_ocr(image_path)
                    
                    # Use LLaVA with the OCR text (bypasses vision privacy issues)
                    result = call_llava_text(ocr_text)
                    
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
    return {"message": "LakeCalc AI Parser API - OCR + LLaVA Version"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8003)
