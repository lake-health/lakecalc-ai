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

def perform_ocr(image_content: bytes) -> str:
    if not client:
        raise RuntimeError("Google Cloud Vision client is not initialized.")
    image = vision.Image(content=image_content)
    resp = client.text_detection(image=image)
    if resp.error.message:
        raise RuntimeError(f"Vision API Error: {resp.error.message}")
    return resp.text_annotations[0].description if resp.text_annotations else ""

# ---------------------------
# IOLMaster 700 parser
# ---------------------------
def parse_iol_master_700(text: str) -> dict:
    data = {
        "OD": OrderedDict([("source","IOL Master 700"),("axial_length",None),("acd",None),("k1",None),("k2",None),("ak",None),("wtw",None),("cct",None),("lt",None)]),
        "OS": OrderedDict([("source","IOL Master 700"),("axial_length",None),("acd",None),("k1",None),("k2",None),("ak",None),("wtw",None),("cct",None),("lt",None)])
    }

    # Eye markers
    eyes = [{"eye": m.group(1), "pos": m.start()} for m in re.finditer(r"\b(OD|OS)\b", text)]
    if not eyes:
        return {"error":"No OD/OS markers found."}
    eyes.sort(key=lambda x: x["pos"])

    def eye_before(pos: int) -> str:
        last = None
        for mark in eyes:
            if mark["pos"] <= pos: last = mark["eye"]
            else: break
        return last or eyes[0]["eye"]

    # Metric patterns
    MM  = r"-?[\d,.]+\s*mm"
    UM  = r"-?[\d,.]+\s*(?:µm|um)"
    DNOAX = r"-?[\d,.]+\s*D"                 # diopters (no axis in the group)
    patterns = {
        "axial_length": rf"AL:\s*({MM})",
        "acd":          rf"ACD:\s*({MM})",
        "cct":          rf"CCT:\s*({UM})",
        "lt":           rf"LT:\s*({MM})",
        "wtw":          rf"WTW:\s*({MM})",
        "k1":           rf"K1:\s*({DNOAX})",
        "k2":           rf"K2:\s*({DNOAX})",
        "ak":           rf"(?:AK|ΔK|K):\s*({DNOAX})",
    }

    # Stop window: newline OR next label
    LABEL_STOP = re.compile(r"(?:\r?\n|(?=(?:AL|ACD|CCT|LT|WTW|K1|K2|K|AK|ΔK)\s*:))", re.IGNORECASE)

    def harvest_axis(suffix: str) -> str | None:
        """Harvest up to 3 digits for the axis from the same line/field only."""
        # Trim to same line/next label
        mstop = LABEL_STOP.search(suffix)
        field = suffix[:mstop.start()] if mstop else suffix

        # Case A: axis follows '@'
        if "@" in field:
            after = field.split("@", 1)[1]
            digits = re.findall(r"\d", after)
            axis = "".join(digits)[:3]
            return axis if axis else None

        # Case B: axis without '@' but with degree mark nearby
        m = re.search(r"(\d[^\d]{0,3}\d(?:[^\d]{0,3}\d)?)\s*(?:°|º|o)", field)
        if m:
            axis = re.sub(r"\D", "", m.group(1))[:3]
            return axis if axis else None

        return None

    # Extract & assign
    for key, pat in patterns.items():
        for m in re.finditer(pat, text, flags=re.IGNORECASE):
            raw = m.group(1)
            val = re.sub(r"\s+", " ", raw).strip()
            eye = eye_before(m.start())

            if key in ("k1","k2","ak"):
                # Look right after the matched diopter (keep in-field only)
                tail = text[m.end(1): m.end(1) + 200]
                axis = harvest_axis(tail)
                if axis:
                    val = f"{val} @ {axis}°"

            if eye and not data[eye][key]:
                data[eye][key] = val

    # Cleanup Nones
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
    return jsonify({"status":"running","version":"22.0.0 (axis digits-only within field)","ocr_enabled":bool(client)})

def process_file_and_parse(file_storage) -> dict:
    name = (file_storage.filename or "").lower()
    if name.endswith(".pdf"):
        pdf_bytes = file_storage.read()
        images = convert_from_bytes(pdf_bytes, fmt="jpeg")
        parts = []
        for img in images:
            buf = io.BytesIO(); img.save(buf, format="JPEG")
            parts.append(perform_ocr(buf.getvalue()))
        text = "\n\n--- Page ---\n\n".join(parts)
    else:
        text = perform_ocr(file_storage.read())
    return parse_clinical_data(text)

@app.route("/api/parse-file", methods=["POST"])
def parse_file_endpoint():
    if "file" not in request.files:
        return jsonify({"error":"No file part"}), 400
    f = request.files["file"]
    if not f or f.filename == "":
        return jsonify({"error":"No selected file"}), 400
    try:
        return jsonify(process_file_and_parse(f))
    except Exception as e:
        print(f"Error in /api/parse-file: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/")
def root():
    try:
        return render_template("index.html")
    except Exception:
        return """<html><body style="font-family:system-ui">
        <h2>/api/parse-file tester</h2>
        <form action="/api/parse-file" method="post" enctype="multipart/form-data">
          <input type="file" name="file"/><button type="submit">Upload & Parse</button>
        </form><p>Health: <a href="/api/health">/api/health</a></p></body></html>"""

@app.route("/<path:path>")
def fallback(path):
    try:
        return render_template("index.html")
    except Exception:
        return jsonify({"ok":True,"route":path})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
