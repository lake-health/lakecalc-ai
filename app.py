# app.py
from flask import Flask, jsonify, request, render_template
from google.cloud import vision
import os
import io
import re
import subprocess
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
# Helpers
# ---------------------------
def poppler_ok() -> bool:
    """Quick check if Poppler is present (so pdf2image will work)."""
    try:
        out = subprocess.check_output(["pdftoppm", "-v"], stderr=subprocess.STDOUT, timeout=2)
        return True  # If it ran, we're good (output varies by distro)
    except Exception:
        return False

# ---------------------------
# OCR helpers
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

def ocr_text_from_filestorage(fs):
    """
    Returns (full_text, pages) where:
      - full_text: str with page separators
      - pages: list[str] raw OCR per page in order
    Uses pdf2image (Poppler). If Poppler path is not default, set POPPLER_PATH env.
    """
    name = (fs.filename or "").lower()
    pages = []

    if name.endswith(".pdf"):
        pdf_bytes = fs.read()
        # Allow explicit Poppler path from env (useful on Docker/Railway)
        poppler_path = os.environ.get("POPPLER_PATH")
        images = convert_from_bytes(pdf_bytes, fmt="jpeg", poppler_path=poppler_path)
        for page_image in images:
            buf = io.BytesIO()
            page_image.save(buf, format="JPEG")
            pages.append(perform_ocr(buf.getvalue()))
    else:
        pages.append(perform_ocr(fs.read()))

    full_text = "\n\n--- Page ---\n\n".join(pages)
    return full_text, pages

# ---------------------------
# Parsers
# ---------------------------
def parse_iol_master_700(text: str) -> dict:
    """
    Robust parser for IOLMaster 700 blocks.

    - Assigns each metric to the last eye marker (OD/OS) that appears BEFORE it.
    - Captures K1/K2/AK values with inline axes (when present), and
      scavenges axis from the same line (or until next label) when OCR splits it.
    - Accepts degree variants ° / º / o and commas for decimals (keeps raw text).
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

    # --- Find eye markers (OD/OS) and positions
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

    # --- Patterns
    AXIS_INLINE = r"\s*@\s*\d{1,3}\s*(?:°|º|o)"
    D_VAL       = rf"-?[\d,.]+\s*D(?:{AXIS_INLINE})?"   # diopters with optional inline axis
    MM_VAL      = r"-?[\d,.]+\s*mm"
    UM_VAL      = r"-?[\d,.]+\s*(?:µm|um)"

    patterns = {
        "axial_length": rf"AL:\s*({MM_VAL})",
        "acd":          rf"ACD:\s*({MM_VAL})",
        "cct":          rf"CCT:\s*({UM_VAL})",
        "lt":           rf"LT:\s*({MM_VAL})",
        "wtw":          rf"WTW:\s*({MM_VAL})",
        "k1":           rf"K1:\s*({D_VAL})",
        "k2":           rf"K2:\s*({D_VAL})",
        # On many IOLMaster printouts the cylinder line is "K:" (sometimes AK or ΔK)
        "ak":           rf"(?:AK|ΔK|K):\s*({D_VAL})",
    }

    # Stop scavenging at newline OR at the next metric label
    LABEL_STOP = re.compile(r"(?:\r?\n|(?=(?:AL|ACD|CCT|LT|WTW|K1|K2|K|AK|ΔK)\s*:))", re.IGNORECASE)

    # Accept axes with or without '@'
    AXIS_PREFER_1_2 = re.compile(r"(?:@?\s*)(\d{1,2})\s*(?:°|º|o)\b")
    AXIS_FALLBACK_3 = re.compile(r"(?:@?\s*)(\d{3})\s*(?:°|º|o)\b")

    def scavenge_axis(tail: str) -> str | None:
        mstop = LABEL_STOP.search(tail)
        segment = tail[:mstop.start()] if mstop else tail
        window = segment[:40]  # cap to stay on the same line / vicinity
        m = AXIS_PREFER_1_2.search(window)
        if m:
            return m.group(1)
        m = AXIS_FALLBACK_3.search(window)
        return m.group(1) if m else None

    # --- Extract & assign
    for key, pattern in patterns.items():
        for m in re.finditer(pattern, text, flags=re.IGNORECASE):
            raw = m.group(1)
            value = re.sub(r"\s+", " ", raw).strip()
            eye = eye_before(m.start())

            # If inline axis isn't present, try scavenging from same line/next chars
            if key in ("k1", "k2", "ak") and "@" not in value:
                axis = scavenge_axis(text[m.end(1): m.end(1) + 100])
                if axis:
                    value = f"{value} @ {axis}°"

            if eye and not data[eye][key]:
                data[eye][key] = value

    # Remove None fields to keep output tidy
    for eye in ("OD", "OS"):
        for k in list(data[eye].keys()):
            if data[eye][k] is None:
                del data[eye][k]

    return data


def parse_pentacam(text: str) -> dict:
    # Minimal stub, expand as needed
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
        "version": "20.0.0 (IOLMaster robust axis + raw flags)",
        "ocr_enabled": bool(client),
        "poppler_ok": poppler_ok(),
        "poppler_path_env": os.environ.get("POPPLER_PATH", None) is not None
    })


def process_file_and_parse(file_storage) -> dict:
    """
    Original behavior preserved (structured only).
    """
    filename = (file_storage.filename or "").lower()

    if filename.endswith(".pdf"):
        pdf_bytes = file_storage.read()
        poppler_path = os.environ.get("POPPLER_PATH")  # allow explicit path in Docker
        images = convert_from_bytes(pdf_bytes, fmt="jpeg", poppler_path=poppler_path)
        full_text = []
        for i, page_image in enumerate(images):
            img_buf = io.BytesIO()
            page_image.save(img_buf, format="JPEG")
            full_text.append(perform_ocr(img_buf.getvalue()))
        text = "\n\n--- Page ---\n\n".join(full_text)
    else:
        image_bytes = file_storage.read()
        text = perform_ocr(image_bytes)

    return parse_clinical_data(text)

def process_file_and_get_raw(file_storage):
    """
    New: returns (full_text, pages) without parsing.
    """
    return ocr_text_from_filestorage(file_storage)

@app.route("/api/parse-file", methods=["POST"])
def parse_file_endpoint():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files["file"]
    if not file or file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    include_raw = request.args.get("include_raw") == "1"
    raw_only    = request.args.get("raw_only") == "1"

    try:
        if raw_only:
            full_text, pages = process_file_and_get_raw(file)
            return jsonify({
                "filename": file.filename,
                "raw_text": full_text,
                "raw_pages": pages,
                "num_chars": len(full_text),
                "num_lines": full_text.count("\n") + 1
            })

        structured = process_file_and_parse(file)

        if include_raw:
            # OCR once more to include the raw text (so you don’t lose your original structured flow)
            file.stream.seek(0)  # rewind to re-read the upload
            full_text, pages = process_file_and_get_raw(file)
            return jsonify({
                "filename": file.filename,
                "structured": structured,
                "raw_text": full_text,
                "raw_pages": pages,
                "num_chars": len(full_text),
                "num_lines": full_text.count("\n") + 1
            })

        return jsonify(structured)
    except Exception as e:
        print(f"Error in /api/parse-file: {e}")
        return jsonify({"error": str(e)}), 500


# Basic front-end (optional template). If you don’t have templates, this still works.
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
            <p>To get raw OCR only, use <code>/api/parse-file?raw_only=1</code>.</p>
            <p>To include raw OCR with structured, use <code>/api/parse-file?include_raw=1</code>.</p>
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