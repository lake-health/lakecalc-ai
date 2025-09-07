from flask import Flask, jsonify, request, render_template
from google.cloud import vision
import os
import io
import re
from pdf2image import convert_from_bytes

# Initialize Flask App
app = Flask(__name__, static_folder='static', template_folder='templates')

# --- Google Cloud Vision Client Setup ---
client = None
try:
    credentials_json_str = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
    if credentials_json_str:
        from google.oauth2 import service_account
        import json
        credentials_info = json.loads(credentials_json_str)
        credentials = service_account.Credentials.from_service_account_info(credentials_info)
        client = vision.ImageAnnotatorClient(credentials=credentials)
    else:
        print("WARNING: GOOGLE_APPLICATION_CREDENTIALS_JSON not set. OCR may not function.")
except Exception as e:
    print(f"Error initializing Google Cloud Vision client: {e}")

# --- Core OCR Function ---
def perform_ocr(image_content):
    if not client:
        raise Exception("Google Cloud Vision client is not initialized.")
    image = vision.Image(content=image_content)
    response = client.text_detection(image=image)
    if response.error.message:
        raise Exception(f"Vision API Error: {response.error.message}")
    return response.text_annotations[0].description if response.text_annotations else ""

# --- PARSER IMPLEMENTATIONS ---

def parse_iol_master_700(text):
    """
    Parses the text extracted from a ZEISS IOLMaster 700 report with improved
    accuracy for columnar data.
    """
    data = {"OD": {"source": "IOL Master 700"}, "OS": {"source": "IOL Master 700"}}
    
    def find_in_section(patterns, section_text):
        """Helper to find multiple patterns within a specific text block."""
        results = {}
        for key, pattern in patterns.items():
            matches = re.findall(pattern, section_text, re.MULTILINE)
            if matches:
                cleaned_match = matches[0].strip().replace(',', '.').replace('\n', ' ')
                results[key] = ' '.join(cleaned_match.split())
        return results

    # Isolate the main biometry data blocks for each eye
    od_biometry_match = re.search(r'OD\s*direita.*?Valores biométricos(.*?)(?=Cálculo IOL|ZEISS IOLMaster 700)', text, re.DOTALL)
    os_biometry_match = re.search(r'OS\s*esquerda.*?Valores biométricos(.*?)(?=Cálculo IOL|ZEISS IOLMaster 700)', text, re.DOTALL)

    od_text = od_biometry_match.group(1) if od_biometry_match else ""
    os_text = os_biometry_match.group(1) if os_biometry_match else ""

    # Define patterns for the values
    patterns = {
        "axial_length": r"AL:\s*([\d,.]+\s*mm)",
        "acd": r"ACD:\s*([\d,.]+\s*mm)",
        "lt": r"LT:\s*([\d,.]+\s*mm)",
        "cct": r"CCT:\s*([\d,.]+\s*μm)",
        "wtw": r"WTW:\s*([\d,.]+\s*mm)",
        "k1": r"K1:\s*([\d,.]+\s*D\s*@\s*\d+°)",
        "k2": r"K2:\s*([\d,.]+\s*D\s*@\s*\d+°)",
        "ak": r"AK:\s*(-?[\d,.]+\s*D)"
    }

    if od_text:
        data["OD"].update(find_in_section(patterns, od_text))
    if os_text:
        data["OS"].update(find_in_section(patterns, os_text))
        
    return data

def parse_pentacam(text):
    data = {"OD": {"source": "Pentacam"}, "OS": {"source": "Pentacam"}}
    def find(p, t):
        m = re.search(p, t, re.MULTILINE)
        return m.group(1).strip().replace(',', '.') if m else None

    od_match = re.search(r'Olho:\s*Direito(.*?)(?=OCULUS PENTACAM Mapas|--- Page)', text, re.DOTALL)
    os_match = re.search(r'Olho:\s*Esquerdo(.*?)(?=OCULUS PENTACAM Mapas|--- Page)', text, re.DOTALL)
    od_text = od_match.group(1) if od_match else ""
    os_text = os_match.group(1) if os_match else ""

    patterns = {
        "k1": r"K1\s*([\d.]+\s*D)", "k2": r"K2\s*([\d.]+\s*D)", "km": r"Km\s*([\d.]+\s*D)",
        "astigmatism": r"Astig\.:\s*([\d.]+\s*D)", "q_value": r"val\. Q\.\s*\((?:8mm)\)\s*([-\d.]+)",
        "pachymetry_apex": r"Paq\.Ápice:\s*(\d+\s*μm)", "pachymetry_thinnest": r"Ponto \+ fino:\s*(\d+\s*μm)",
        "acd": r"Prof\.Câmara Ant\.:\s*([\d.]+\s*mm)", "chamber_volume": r"Volume Câmara:\s*(\d+\s*mm\s*3)",
        "chamber_angle": r"Ângulo:\s*([\d.]+\s*\*)"
    }
    
    for key, pattern in patterns.items():
        if od_text: data["OD"][key] = find(pattern, od_text)
        if os_text: data["OS"][key] = find(pattern, os_text)
    return data

# --- MASTER PARSER CONTROLLER ---

def parse_clinical_data(text):
    if
