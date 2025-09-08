# app.py
from flask import Flask, jsonify, request, render_template
from google.cloud import vision
import os, io, re
from pdf2image import convert_from_bytes
from collections import OrderedDict

app = Flask(__name__, static_folder='static', template_folder='templates')

# ---------------------------
# Google Cloud Vision setup
# ---------------------------
client = None
try:
    creds_json = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    if creds_json:
        from google.oauth2 import service_account
        import json
        info = json.loads(creds_json)
        credentials = service_account.Credentials.from_service_account_info(info)
        client = vision.ImageAnnotatorClient(credentials=credentials)
    elif os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        client = vision.ImageAnnotatorClient()
    else:
        print("WARNING: Vision credentials not set. Set GOOGLE_APPLICATION_CREDENTIALS_JSON or GOOGLE_APPLICATION_CREDENTIALS.")
except Exception as e:
    print(f"Error initializing Vision: {e}")

# ---------------------------
# OCR helper
# ---------------------------
def perform_ocr(image_content: bytes) -> str:
    if not client:
        raise RuntimeError("Google Cloud Vision client is not initialized.")
    image = vision.Image(content=image_content)
    resp = client.text_detection(image=image)
    if resp.error.message:
        raise RuntimeError(f"Vision API Error: {resp.error.message}")
    return resp.text_annotations[0].description if resp.text_annotations else ""

def ocr_from_filestorage(fs) -> str:
    """Return full OCR text for a PDF or image upload."""
    name = (fs.filename or "").lower()
    if name.endswith(".pdf"):
        pdf_bytes = fs.read()
        images = convert_from_bytes(pdf_bytes, fmt="jpeg")
        parts = []
        for page_image in images:
            buf = io.BytesIO()
            page_image.save(buf, format="JPEG")
            parts.append(perform_ocr(buf.getvalue()))
        return "\n\n--- Page ---\n\n".join(parts)
    else:
        return perform_ocr(fs.read())

# ---------------------------
# Minimal IOLMaster parser (unchanged logic, OK if axes fail for now)
# ---------------------------
def parse_iol_master_700(text: str) -> dict:
    data = {
        "OD": OrderedDict([("source","IOL Master 700"),("axial_length",None),("acd",None),("k1",None),("k2",None),("ak",None),("wtw",None),("cct",None),("lt",None)]),
        "OS": OrderedDict([("source","IOL Master 700"),("axial_length",None),("acd",None),("k1",None),("k2",None),("ak",None),("wtw",None),("cct",None),("lt",None)])
    }
    eyes = [{"eye": m.group(1), "pos": m.start()} for m in re.finditer(r"\b(OD|OS)\b", text)]
    if not eyes:
        return {"error":"No OD/OS markers found."}
    eyes.sort(key=lambda x: x["pos"])
    def eye_before(pos:int)->str:
        last=None
        for mark in eyes:
            if mark["pos"] <= pos: last = mark["eye"]
            else: break
        return last or eyes[0]["eye"]

    MM  = r"-?[\d,.]+\s*mm"
    UM  = r"-?[\d,.]+\s*(?:µm|um)"
    D   = r"-?[\d,.]+\s*D(?:\s*@\s*\d{1,3}\s*(?:°|º|o))?"
    pats = {
        "axial_length": rf"AL:\s*({MM})",
        "acd":          rf"ACD:\s*({MM})",
        "cct":          rf"CCT:\s*({UM})",
        "lt":           rf"LT:\s*({MM})",
        "wtw":          rf"WTW:\s*({MM})",
        "k1":           rf"K1:\s*({D})",
        "k2":           rf"K2:\s*({D})",
        "ak":           rf"(?:AK|ΔK|K):\s*({D})",
    }
    for key, pat in pats.items():
        for m in re.finditer(pat, text, flags=re.IGNORECASE):
            value = re.sub(r"\s+", " ", m.group(1)).strip()
            eye = eye_before(m.start())
            if eye and not data[eye][key]:
                data[eye][key] = value
    for eye in ("OD","OS"):
        for k in list(data[eye].keys()):
            if data[eye][k] is None:
                del data[eye][k]
    return data

def parse_pentacam(text: str) -> dict:
    return {"OD":{"source":"Pentacam"},"OS":{"source":"Pentacam"}}

def parse_clinical_data(text: str) -> dict:
    if "IOLMaster 700" in text or "IOL Master 700" in text:
        return parse_iol_master_700(text)
    if "OCULUS PENTACAM" in text or "Pentacam" in text:
        return parse_pentacam(text)
    return {"error":"Unknown device or format","raw_text":text}

# ---------------------------
# Routes
# ---------------------------
@app.route("/api/health")
def health_check():
    return jsonify({"status":"running","version":"OCR dump helper","ocr_enabled":bool(client)})

@app.route("/api/parse-file", methods=["POST"])
def parse_file_endpoint():
    if "file" not in request.files:
        return jsonify({"error":"No file part"}), 400
    f = request.files["file"]
    if not f or f.filename == "":
        return jsonify({"error":"No selected file"}), 400
    try:
        text = ocr_from_filestorage(f)
        return jsonify(parse_clinical_data(text))
    except Exception as e:
        print(f"Error in /api/parse-file: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/ocr-dump", methods=["POST"])
def ocr_dump_endpoint():
    """Upload a file and get the raw OCR text back."""
    if "file" not in request.files:
        return jsonify({"error":"No file part"}), 400
    f = request.files["file"]
    if not f or f.filename == "":
        return jsonify({"error":"No selected file"}), 400
    try:
        raw_text = ocr_from_filestorage(f)
        return jsonify({
            "filename": f.filename,
            "num_chars": len(raw_text),
            "num_lines": raw_text.count("\n") + 1 if raw_text else 0,
            "raw_text": raw_text
        })
    except Exception as e:
        print(f"Error in /api/ocr-dump: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/")
def root():
    # Minimal page with two forms: Parse and OCR Dump
    return """
    <html><body style="font-family:system-ui;max-width:900px;margin:2rem auto;">
      <h2>IOL Parser / OCR Tester</h2>
      <h3>Parse (structured JSON)</h3>
      <form action="/api/parse-file" method="post" enctype="multipart/form-data">
        <input type="file" name="file" required />
        <button type="submit">Upload & Parse</button>
      </form>
      <hr/>
      <h3>Dump OCR (raw text)</h3>
      <form action="/api/ocr-dump" method="post" enctype="multipart/form-data">
        <input type="file" name="file" required />
        <button type="submit">Upload & Dump OCR</button>
      </form>
      <p>Health: <a href="/api/health">/api/health</a></p>
    </body></html>
    """

@app.route("/<path:path>")
def fallback(path):
    return render_template("index.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
