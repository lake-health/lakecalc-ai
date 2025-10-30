#!/usr/bin/env python3
import requests, json, pytesseract, fitz
from PIL import Image
import io
from pathlib import Path

def extract_text_from_pdf(pdf_path, page_num=0):
    """Extract text from specific PDF page using OCR"""
    doc = fitz.open(pdf_path)
    if page_num < len(doc):
        page = doc.load_page(page_num)
        mat = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=mat)
        img_data = pix.tobytes("png")
        doc.close()
        
        image = Image.open(io.BytesIO(img_data))
        text = pytesseract.image_to_string(image)
        return text
    else:
        doc.close()
        return ""

def extract_keratometry(pdf_path, eye):
    """Extract keratometry for specific eye (OD or OS)"""
    
    # Determine which page to read based on filename pattern
    if 'carina' in str(pdf_path).lower():
        # Carina: both eyes on page 0
        text = extract_text_from_pdf(pdf_path, 0)
    else:
        # Geraldo: OD on page 0, OS on page 1
        if eye == 'OD':
            text = extract_text_from_pdf(pdf_path, 0)
        else:  # OS
            text = extract_text_from_pdf(pdf_path, 1)
    
    prompt = f"""Extract keratometry data for {eye} ({"right" if eye == "OD" else "left"} eye) from this medical document:

{text}

Extract:
- k1 (first keratometry value in diopters)
- k2 (second keratometry value in diopters)  
- k_axis_1 (axis for K1, 0-180 degrees)
- k_axis_2 (axis for K2, 0-180 degrees)

Look for patterns like "K1: 42.30 D @ 100°" or "K1: 42,30 D @ 100°"
Map K1 axis to k_axis_1 and K2 axis to k_axis_2

Return only valid JSON:
{{"k1": number, "k2": number, "k_axis_1": number, "k_axis_2": number}}"""

    resp = requests.post('http://127.0.0.1:11434/api/generate',
                        json={'model': 'biometry-llama', 'prompt': prompt, 'stream': False})
    
    if resp.status_code == 200:
        return resp.json().get('response', '')
    return None

if __name__ == "__main__":
    pdf_dir = Path('/workspace/lora_training/data/')
    for pdf in pdf_dir.glob('*.pdf'):
        print(f"\n=== {pdf.name} ===")
        
        # Test both eyes
        for eye in ["OD", "OS"]:
            print(f"\n--- {eye} Keratometry ---")
            result = extract_keratometry(pdf, eye)
            print(result)
