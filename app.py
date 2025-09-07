from flask import Flask, jsonify, request, render_template
from google.cloud import vision
import os
import io
from pdf2image import convert_from_bytes # New import

# Initialize Flask App
app = Flask(__name__, static_folder='static', template_folder='templates')

# --- Google Cloud Vision Client Setup ---
# Securely initialize the client from the environment variable
credentials_json_str = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
client = None
if credentials_json_str:
    from google.oauth2 import service_account
    import json
    try:
        credentials_info = json.loads(credentials_json_str)
        credentials = service_account.Credentials.from_service_account_info(credentials_info)
        client = vision.ImageAnnotatorClient(credentials=credentials)
    except Exception as e:
        # Log the error but don't crash the app
        print(f"Error initializing Google Cloud Vision client: {e}")
else:
    print("WARNING: GOOGLE_APPLICATION_CREDENTIALS_JSON not set. OCR will not function.")

# --- Core OCR Function ---
def perform_ocr(image_content):
    """Performs OCR on a single image's byte content."""
    if not client:
        raise Exception("Google Cloud Vision client is not initialized.")
    
    image = vision.Image(content=image_content)
    response = client.text_detection(image=image)
    
    if response.error.message:
        raise Exception(f"Vision API Error: {response.error.message}")
        
    if response.text_annotations:
        return response.text_annotations[0].description
    return "" # Return empty string if no text is found

# --- API Routes ---

@app.route('/api/health')
def health_check():
    """Health check endpoint to verify service is running."""
    return jsonify({
        "status": "running",
        "version": "2.1.0", # Version updated for PDF processing
        "ocr_enabled": bool(client),
        "service": "LakeCalc.ai API (Railway Optimized)"
    })

@app.route('/api/calculate-lol', methods=['POST'])
def calculate_lol():
    """Endpoint to perform OCR on an uploaded image."""
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    try:
        content = file.read()
        extracted_text = perform_ocr(content)
        return jsonify({"text": extracted_text})
    except Exception as e:
        print(f"Error in /api/calculate-lol: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/parse-pdf', methods=['POST'])
def parse_pdf():
    """
    Endpoint to perform OCR on each page of an uploaded PDF.
    This is the new, fully implemented version.
    """
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '' or not file.filename.lower().endswith('.pdf'):
        return jsonify({"error": "Please select a PDF file"}), 400
    
    try:
        pdf_bytes = file.read()
        # Convert PDF bytes to a list of PIL image objects
        # The 'fmt' specifies the output image format
        images = convert_from_bytes(pdf_bytes, fmt='jpeg')
        
        full_text = ""
        
        # Loop through each page image and perform OCR
        for i, page_image in enumerate(images):
            # Convert PIL image to bytes for the OCR function
            img_byte_arr = io.BytesIO()
            page_image.save(img_byte_arr, format='JPEG')
            image_content = img_byte_arr.getvalue()
            
            text_from_page = perform_ocr(image_content)
            full_text += f"--- Page {i+1} ---\n{text_from_page}\n\n"
            
        return jsonify({"text": full_text.strip()})
        
    except Exception as e:
        print(f"Error in /api/parse-pdf: {e}")
        return jsonify({"error": str(e)}), 500

# --- Frontend Serving Routes ---

@app.route('/')
def serve_app():
    """Serves the main index.html file."""
    return render_template("index.html")

@app.route('/<path:path>')
def serve_fallback(path):
    """Serves the index.html for any other path (for client-side routing)."""
    return render_template('index.html')

# --- Main Execution ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
