# app.py
import os, io, re
from collections import OrderedDict
from io import BytesIO

from flask import Flask, request, jsonify, render_template
from pdfminer.high_level import extract_text as pdfminer_extract_text

# Google Vision used only as fallback when there's no text layer / for images
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
        # OK: born-digital PDFs still work via pdfminer
        print("INFO: Vision credentials not set. OCR fallback disabled.")
except Exception as e:
    print(f"Vision init error: {e}")


# ---------------------------
# Text extraction (PDF-first, with optional force modes)
# ---------------------------
def try_pdf_text_extract(pdf_bytes: bytes) -> str:
    """Extract native text from born-digital PDF (no OCR)."""
    try:
        text = pdfminer_extract_text(BytesIO(pdf_bytes)) or ""
        text = re.sub(r"[ \t]+\n", "\n", text)  # mild cleanup
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

def get_text_from_upload(fs, force_mode: str | None = None):
    """
    Returns (text, source_tag): 'pdf_text' | 'ocr_pdf' | 'ocr_image'
    force_mode: 'pdf' to force pdfminer, 'ocr' to force OCR (when possible).
    """
    name = (fs.filename or "").lower()
    is_pdf = name.endswith(".pdf")

    if is_pdf:
        pdf_bytes = fs.read()

        if force_mode == "pdf":
            return try_pdf_text_extract(pdf_bytes), "pdf_text"
        if force_mode == "ocr":
            return ocr_pdf_to_text(pdf_bytes), "ocr_pdf"

        # Default: PDF text first, OCR fallback
        text = try_pdf_text_extract(pdf_bytes)
        if text:
            return text, "pdf_text"
        return ocr_pdf_to_text(pdf_bytes), "ocr_pdf"

    # Not a PDF (image): OCR is required
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
# Normalization to fix OCR/PDF line break quirks
# ---------------------------
def normalize_for_ocr(text: str) -> str:
    """
    Fix common fragmentation:
      - Join label/value/unit splits (AL/ACD/LT/WTW/CCT)
      - Join K-lines split across value and 'D'
      - Normalize scattered '@', '°', and digits into '@ XX°'
      - Collapse excessive whitespace
    """
    t = text.replace("\u00A0", " ")

    # AL/ACD/LT/WTW/CCT on 3 lines -> single line
    t = re.sub(r"(?mi)^(AL|ACD|LT|WTW|CCT)\s*:\s*\n\s*([-\d.,]+)\s*\n\s*(mm|µm|um)\b",
               r"\1: \2 \3", t)

    # K lines: value on one line, 'D' on next
    t = re.sub(r"(?mi)^(K1|K2|K|AK|ΔK)\s*:\s*\n\s*([-\d.,]+)\s*\n\s*D\b",
               r"\1: \2 D", t)

    # Normalize axis patterns: "@ \n ° \n 10" or "@ \n 10 \n °" -> "@ 10°"
    t = re.sub(r"@\s*(?:\r?\n|\s)*(?:[°ºo])\s*(?:\r?\n|\s)*?(\d{1,3})\b", r"@ \1°", t)
    t = re.sub(r"@\s*(?:\r?\n|\s)*(\d{1,3})\s*(?:\r?\n|\s)*(?:[°ºo])\b", r"@ \1°", t)

    # Lone degree+digits split across lines -> " 10°"
    t = re.sub(r"(?:[°ºo])\s*(?:\r?\n|\s)*?(\d{1,3})\b", r" \1°", t)

    # Collapse internal whitespace
    t = re.sub(r"[ \t]+", " ", t)

    return t


# ---------------------------
# Parser for IOLMaster (ordered fields) — robust OD/OS detection
# ---------------------------
def parse_iol_master_text(text: str) -> dict:
    """
    Returns, per eye and IN ORDER:
      source, axial_length, acd, k1 (D+axis), k2 (D+axis), ak (D+axis), wtw, cct, lt
    Header detection is conservative to avoid false OS from 'Olhos' and 'OD: Cilindro' lines.
    """
    # Source label
    if re.search(r"IOL\s*Master\s*700", text, re.IGNORECASE):
        source_label = "IOL Master 700"
    elif re.search(r"OCULUS\s+PENTACAM", text, re.IGNORECASE):
        source_label = "Pentacam"
    else:
        head_line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "Unknown")
        source_label = head_line[:60]

    def blank_eye():
        return OrderedDict([
            ("source", source_label),
            ("axial_length", ""),
            ("acd", ""),
            ("k1", ""),
            ("k2", ""),
            ("ak", ""),
            ("wtw", ""),
            ("cct", ""),
            ("lt", ""),
        ])

    result = {"OD": blank_eye(), "OS": blank_eye()}

    # ---------- Find OD/OS headers, conservatively ----------
    lines = text.splitlines(keepends=True)
    offsets, pos = [], 0
    for ln in lines:
        offsets.append(pos)
        pos += len(ln)

    def is_metricy(u: str) -> bool:
        # any label or obvious number present -> not a header
        if re.search(r"\b(AL|ACD|CCT|LT|WTW|K1|K2|AK|ΔK|TK1|TK2|SE|SD|P:|Ix|Iy)\b", u): return True
        if "CILINDRO" in u: return True
        if re.search(r"\d", u): return True
        return False

    markers = []
    for i, line in enumerate(lines):
        u = line.upper()
        if not u.strip(): 
            continue
        # never treat 'OLHOS' lines as headers
        if re.search(r"\bOLHOS\b", u): 
            continue

        # strong word cues first
        if ("DIREITA" in u or "RIGHT" in u) and not is_metricy(u):
            markers.append({"eye": "OD", "pos": offsets[i]})
            continue
        if (("ESQUERDA" in u or "ESQUERDO" in u or "LEFT" in u) and not is_metricy(u)):
            markers.append({"eye": "OS", "pos": offsets[i]})
            continue

        # stand-alone tokens (reject 'OD:' note lines)
        if re.search(r"\bOD\b|\bO\s*D\b", u) and not is_metricy(u) and not re.search(r"\bOD\s*:", u):
            markers.append({"eye": "OD", "pos": offsets[i]})
            continue
        if re.search(r"\bOS\b|\bO\s*S\b|\bOE\b|\bO\s*E\b", u) and not is_metricy(u):
            markers.append({"eye": "OS", "pos": offsets[i]})
            continue

    markers.sort(key=lambda x: x["pos"])
    # collapse near duplicates
    collapsed = []
    for m in markers:
        if not collapsed or (m["pos"] - collapsed[-1]["pos"]) > 6 or m["eye"] != collapsed[-1]["eye"]:
            collapsed.append(m)
    markers = collapsed

    # Build blocks; if none, treat whole as one OD block
    blocks = []
    if markers:
        for i, mark in enumerate(markers):
            start = mark["pos"]
            end = markers[i + 1]["pos"] if i + 1 < len(markers) else len(text)
            blocks.append((mark["eye"], text[start:end]))
    else:
        blocks = [("OD", text)]

    # ---------- Patterns & axis harvesting ----------
    MM   = r"-?\d[\d.,]*\s*mm"
    UM   = r"-?\d[\d.,]*\s*(?:µm|um)"
    DVAL = r"-?\d[\d.,]*\s*D"
    LABEL_STOP = re.compile(r"(?:\r?\n|(?=(?:AL|ACD|CCT|LT|WTW|K1|K2|K|AK|ΔK)\s*:))", re.IGNORECASE)

    def harvest_axis(field_tail: str) -> str:
        mstop = LABEL_STOP.search(field_tail)
        seg = field_tail[:mstop.start()] if mstop else field_tail
        seg = seg[:120]
        if "@" in seg:
            after = seg.split("@", 1)[1]
            digits = re.findall(r"\d", after)
            axis = "".join(digits)[:3]
            return f" @ {axis}°" if axis else ""
        m = re.search(r"(\d{1,3})\s*(?:°|º|o)\b", seg)
        return f" @ {m.group(1)}°" if m else ""

    patterns = {
        "axial_length": re.compile(rf"AL:\s*({MM})", re.IGNORECASE),
        "acd":          re.compile(rf"ACD:\s*({MM})", re.IGNORECASE),
        "cct":          re.compile(rf"CCT:\s*({UM})", re.IGNORECASE),
        "lt":           re.compile(rf"LT:\s*({MM})", re.IGNORECASE),
        "wtw":          re.compile(rf"WTW:\s*({MM})", re.IGNORECASE),
        "k1":           re.compile(rf"K1:\s*({DVAL})", re.IGNORECASE),
        "k2":           re.compile(rf"K2:\s*({DVAL})", re.IGNORECASE),
        "ak":           re.compile(rf"(?:AK|ΔK|K):\s*({DVAL})", re.IGNORECASE),
    }

    def parse_block(block: str) -> dict:
        out = {"axial_length":"", "acd":"", "k1":"", "k2":"", "ak":"", "wtw":"", "cct":"", "lt":""}
        for key, pat in patterns.items():
            for m in pat.finditer(block):
                raw = re.sub(r"\s+", " ", m.group(1)).strip()
                if key in ("k1", "k2", "ak"):
                    raw = re.sub(r"@\s*.*$", "", raw)  # drop inline axis tail
                    tail = block[m.end(1): m.end(1) + 200]
                    axis = harvest_axis(tail)
                    raw = (raw + axis).strip()
                if not out[key]:
                    out[key] = raw
        return out

    parsed_blocks = [(eye, parse_block(block)) for eye, block in blocks]

    # If exactly one block has measurements, map it to OD (single-eye export safety)
    def any_filled(d): return any(v for v in d.values())
    with_data = [(e, d) for (e, d) in parsed_blocks if any_filled(d)]
    if len(with_data) == 1:
        _, d = with_data[0]
        for k, v in d.items():
            if v: result["OD"][k] = v
        return result

    # Merge per eye (first occurrence wins)
    merged = {"OD": {}, "OS": {}}
    for e, d in parsed_blocks:
        if e not in merged: merged[e] = {}
        for k, v in d.items():
            if v and k not in merged[e]:
                merged[e][k] = v
    for e in ("OD", "OS"):
        for k, v in merged.get(e, {}).items():
            if v: result[e][k] = v

    return result

# ---------------------------
# Routes
# ---------------------------
@app.route("/api/health")
def health():
    return jsonify({
        "status": "running",
        "version": "LakeCalc.ai parser v2.1 (token-OD/OS; PDF-first + OCR normalize)",
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
    force_pdf   = request.args.get("force_pdf") == "1"   # force pdfminer
    force_ocr   = request.args.get("force_ocr") == "1"   # force OCR

    force_mode = "pdf" if force_pdf else ("ocr" if force_ocr else None)

    try:
        text, source_tag = get_text_from_upload(fs, force_mode=force_mode)
        text = normalize_for_ocr(text)  # normalize before parsing

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
    # Renders templates/index.html (drag & drop UI)
    return render_template("index.html")

@app.route("/<path:path>")
def fallback(path):
    try:
        return render_template("index.html")
    except Exception:
        return jsonify({"ok": True, "route": path})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", os.environ.get("PORT", 8080)))
    app.run(host="0.0.0.0", port=int(port))