import os, io, re
from collections import OrderedDict
from io import BytesIO

from flask import Flask, request, jsonify, render_template
from pdfminer.high_level import extract_text as pdfminer_extract_text

from google.cloud import vision
from pdf2image import convert_from_bytes

app = Flask(__name__, static_folder='static', template_folder='templates')

# ---------------------------
# Google Cloud Vision (OCR fallback)
# ---------------------------
vision_client = None
try:
    creds_json = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    if creds_json:
        from google.oauth2 import service_account
        import json
        info = json.loads(creds_json)
        credentials = service_account.Credentials.from_service_account_info(info)
        vision_client = vision.ImageAnnotatorClient(credentials=credentials)
    elif os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        vision_client = vision.ImageAnnotatorClient()
    else:
        print("WARNING: Vision credentials not set. OCR fallback will be unavailable.")
except Exception as e:
    print(f"Vision init error: {e}")


# ---------------------------
# Text extraction (PDF-first, OCR fallback)
# ---------------------------
def try_pdf_text_extract(pdf_bytes: bytes) -> str:
    """Extract native text from a born-digital PDF (no OCR)."""
    try:
        text = pdfminer_extract_text(BytesIO(pdf_bytes)) or ""
        # mild whitespace normalization only
        text = re.sub(r"[ \t]+\n", "\n", text)
        return text.strip()
    except Exception as e:
        print(f"pdfminer error: {e}")
        return ""

def ocr_pdf_to_text(pdf_bytes: bytes) -> str:
    """Render pages to images and OCR each page (fallback)."""
    if not vision_client:
        raise RuntimeError("Vision client not initialized for OCR fallback.")
    pages = []
    images = convert_from_bytes(pdf_bytes, fmt="jpeg")
    for img in images:
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        image = vision.Image(content=buf.getvalue())
        resp = vision_client.text_detection(image=image)
        if resp.error.message:
            raise RuntimeError(f"Vision API Error: {resp.error.message}")
        pages.append(resp.text_annotations[0].description if resp.text_annotations else "")
    return "\n\n--- Page ---\n\n".join(pages).strip()

def get_text_from_upload(fs):
    """
    Returns (text, source_tag):
      - text: full string (pages joined)
      - source_tag: 'pdf_text' | 'ocr_pdf' | 'ocr_image'
    """
    name = (fs.filename or "").lower()
    if name.endswith(".pdf"):
        pdf_bytes = fs.read()
        # 1) PDF text layer first
        text = try_pdf_text_extract(pdf_bytes)
        if text:
            return text, "pdf_text"
        # 2) OCR fallback
        return ocr_pdf_to_text(pdf_bytes), "ocr_pdf"
    else:
        if not vision_client:
            raise RuntimeError("Vision client not initialized; cannot OCR image.")
        image_bytes = fs.read()
        image = vision.Image(content=image_bytes)
        resp = vision_client.text_detection(image=image)
        if resp.error.message:
            raise RuntimeError(f"Vision API Error: {resp.error.message}")
        text = resp.text_annotations[0].description if resp.text_annotations else ""
        return text.strip(), "ocr_image"


# ---------------------------
# Parser for IOL Master 700 (and similar layouts)
# ---------------------------
def parse_iol_master_text(text: str) -> dict:
    """
    Extracts, for each eye (OD/OS), in this order:
    source, axial_length, acd, k1 (D+axis), k2 (D+axis), ak (D+axis), wtw, cct, lt
    Notes:
      - Axis digits tolerate degree variants and spaced digits; prefer 3>2>1 digits when harvesting.
      - Values are assigned to the LAST 'OD'/'OS' marker BEFORE the metric.
      - 'ak' will match lines labeled 'K:', 'AK:' or 'ΔK:' (the device uses 'K:' for cylinder).
    """
    # Device/source detection
    source_label = None
    if re.search(r"IOL\s*Master\s*700", text, re.IGNORECASE):
        source_label = "IOL Master 700"
    elif re.search(r"OCULUS\s+PENTACAM", text, re.IGNORECASE):
        source_label = "Pentacam"
    else:
        # fallback: first non-empty header-ish line
        head_line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "Unknown")
        source_label = head_line[:60]

    # Prepare data with required order
    def fresh_eye():
        return OrderedDict([
            ("source", source_label),
            ("axial_length", None),
            ("acd", None),
            ("k1", None),
            ("k2", None),
            ("ak", None),
            ("wtw", None),
            ("cct", None),
            ("lt", None),
        ])

    data = {"OD": fresh_eye(), "OS": fresh_eye()}

    # Find all OD/OS markers with positions
    eye_marks = [{"eye": m.group(1), "pos": m.start()} for m in re.finditer(r"\b(OD|OS)\b", text)]
    if not eye_marks:
        # still return ordered structure with source filled
        return data
    eye_marks.sort(key=lambda d: d["pos"])

    def eye_before(pos: int) -> str:
        last = "OD"
        for mark in eye_marks:
            if mark["pos"] <= pos:
                last = mark["eye"]
            else:
                break
        return last

    # Common token regexes
    # Accept both comma and dot decimals; keep raw text (you can normalize later)
    MM   = r"-?\d[\d.,]*\s*mm"
    UM   = r"-?\d[\d.,]*\s*(?:µm|um)"
    DVAL = r"-?\d[\d.,]*\s*D"

    # Axis harvesting helpers (robust to spaces/degree/quotes)
    DEG_QUOTE = r'(?:°|º|o)?["”\']?'  # degree optional, stray quote tolerated

    # tight label stop (stop scanning at newline or next known label)
    LABEL_STOP = re.compile(r"(?:\r?\n|(?=(?:AL|ACD|CCT|LT|WTW|K1|K2|K|AK|ΔK)\s*:))", re.IGNORECASE)

    def harvest_axis(field_tail: str) -> str | None:
        """Harvest up to 3 digits for axis within same field; prefer 3>2>1 digits."""
        # Trim to same line / before next label
        mstop = LABEL_STOP.search(field_tail)
        seg = field_tail[:mstop.start()] if mstop else field_tail
        seg = seg[:120]  # local window

        # 1) If '@' present, grab digits after it
        if "@" in seg:
            after = seg.split("@", 1)[1]
            digits = re.findall(r"\d", after)
            axis = "".join(digits)[:3]
            return axis or None

        # 2) Otherwise, look for digits near a degree symbol (digits can be spaced/split)
        m = re.search(r"(\d(?:\D{0,2}\d){0,2})\s*" + DEG_QUOTE, seg)
        if m:
            axis = re.sub(r"\D", "", m.group(1))[:3]
            return axis or None

        return None

    # Patterns for metrics (capture diopters without axis; we'll attach axis with harvester)
    patterns = {
        "axial_length": re.compile(rf"AL:\s*({MM})", re.IGNORECASE),
        "acd":          re.compile(rf"ACD:\s*({MM})", re.IGNORECASE),
        "cct":          re.compile(rf"CCT:\s*({UM})", re.IGNORECASE),
        "lt":           re.compile(rf"LT:\s*({MM})", re.IGNORECASE),
        "wtw":          re.compile(rf"WTW:\s*({MM})", re.IGNORECASE),
        "k1":           re.compile(rf"K1:\s*({DVAL})", re.IGNORECASE),
        "k2":           re.compile(rf"K2:\s*({DVAL})", re.IGNORECASE),
        # cylinder line: device often prints just "K:"; include AK and ΔK too
        "ak":           re.compile(rf"(?:AK|ΔK|K):\s*({DVAL})", re.IGNORECASE),
    }

    # Extract/assign in a single pass per metric type
    for key, pat in patterns.items():
        for m in pat.finditer(text):
            raw_val = m.group(1)
            clean_val = re.sub(r"\s+", " ", raw_val).strip()
            pos = m.start()
            eye = eye_before(pos)

            # add axis for K1/K2/AK if available in the same field
            if key in ("k1", "k2", "ak"):
                tail = text[m.end(1): m.end(1) + 200]
                axis = harvest_axis(tail)
                if axis:
                    if "@" in clean_val:
                        # normalize any weird inline axis
                        clean_val = re.sub(r"@\s*\d[\d\s\"”°ºo]*", f"@ {axis}°", clean_val)
                    else:
                        clean_val = f"{clean_val} @ {axis}°"

            # write once
            if data[eye][key] is None:
                data[eye][key] = clean_val

    # Final tidy: ensure keys exist in requested order and None replaced by ""
    for eye in ("OD", "OS"):
        for k in list(data[eye].keys()):
            if data[eye][k] is None:
                data[eye][k] = ""

    return data


# ---------------------------
# Routes
# ---------------------------
@app.route("/api/health")
def health():
    return jsonify({
        "status": "running",
        "version": "PDF-first parsing (axes robust) v1.0",
        "ocr_enabled": bool(vision_client)
    })

@app.route("/api/parse-file", methods=["POST"])
def parse_file():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400
    fs = request.files["file"]
    if not fs or fs.filename == "":
        return jsonify({"error": "No selected file"}), 400

    include_raw = request.args.get("include_raw") == "1"
    raw_only    = request.args.get("raw_only") == "1"

    try:
        text, source_tag = get_text_from_upload(fs)

        if raw_only:
            return jsonify({
                "filename": fs.filename,
                "text_source": source_tag,
                "raw_text": text,
                "num_chars": len(text),
                "num_lines": text.count("\n") + 1
            })

        parsed = parse_iol_master_text(text)

        if include_raw:
            return jsonify({
                "filename": fs.filename,
                "text_source": source_tag,
                "structured": parsed,
                "raw_text_preview": text[:1500]
            })

        return jsonify(parsed)

    except Exception as e:
        print(f"Error in /api/parse-file: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/")
def root():
    return """
    <html><body style="font-family:system-ui;max-width:900px;margin:2rem auto;">
      <h2>LakeCalc.ai — IOL Parser</h2>
      <form action="/api/parse-file" method="post" enctype="multipart/form-data">
        <p><input type="file" name="file" required /></p>
        <button type="submit">Upload & Parse</button>
      </form>
      <p style="margin-top:1rem">
        Debug options: append <code>?include_raw=1</code> to see a text preview, or <code>?raw_only=1</code> to dump text only.
      </p>
      <p>Health: <a href="/api/health">/api/health</a></p>
    </body></html>
    """

@app.route("/<path:path>")
def fallback(path):
    try:
        return render_template("index.html")
    except Exception:
        return jsonify({"ok": True, "route": path})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
