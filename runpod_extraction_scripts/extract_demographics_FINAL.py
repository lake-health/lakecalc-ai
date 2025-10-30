#!/usr/bin/env python3
import requests, json, pytesseract, fitz
from PIL import Image
import io
from pathlib import Path

def extract_text_from_pdf(pdf_path):
    """Extract text from PDF using OCR"""
    doc = fitz.open(pdf_path)
    page = doc.load_page(0)
    mat = fitz.Matrix(2.0, 2.0)
    pix = page.get_pixmap(matrix=mat)
    img_data = pix.tobytes("png")
    doc.close()
    
    image = Image.open(io.BytesIO(img_data))
    text = pytesseract.image_to_string(image)
    return text

def extract_demographics(pdf_path):
    """Extract demographics using OCR + Llama"""
    text = extract_text_from_pdf(pdf_path)
    
    prompt = f"""Extract patient demographics from this medical document text:

{text}

Extract:
- patient_name (full name)
- age (calculate from birth date)
- device (measurement device/manufacturer like ZEISS, IOLMaster, etc.)

Return only valid JSON:
{{"patient_name": "string", "age": number, "device": "string"}}"""

    resp = requests.post('http://127.0.0.1:11434/api/generate',
                        json={'model': 'llama3.1:8b', 'prompt': prompt, 'stream': False})
    
    if resp.status_code == 200:
        return resp.json().get('response', '')
    return None

if __name__ == "__main__":
    pdf_dir = Path('/workspace/lora_training/data/')
    for pdf in pdf_dir.glob('*.pdf'):
        print(f"\n=== {pdf.name} ===")
        result = extract_demographics(pdf)
        print(result)
