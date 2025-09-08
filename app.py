import os
import io
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from google.cloud import vision
from pdf2image import convert_from_bytes

# --- Flask setup ---
app = Flask(__name__, static_folder="frontend", static_url_path="")
CORS(app)

# --- Google Vision setup ---
VISION_CREDENTIALS = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
client = None
if VISION_CREDENTIALS and os.path.exists(VISION_CREDENTIALS):
    client = vision.ImageAnnotatorClient()
else:
    print("⚠️ Google Vision credentials not found. OCR will not work.")

# --- OCR helpers ---
def perform_ocr(image_content: bytes) -> str:
    if not client:
        raise RuntimeError("Google Cloud Vision client is not initialized.")
    image = vision.Image(content=image_content)
    response = client.text_detection(image=image)
    if response.error.message:
        raise RuntimeError(f"Vision API Error: {response.error.message}")
    return response.text_annotations[0].description if response.text_annotations else ""

def ocr_text_from_filestorage(fs):
    """
    Returns (full_text, pages) where:
      - full_text: str with page separators
      - pages: list[str] raw OCR per page in order
    """
    name = (fs.filename or "").lower()
    pages = []

    if name.endswith(".pdf"):
        pdf_bytes = fs.read()
        images = convert_from_bytes(pdf_bytes, fmt="jpeg")
        for page_image in images:
            buf = io.BytesIO()
            page_image.save(buf, format="JPEG")
            pages.append(perform_ocr(buf.getvalue()))
    else:
        pages.append(perform_ocr(fs.read()))

    full_text = "\n\n--- Page ---\n\n".join(pages)
    return full_text, pages

# --- Parser stub (keep your existing logic here) ---
def parse_clinical_data(text: str) -> dict:
    """Replace with your IOLMaster / Pentacam parser"""
    return {"note": "Parsing not implemented in this stub", "length": len(text)}

# --- Routes ---
@app.route("/api/parse-file", methods=["POST"])
def parse_file_endpoint():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400
    f = request.files["file"]
    if not f or f.filename == "":
        return jsonify({"error": "No selected file"}), 400

    include_raw = request.args.get("include_raw") == "1"
    raw_only = request.args.get("raw_only") == "1"

    try:
        full_text, pages = ocr_text_from_filestorage(f)

        if raw_only:
            return jsonify({
                "filename": f.filename,
                "raw_text": full_text,
                "raw_pages": pages,
                "num_chars": len(full_text),
                "num_lines": full_text.count("\n") + 1
            })

        structured_data = parse_clinical_data(full_text)

        if include_raw:
            return jsonify({
                "filename": f.filename,
                "structured": structured_data,
                "raw_text": full_text,
                "raw_pages": pages,
                "num_chars": len(full_text),
                "num_lines": full_text.count("\n") + 1
            })

        return jsonify(structured_data)

    except Exception as e:
        print(f"Error in /api/parse-file: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})

# Serve frontend files if you have them
@app.route("/")
def serve_index():
    return send_from_directory(app.static_folder, "index.html")

@app.errorhandler(404)
def not_found(e):
    return send_from_directory(app.static_folder, "index.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)