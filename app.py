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
    Parses a ZEISS IOLMaster 700 report using a "Line-by-Line" strategy.
    It finds all occurrences of a parameter and assumes the first is OD and
    the second is OS, which is robust for column-based layouts.
    Returns the data in a standardized, logical order.
    """
    key_order = ["source", "axial_length", "acd", "k1", "k2", "ak", "wtw", "cct", "lt"]
    
    data = {
        "OD": {key: None for key in key_order},
        "OS": {key: None for key in key_order}
    }
    data["OD"]["source"] = "IOL Master 700"
    data["OS"]["source"] = "IOL Master 700"

    patterns = {
        "axial_length": r"AL:\s*([\d,.]+\s*mm)",
        "acd": r"ACD:\s*([\d,.]+\s*mm)",
        "lt": r"LT:\s*([\d,.]+\s*mm)",
        "cct": r"CCT:\s*([\d,.]+\s*μm)",
        "wtw": r"WTW:\s*([\d,.]+\s*mm)",
        "k1": r"K1:\s*([\d,.]+\s*@\s*\d+°)",
        "k2": r"K2:\s*([\d,.]+\s*@\s*\d+°)",
        "ak": r"[ΔA]K:\s*(-?[\d,.]+\s*D\s*@\s*\d+°)"
    }

    # --- KEY CHANGE: Only use the text from the first page for primary biometry ---
    first_page_text = text.split('--- Page ---')[0]

    for key, pattern in patterns.items():
        # Find all matches for the current pattern on the first page
        matches = re.findall(pattern, first_page_text)
        
        # Clean up the matches to a standard format
        cleaned_matches = [' '.join(m.strip().replace(',', '.').replace('\n', ' ').split()) for m in matches]
        
        # Assign the first found value to OD and the second to OS
        if len(cleaned_matches) > 0:
            data["OD"][key] = cleaned_matches[0]
        if len(cleaned_matches) > 1:
            data["OS"][key] = cleaned_matches[1]

    # Rebuild the final dictionaries to ensure the requested key order
    ordered_data = {
        "OD": {key: data["OD"][key] for key in key_order if data["OD"].get(key) is not None},
        "OS": {key: data["OS"][key] for key in key_order if data["OS"].get(key) is not None}
    }
    return ordered_data

def parse_pentacam(text):
    # This parser can also be updated to use the ordered dictionary approach
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
    if "IOLMaster 700" in text:
        return parse_iol_master_700(text)
    elif "OCULUS PENTACAM" in text:
        return parse_pentacam(text)
    else:
        return {"error": "Unknown device or format", "raw_text": text}

# --- API Routes ---

@app.route('/api/health')
def health_check():
    return jsonify({"status": "running", "version": "3.0.0", "ocr_enabled": bool(client)})

def process_file_and_parse(file):
    if file.filename.lower().endswith('.pdf'):
        pdf_bytes = file.read()
        images = convert_from_bytes(pdf_bytes, fmt='jpeg')
        full_text = ""
        for i, page_image in enumerate(images):
            img_byte_arr = io.BytesIO()
            page_image.save(img_byte_arr, format='JPEG')
            full_text += perform_ocr(img_byte_arr.getvalue())
            if i < len(images) - 1:
                full_text += "\n\n--- Page --- \n\n"
    else:
        image_bytes = file.read()
        full_text = perform_ocr(image_bytes)
    
    return parse_clinical_data(full_text)

@app.route('/api/parse-file', methods=['POST'])
def parse_file_endpoint():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    try:
        structured_data = process_file_and_parse(file)
        return jsonify(structured_data)
    except Exception as e:
        print(f"Error in /api/parse-file: {e}")
        return jsonify({"error": str(e)}), 500

# --- Frontend Serving Routes ---

@app.route('/')
def serve_app():
    return render_template("index.html")

@app.route('/<path:path>')
def serve_fallback(path):
    return render_template('index.html')

# --- Main Execution ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
