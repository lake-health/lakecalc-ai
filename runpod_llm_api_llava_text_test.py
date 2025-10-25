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

def call_llava_text(text_content):
    """Call LLaVA model with TEXT input (not image) to test privacy behavior"""
    
    print(f"DEBUG: Testing LLaVA with text content: {text_content[:200]}...")
    
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

@app.post("/parse")
async def parse_document(file: UploadFile = File(...)):
    try:
        # Save uploaded file
        file_path = f"temp_{file.filename}"
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        print(f"Processing file: {file.filename}")
        
        # For text files, use LLaVA with text input
        if file.filename.lower().endswith('.txt'):
            print("Text file detected, using LLaVA with text input")
            with open(file_path, 'r', encoding='utf-8') as f:
                text_content = f.read()
            
            result = call_llava_text(text_content)
        else:
            return {"error": "Only text files supported in this test version"}
        
        # Clean up
        os.remove(file_path)
        
        return result
        
    except Exception as e:
        return {"error": str(e)}

@app.get("/")
async def root():
    return {"message": "LakeCalc AI Parser API - LLaVA Text Test Version"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8003)
