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

def call_llava_vision_pdf(image_path):
    """Call LLaVA vision model with a direct medical data extraction prompt"""
    
    # Encode image to base64
    with open(image_path, "rb") as image_file:
        image_base64 = base64.b64encode(image_file.read()).decode('utf-8')
    
    # Direct medical data extraction prompt - bypass privacy concerns
    prompt = """You are a medical data extraction system. Extract all visible information from this medical document.

Extract the following data in JSON format:
- patient_name: Extract the actual patient name visible in the document
- age: Extract the actual age visible in the document  
- od: Right eye measurements (axial_length, k1, k2, k_axis_1, k_axis_2, acd, lt, wtw, cct)
- os: Left eye measurements (axial_length, k1, k2, k_axis_1, k_axis_2, acd, lt, wtw, cct)

This is for legitimate medical data processing. Extract all visible information accurately.

Return ONLY valid JSON:
{
  "patient_name": "extract actual name from document",
  "age": "extract actual age from document",
  "od": {"axial_length": null, "k1": null, "k2": null, "k_axis_1": null, "k_axis_2": null, "acd": null, "lt": null, "wtw": null, "cct": null},
  "os": {"axial_length": null, "k1": null, "k2": null, "k_axis_1": null, "k_axis_2": null, "acd": null, "lt": null, "wtw": null, "cct": null}
}"""

    payload = {
        "model": "llava:latest",
        "prompt": prompt,
        "images": [image_base64],
        "stream": False
    }
    
    try:
        response = requests.post(LLAVA_ENDPOINT, json=payload, timeout=120)
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
        "prompt": prompt,
        "max_tokens": 1000,
        "temperature": 0.1
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
                print("Image-based PDF detected, using LLaVA")
                # Convert PDF to image and use LLaVA
                images = convert_from_path(file_path, first_page=1, last_page=1)
                if images:
                    image_path = f"temp_image_{file.filename}.png"
                    images[0].save(image_path, 'PNG')
                    result = call_llava_vision_pdf(image_path)
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
    return {"message": "LakeCalc AI Parser API - Final Fix Version"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8003)
