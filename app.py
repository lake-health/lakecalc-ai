# app.py
from flask import Flask, jsonify, request, render_template
from google.cloud import vision
import os
import io
import re
from pdf2image import convert_from_bytes
from collections import OrderedDict

# ---------------------------
# Flask
# ---------------------------
app = Flask(__name__, static_folder='static', template_folder='templates')

# ---------------------------
# Google Cloud Vision setup
# ---------------------------
client = None
try:
    credentials_json_str = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    if credentials_json_str:
        from google.oauth2 import service_account
        import json
        credentials_info = json.loads(credentials_json_str)
        credentials = service_account.Credentials.from_service_account_info(credentials_info)
        client = vision.ImageAnnotatorClient(credentials=credentials)
    else:
        if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
            client = vision.ImageAnnotatorClient()
        else:
            print("WARNING: No Vision credentials found. Set GOOGLE_APPLICATION_CREDENTIALS_JSON or GOOGLE_APPLICATION_CREDENTIALS.")
except Exception as e:
    print(f"Error initializing Google Cloud Vision client: {e}")

# ---------------------------
# OCR helper
# ---------------------------
def perform_ocr(image_content: bytes) -> str:
    if not client:
        raise RuntimeError(
            "Google Cloud Vision client is not initialized. "
            "Set GOOGLE_APPLICATION_CREDENTIALS_JSON (recommended) or GOOGLE_APPLICATION_CREDENTIALS."
        )
    image = vision.Image(content=image_content)
    response = client.text_detection(image=image)
    if response.error.message:
        raise RuntimeError(f"Vision API Error: {response.error.message}")
    return response.text_annotations[0].description if response.text_annotations else ""

# ---------------------------
# Parsers
# ---------------------------

def parse_iol_master_700(text: str) -> dict:
    """
    Robust parser for IOLMaster 700.

    - Assign each metric to the last eye marker (OD/OS) BEFORE it.
    - Capture K1/K2/AK with inline axes; if OCR splits axis, scavenge it
      from the same line (or up to next label) and allow digits with spaces
      (e.g., '1 0°' -> '10°').
    - Accept degree variants (°/º/o) and an optional trailing quote.
    """
    data = {
        "OD": OrderedDict([
            ("source", "IOL Master 700"),
            ("axial_length", None), ("acd", None), ("k1", None),
            ("k2", None), ("ak", None), ("wtw", None), ("cct", None), ("lt", None)
        ]),
        "OS": OrderedDict([
            ("source", "IOL Master 700"),
            ("axial_length", None), ("acd", None), ("k1", None),
            ("k2", None), ("ak", None), ("wtw", None), ("cct", None), ("lt", None)
        ])
    }

    # --- Eye markers (OD/OS)
    eye_markers = [{"eye": m.group(1), "pos": m.start()} for m in re.finditer(r"\b(OD|OS)\b", text)]
    if not eye_markers:
        return {"error": "No OD or OS markers found."}
    eye_markers.sort(key=lambda x: x["pos"])

    def eye_before(position: int) -> str:
        last = None
        for marker in eye_markers:
            if marker["pos"] <= position:
                last = marker["eye"]
            else:
                break
        return last or eye_markers[0]["eye"]

    # --- Regex building blocks
    DEG = r"(?:°|º|o)"
    QUO = r'["”]?'  # OCR sometimes leaves an extra quote
    # digits allowing a single optional space between each digit (1 to 3 total digits)
    DIG1_2 = r"\d(?:\s?\d)?"          # 1–2 digits, possibly spaced: '10' or '1 0'
    DIG3   = r"\d(?:\s?\d){2}"        # exactly 3 digits, possibly spaced: '1 0 0' or '165'
    AXIS_INLINE = rf"\s*@\s*(?:{DIG1_2}|{DIG3})\s*{DEG}?{QUO}"

    D_VAL = rf"-?[\d,.]+\s*D(?:{AXIS_INLINE})?"  # diopters with optional inline axis
    MM_VAL = r"-?[\d,.]+\s*mm"
    UM_VAL = r"-?[\d,.]+\s*(?:µm|um)"

    patterns = {
        "axial_length": rf"AL:\s*({MM_VAL})",
        "acd":          rf"ACD:\s*({MM_VAL})",
        "cct":          rf"CCT:\s*({UM_VAL})",
        "lt":           rf"LT:\s*({MM_VAL})",
        "wtw":          rf"WTW:\s*({MM_VAL})",
        "k1":           rf"K1:\s*({D_VAL})",
        "k2":           rf"K2:\s*({D_VAL})",
        "ak":           rf"(?:AK|ΔK|K):\s*({D_VAL})",  # cylinder line label variants
    }

    # Stop scavenging at newline OR at the next metric label
    LABEL_STOP = re.compile(
        r"(?:\r?\n|(?=(?:AL|ACD|CCT|LT|WTW|K1|K2|K|AK|ΔK)\s*:))",
        re.IGNORECASE
    )

    # Axis tokens with/without '@' & degree, allowing spaced digits
    AXIS_1_2_ANY = re.compile(rf"(?:@?\s*)({DIG1_2})\s*{DEG}?{QUO}\b")
    AXIS_3_ANY   = re.compile(rf"(?:@?\s*)({DIG3})\s*{DEG}?{QUO}\b")

    def normalize_axis(num_str: str) -> str:
        # remove spaces between digits: '1 0' -> '10'
        return re.sub(r"\s+", "", num_str)

    def scavenge_axis_forward(tail: str) -> str | None:
        mstop = LABEL_STOP.search(tail)
        segment = tail[:mstop.start()] if mstop else tail
        window = segment[:80]  # local, but generous
        m = AXIS_1_2_ANY.search(window)
        if m:
            return normalize_axis(m.group(1))
        m = AXIS_3_ANY.search(window)
        return normalize_axis(m.group(1)) if m else None

    def scavenge_axis_backward(head: str) -> str | None:
        start_limit = max(0, len(head) - 60)
        slice_ = head[start_limit:]
        # cut back to after the last newline if present
        nl = slice_.rfind("\n")
        if nl != -1:
            slice_ = slice_[nl + 1:]
        # prefer 1–2 digits, then 3
        cands = list(AXIS_1_2_ANY.finditer(slice_)) or list(AXIS_3_ANY.finditer(slice_))
        if cands:
            return normalize_axis(cands[-1].group(1))
        return None

    # --- Extract & assign
    for key, pattern in patterns.items():
        for m in re.finditer(pattern, text, flags=re.IGNORECASE):
            raw = m.group(1)
            value = re.sub(r"\s+", " ", raw).strip()
            eye = eye_before(m.start())

            # If inline axis isn't present, try forward then backward scavenging
            if key in ("k1", "k2", "ak") and "@" not in value:
                axis = scavenge_axis_forward(text[m.end(1): m.end(1) + 160]) or \
                       scavenge_axis_backward(text[:m.start(1)])
                if axis:
                    value = f"{value} @ {axis}°"

            if eye and not data[eye][key]:
                data[eye][key] = value

    # Remove None fields
    for eye in ("OD", "OS"):
        for k in list(data[eye].keys()):
            if data[eye][k] is None:
                del data[eye][k]

    return data


def parse_pentacam(text: str) -> dict:
    # Minimal stub; extend as needed
    return {"OD": {"source": "Pentacam"}, "OS": {"source": "Pentacam"}}


def parse_clinical_data(text: str) -> dict:
    if "IOLMaster 700" in text or "IOL Master 700" in text:
        return parse_iol_master_700(text)
    if "OCULUS PENTACAM" in text or "Pentacam" in text:
        return parse_pentacam(text)
    return {"error": "Unknown device or format", "raw_text": text}

# ---------------------------
# Routes
# ---------------------------

@app.route("/api/health")
def health_check():
    return jsonify({
        "status": "running",
        "version": "20.3.0 (axis tolerates spaced digits)",
        "ocr_enabled": bool(client)
    })


def process_file_and_parse(file_storage) -> dict:
    filename = (file_storage.filename or "").lower()
    if filename.endswith(".pdf"):
        pdf_bytes = file_storage.read()
        images = convert_from_bytes(pdf_bytes, fmt="jpeg")
        full_text_parts = []
        for page_image in images:
            buf = io.BytesIO()
            page_image.save(buf, format="JPEG")
            full_text_parts.append(perform_ocr(buf.getvalue()))
        text = "\n\n--- Page ---\n\n".join(full_text_parts)
    else:
        text = perform_ocr(file_storage.read())
    return parse_clinical_data(text)


@app.route("/api/parse-file", methods=["POST"])
def parse_file_endpoint():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files["file"]
    if not file or file.filename == "":
        return jsonify({"error": "No selected file"}), 400
    try:
        structured = process_file_and_parse(file)
        return jsonify(structured)
    except Exception as e:
        print(f"Error in /api/parse-file: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/")
def serve_app():
    try:
        return render_template("index.html")
    except Exception:
        return """
        <html>
          <body style="font-family: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;">
            <h2>/api/parse-file tester</h2>
            <form action="/api/parse-file" method="post" enctype="multipart/form-data">
              <input type="file" name="file" />
              <button type="submit">Upload & Parse</button>
            </form>
            <p>Health: <a href="/api/health">/api/health</a></p>
          </body>
        </html>
        """


@app.route("/<path:path>")
def serve_fallback(path):
    try:
        return render_template("index.html")
    except Exception:
        return jsonify({"ok": True, "route": path})


# ---------------------------
# Main
# ---------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
