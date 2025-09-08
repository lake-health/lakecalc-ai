# app.py
from flask import Flask, jsonify, request, render_template
from google.cloud import vision
import os
import io
import re
from pdf2image import convert_from_bytes
from collections import OrderedDict

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
# Parser
# ---------------------------
def parse_iol_master_700(text: str) -> dict:
    """
    Robust IOLMaster 700 parser.

    - Assigns metrics to the last eye marker (OD/OS) appearing *before* them.
    - K1/K2/AK axis: tolerant to OCR quirks like '1 0°', '1°0', '16°5', missing '@', extra quotes.
    - Axis harvester collects up to 3 digits while ignoring non-digits, then prefers 3>2>1 digits.
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

    # Eye markers
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

    # Value patterns
    DEG = r"(?:°|º|o)"
    AXIS_INLINE = rf"\s*@\s*\d{{1,3}}\s*{DEG}?"   # inline when OCR keeps it grouped
    D_VAL   = rf"-?[\d,.]+\s*D(?:{AXIS_INLINE})?"
    MM_VAL  = r"-?[\d,.]+\s*mm"
    UM_VAL  = r"-?[\d,.]+\s*(?:µm|um)"

    patterns = {
        "axial_length": rf"AL:\s*({MM_VAL})",
        "acd":          rf"ACD:\s*({MM_VAL})",
        "cct":          rf"CCT:\s*({UM_VAL})",
        "lt":           rf"LT:\s*({MM_VAL})",
        "wtw":          rf"WTW:\s*({MM_VAL})",
        "k1":           rf"K1:\s*({D_VAL})",
        "k2":           rf"K2:\s*({D_VAL})",
        "ak":           rf"(?:AK|ΔK|K):\s*({D_VAL})",  # cylinder label variants
    }

    # Where to stop scavenging: newline or the next metric label
    LABEL_STOP = re.compile(r"(?:\r?\n|(?=(?:AL|ACD|CCT|LT|WTW|K1|K2|K|AK|ΔK)\s*:))", re.IGNORECASE)

    # --- Axis harvesting ---
    # Grab a loose token that *starts near an axis*: optional @, then a run containing digits,
    # spaces, degree marks, or quotes. We'll strip non-digits afterwards.
    AXIS_TOKEN = re.compile(r"@?\s*([0-9][0-9\s\"”°ºo]{0,6})")

    def best_axis_from(token: str) -> str | None:
        # Keep only digits, cap at 3
        digits = re.sub(r"\D", "", token)[:3]
        if not digits:
            return None
        # Prefer 3-digit (e.g., 165) over 2-digit (e.g., 10) over 1-digit
        if len(digits) == 3:
            return digits
        if len(digits) == 2:
            return digits
        # Single-digit axis is almost always an OCR fragment; keep only if nothing better exists.
        return digits

    def scan_window(s: str) -> str | None:
        # Try all tokens; choose the "best" by length (3>2>1). If ties, take the first.
        best = None
        for m in AXIS_TOKEN.finditer(s):
            candidate = best_axis_from(m.group(1))
            if not candidate:
                continue
            if best is None or len(candidate) > len(best):
                best = candidate
                if len(best) == 3:
                    break
        return best

    def scavenge_axis_forward(tail: str) -> str | None:
        mstop = LABEL_STOP.search(tail)
        segment = tail[:mstop.start()] if mstop else tail
        window = segment[:120]  # local but generous
        return scan_window(window)

    def scavenge_axis_backward(head: str) -> str | None:
        # look left from the start of the numeric D value
        start_limit = max(0, len(head) - 120)
        slice_ = head[start_limit:]
        # keep only the last line to avoid crossing fields
        nl = slice_.rfind("\n")
        if nl != -1:
            slice_ = slice_[nl + 1:]
        return scan_window(slice_)

    # Extract & assign
    for key, pattern in patterns.items():
        for m in re.finditer(pattern, text, flags=re.IGNORECASE):
            raw = m.group(1)
            value = re.sub(r"\s+", " ", raw).strip()
            eye = eye_before(m.start())

            if key in ("k1", "k2", "ak"):
                # If inline didn't include a clean axis, harvest around it
                # (even if '@' in value, OCR may have split digits awkwardly).
                fwd = scavenge_axis_forward(text[m.end(1): m.end(1) + 200])
                bwd = scavenge_axis_backward(text[:m.start(1)])
                # Choose the better (longer) axis; prefer 3 > 2 > 1
                axis = None
                if fwd and bwd:
                    axis = fwd if len(fwd) >= len(bwd) else bwd
                else:
                    axis = fwd or bwd
                if axis:
                    # If value already has an @-axis but it's clearly too short (1 digit),
                    # replace it with the harvested axis.
                    if "@" in value:
                        value = re.sub(r"@[^,;]+$", f"@ {axis}°", value)
                        if "@ " not in value:
                            # fallback replace any '@'...tail pattern
                            value = re.sub(r"@\s*.*", f"@ {axis}°", value)
                    else:
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
        "version": "21.0.0 (robust axis harvester)",
        "ocr_enabled": bool(client)
    })

def process_file_and_parse(file_storage) -> dict:
    filename = (file_storage.filename or "").lower()
    if filename.endswith(".pdf"):
        pdf_bytes = file_storage.read()
        images = convert_from_bytes(pdf_bytes, fmt="jpeg")
        parts = []
        for page_image in images:
            buf = io.BytesIO()
            page_image.save(buf, format="JPEG")
            parts.append(perform_ocr(buf.getvalue()))
        text = "\n\n--- Page ---\n\n".join(parts)
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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
