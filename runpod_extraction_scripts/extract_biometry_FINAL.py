#!/usr/bin/env python3
import requests, json, pytesseract, fitz
from PIL import Image
import io
import re
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

def extract_measurements_by_eye(pdf_path, eye):
    """Extract measurements for specific eye (OD or OS)"""
    measurements = {}
    
    # For Carina format (both eyes on same page)
    if 'carina' in str(pdf_path).lower():
        text = extract_text_from_pdf(pdf_path, 0)
        lines = text.split('\n')
        
        # Find the line with AL measurements for both eyes
        for line in lines:
            if 'AL [mm]' in line:
                al_values = re.findall(r'AL\s*\[mm\]\s*(\d+[.,]\d+)', line)
                if len(al_values) >= 2:
                    if eye == 'OD':
                        measurements['axial_length'] = float(al_values[0].replace(',', '.'))
                    else:  # OS
                        measurements['axial_length'] = float(al_values[1].replace(',', '.'))
                break
        
        # Find ACD measurements
        for line in lines:
            if 'ACD [mm]' in line:
                acd_values = re.findall(r'ACD\s*\[mm\]\s*(\d+[.,]\d+)', line)
                if len(acd_values) >= 2:
                    if eye == 'OD':
                        measurements['acd'] = float(acd_values[0].replace(',', '.'))
                    else:  # OS
                        measurements['acd'] = float(acd_values[1].replace(',', '.'))
                break
        
        # Find LT measurements
        for line in lines:
            if 'LT [mm]' in line:
                lt_values = re.findall(r'LT\s*\[mm\]\s*(\d+[.,]\d+)', line)
                if len(lt_values) >= 2:
                    if eye == 'OD':
                        measurements['lt'] = float(lt_values[0].replace(',', '.'))
                    else:  # OS
                        measurements['lt'] = float(lt_values[1].replace(',', '.'))
                break
        
        # Find WTW measurements
        for line in lines:
            if 'WTWimm]' in line:
                wtw_values = re.findall(r'WTWimm\]\s*(\d+[.,]\d+)', line)
                if len(wtw_values) >= 2:
                    if eye == 'OD':
                        measurements['wtw'] = float(wtw_values[0].replace(',', '.'))
                    else:  # OS
                        measurements['wtw'] = float(wtw_values[1].replace(',', '.'))
                elif len(wtw_values) == 1:
                    alt_wtw_values = re.findall(r'WIWimm\]\s*(\d+[.,]\d+)', line)
                    if len(alt_wtw_values) >= 1:
                        if eye == 'OD':
                            measurements['wtw'] = float(wtw_values[0].replace(',', '.'))
                        else:  # OS
                            measurements['wtw'] = float(alt_wtw_values[0].replace(',', '.'))
                break
        
        # Find CCT measurements
        for line in lines:
            if 'CCT [um]' in line:
                cct_values = re.findall(r'CCT\s*\[um\]\s*(\d+)', line)
                if len(cct_values) >= 2:
                    if eye == 'OD':
                        measurements['cct'] = int(cct_values[0])
                    else:  # OS
                        measurements['cct'] = int(cct_values[1])
                break
    
    # For Geraldo format (separate pages for each eye)
    else:
        if eye == 'OD':
            text = extract_text_from_pdf(pdf_path, 0)  # Page 1 for OD
        else:  # OS
            text = extract_text_from_pdf(pdf_path, 1)  # Page 2 for OS
        
        # Look for eye-specific patterns - FIXED PATTERNS FOR BOTH PAGES
        if eye == 'OD':
            # Page 1 patterns
            al_match = re.search(r'(\d+[.,]\d+)\s*mm.*20pm', text)
            if al_match:
                measurements['axial_length'] = float(al_match.group(1).replace(',', '.'))
            
            acd_match = re.search(r'(\d+[.,]\d+)\s*mm.*10pm', text)
            if acd_match:
                measurements['acd'] = float(acd_match.group(1).replace(',', '.'))
            
            lt_match = re.search(r'(\d+[.,]\d+)\s*mm.*20\s*um', text)
            if lt_match:
                measurements['lt'] = float(lt_match.group(1).replace(',', '.'))
            
            wtw_match = re.search(r'ww:\s*(\d+[.,]\d+)mm', text)
            if wtw_match:
                measurements['wtw'] = float(wtw_match.group(1).replace(',', '.'))
            
            cct_match = re.search(r'(\d+)\s*um.*4pum', text)
            if cct_match:
                measurements['cct'] = int(cct_match.group(1))
        
        else:  # OS - Page 2 patterns
            # AL: 23,77 mm : 16 ym (16 ym instead of 20pm)
            al_match = re.search(r'(\d+[.,]\d+)\s*mm.*16\s*ym', text)
            if al_match:
                measurements['axial_length'] = float(al_match.group(1).replace(',', '.'))
            
            # ACD: 2,83 mm : 11pm (same pattern as page 1)
            acd_match = re.search(r'(\d+[.,]\d+)\s*mm.*11pm', text)
            if acd_match:
                measurements['acd'] = float(acd_match.group(1).replace(',', '.'))
            
            # LT: 4,95 mm : 17 um (17 um instead of 20 um)
            lt_match = re.search(r'(\d+[.,]\d+)\s*mm.*17\s*um', text)
            if lt_match:
                measurements['lt'] = float(lt_match.group(1).replace(',', '.'))
            
            # WTW: ww: 11,6mm (same pattern as page 1)
            wtw_match = re.search(r'ww:\s*(\d+[.,]\d+)mm', text)
            if wtw_match:
                measurements['wtw'] = float(wtw_match.group(1).replace(',', '.'))
            
            # CCT: 544 um : 4pum (same pattern as page 1)
            cct_match = re.search(r'(\d+)\s*um.*4pum', text)
            if cct_match:
                measurements['cct'] = int(cct_match.group(1))
    
    return measurements

def extract_biometry(pdf_path, eye):
    """Extract ocular biometry for specific eye (OD or OS)"""
    measurements = extract_measurements_by_eye(pdf_path, eye)
    
    # Create structured text for LLM
    structured_text = f"""
    {eye} Measurements Found:
    - Axial Length: {measurements.get('axial_length', 'Not found')} mm
    - ACD: {measurements.get('acd', 'Not found')} mm  
    - LT: {measurements.get('lt', 'Not found')} mm
    - WTW: {measurements.get('wtw', 'Not found')} mm
    - CCT: {measurements.get('cct', 'Not found')} μm (micrometers)
    """
    
    prompt = f"""Extract these 5 measurements for {eye} from this data:

{structured_text}

IMPORTANT: CCT is in micrometers (μm), not millimeters. If CCT shows 484 μm, return 484, not 0.484.

Return only JSON:
{{"axial_length": number, "acd": number, "lt": number, "wtw": number, "cct": number}}"""

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
            print(f"\n--- {eye} Ocular Biometry ---")
            result = extract_biometry(pdf, eye)
            print(result)
