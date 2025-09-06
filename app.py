from flask import Flask, jsonify, request, render_template, send_from_directory
from google.cloud import vision
import os
import io
import PyPDF2

# Initialize Flask App
app = Flask(__name__, static_folder='static', template_folder='templates')

# Configure Google Cloud credentials from environment variable
# The content of the JSON key file is expected to be in this env var
credentials_json_str = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
if credentials_json_str:
    from google.oauth2 import service_account
    import json
    credentials_info = json.loads(credentials_json_str)
    credentials = service_account.Credentials.from_service_account_info(credentials_info)
    client = vision.ImageAnnotatorClient(credentials=credentials)
else:
    # Fallback for local development if the env var is not set
    # This will use the GOOGLE_APPLICATION_CREDENTIALS file path if available
    client = vision.ImageAnnotatorClient()

def perform_ocr(image_content):
    """Performs OCR on the given image content."""
    image = vision.Image(content=image_content)
    response = client.text_detection(image=image)
    texts = response.text_annotations
    if texts:
        return texts[0].description
    return "No text found."

# --- API Routes ---

@app.route('/api/health')
def health_check():
    """Health check endpoint to verify service is running."""
    return jsonify({
        "status": "running",
        "version": "2.0.0",
        "ocr_enabled": bool(credentials_json_str),
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
    if file:
        try:
            content = file.read()
            extracted_text = perform_ocr(content)
            return jsonify({"text": extracted_text})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return jsonify({"error": "File processing failed"}), 500

@app.route('/api/parse-pdf', methods=['POST'])
def parse_pdf():
    """Endpoint to perform OCR on an uploaded PDF."""
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '' or not file.filename.lower().endswith('.pdf'):
        return jsonify({"error": "Please select a PDF file"}), 400
    if file:
        try:
            pdf_reader = PyPDF2.PdfReader(io.BytesIO(file.read()))
            full_text = ""
            # This is a placeholder for actual PDF OCR.
            # A real implementation would convert each PDF page to an image
            # and run OCR on it. For now, we just count pages.
            num_pages = len(pdf_reader.pages)
            full_text = f"PDF processing is a work in progress. The document has {num_pages} page(s)."
            # To actually OCR a PDF, you would need a library like pdf2image
            # to convert pages to images, then loop through them calling perform_ocr.
            return jsonify({"text": full_text})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return jsonify({"error": "PDF processing failed"}), 500

# --- Frontend Serving Routes ---

@app.route('/')
def serve_app():
    """Serves the main index.html file."""
    return render_template("index.html")

@app.route('/<path:path>')
def serve_fallback(path):
    """
    Serves the index.html for any other path.
    This is useful for client-side routing in single-page applications.
    """
    return render_template('index.html')

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
