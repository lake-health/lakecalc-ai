# app.py — LakeCalc.ai parser v3.3
import os, io, re, unicodedata
from collections import OrderedDict
from io import BytesIO

from flask import Flask, request, jsonify, render_template

# PDF text & geometry
from pdfminer.high_level import extract_text as pdfminer_extract_text, extract_pages
from pdfminer.layout import (
    LTTextBox, LTTextBoxHorizontal, LTTextLine, LTTextLineHorizontal, LAParams
)

# OCR fallback
from google.cloud import vision
from pdf2image import convert_from_bytes

app = Flask(__name__, static_folder='static', template_folder='templates')

# =========================
# Google Vision (OCR)
# =========================
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
        print("INFO: Vision credentials not set. OCR fallback disabled for images.")
except Exception as e:
    print(f"Vision init error: {e}")

# =========================
# Text extraction (PDF-first, OCR fallback)
# =========================
def try_pdf_text_extract(pdf_bytes: bytes) -> str:
    try:
        text = pdfminer_extract_text(BytesIO(pdf_bytes)) or ""
        return re.sub(r"[ \t]+\n", "\n", text).strip()
    except Exception as e:
        print(f"pdfminer text error: {e}")
        return ""

def ocr_pdf_to_text(pdf_bytes: bytes) -> str:
    if not vision_client:
        raise RuntimeError("Vision client not initialized for OCR fallback.")
    pages_txt = []
    for img in convert_from_bytes(pdf_bytes, fmt="jpeg"):
        buf = io.BytesIO(); img.save(buf, format="JPEG")
        image = vision.Image(content=buf.getvalue())
        resp = vision_client.text_detection(image=image)
        if resp.error.message:
            raise RuntimeError(f"Vision API Error: {resp.error.message}")
        pages_txt.append(resp.text_annotations[0].description if resp.text_annotations else "")
    return "\n\n--- Page ---\n\n".join(pages_txt).strip()

def ocr_image_to_text(image_bytes: bytes) -> str:
    if not vision_client:
        raise RuntimeError("Vision client not initialized; cannot OCR image.")
    image = vision.Image(content=image_bytes)
    resp = vision_client.text_detection(image=image)
    if resp.error.message:
        raise RuntimeError(f"Vision API Error: {resp.error.message}")
    return (resp.text_annotations[0].description if resp.text_annotations else "").strip()

def get_text_from_upload(fs, force_mode: str | None = None):
    """
    Returns (text, source_tag, pdf_bytes_or_None).
    source_tag: 'pdf_text'|'ocr_pdf'|'ocr_image'
    """
    name = (fs.filename or "").lower()
    is_pdf = name.endswith(".pdf")

    if is_pdf:
        pdf_bytes = fs.read()
        if force_mode == "pdf":
            return try_pdf_text_extract(pdf_bytes), "pdf_text", pdf_bytes
        if force_mode == "ocr":
            return ocr_pdf_to_text(pdf_bytes), "ocr_pdf", pdf_bytes
        text = try_pdf_text_extract(pdf_bytes)
        if text:
            return text, "pdf_text", pdf_bytes
        return ocr_pdf_to_text(pdf_bytes), "ocr_pdf", pdf_bytes

    # images
    image_bytes = fs.read()
    return ocr_image_to_text(image_bytes), "ocr_image", None

# =========================
# Normalization (OCR/PDF quirks)
# =========================
def normalize_for_ocr(text: str) -> str:
    t = text.replace("\u00A0", " ")

    # Join AL/ACD/LT/WTW/CCT split across lines: "AL:\n23,73\nmm" -> "AL: 23,73 mm"
    t = re.sub(
        r"(?mi)^(AL|ACD|LT|WTW|CCT)\s*:\s*\n\s*([-\d.,]+)\s*\n\s*(mm|[µμ]m|um)\b",
        r"\1: \2 \3",
        t
    )

    # Join K* value + 'D' split across lines
    t = re.sub(
        r"(?mi)^(K1|K2|K|AK|ΔK)\s*:\s*\n\s*([-\d.,]+)\s*\n\s*D\b",
        r"\1: \2 D",
        t
    )

    # Normalize axes like "@ \n ° \n 10" / "@ \n 10 \n °" -> "@ 10°"
    t = re.sub(r"@\s*(?:\r?\n|\s)*(?:[°ºo])\s*(?:\r?\n|\s)*?(\d{1,3})\b", r"@ \1°", t)
    t = re.sub(r"@\s*(?:\r?\n|\s)*(\d{1,3})\s*(?:\r?\n|\s)*(?:[°ºo])\b", r"@ \1°", t)

    # Degree then digits split across lines -> " 10°"
    t = re.sub(r"(?:[°ºo])\s*(?:\r?\n|\s)*?(\d{1,3})\b", r" \1°", t)

    # Collapse internal whitespace
    t = re.sub(r"[ \t]+", " ", t)

    return t

# =========================
# Controlled PT→EN localization (header clues only)
# =========================
def localize_pt_to_en(text: str) -> str:
    """
    Controlled localization: Portuguese → English for header clues ONLY.
    Does NOT touch OD/OS/OE tokens, numbers, labels, or units.
    """
    t = text
    replacements = [
        (r"\b(direita|olho\s+direito)\b", "RIGHT"),
        (r"\b(esquerda|esquerdo|olho\s+esquerdo)\b", "LEFT"),
        # (optional) benign UI words
        (r"\bpaciente\b", "PATIENT"),
        (r"\ban[aá]lise\b", "ANALYSIS"),
        (r"\bbranco a branco\b", "WHITE TO WHITE"),
    ]
    for pat, repl in replacements:
        t = re.sub(pat, repl, t, flags=re.IGNORECASE)
    # Never replace 'os' or 'olhos'
    return t

# =========================
# PDF layout split: left/right columns
# =========================
def pdf_split_left_right(pdf_bytes: bytes) -> dict:
    """
    Return {"left": "...", "right": "..."} by splitting each page using its mid X.
    Concatenate left texts for all pages, same for right.
    """
    left_chunks, right_chunks = [], []
    laparams = LAParams(all_texts=True)
    try:
        for page_layout in extract_pages(BytesIO(pdf_bytes), laparams=laparams):
            page_width = getattr(page_layout, "width", None)
            if page_width is None:
                xs = []
                for el in page_layout:
                    if hasattr(el, "bbox"):
                        xs += [el.bbox[0], el.bbox[2]]
                page_width = max(xs) if xs else 1000.0
            midx = page_width / 2.0

            blobs = []
            for el in page_layout:
                if isinstance(el, (LTTextBox, LTTextBoxHorizontal, LTTextLine, LTTextLineHorizontal)):
                    x0, y0, x1, y1 = el.bbox
                    x_center = (x0 + x1) / 2.0
                    txt = el.get_text()
                    if not txt or not txt.strip():
                        continue
                    blobs.append((y1, txt, x_center < midx))

            blobs.sort(key=lambda t: -t[0])  # top→bottom
            left_txt = "".join([b[1] for b in blobs if b[2]])
            right_txt = "".join([b[1] for b in blobs if not b[2]])
            left_chunks.append(left_txt)
            right_chunks.append(right_txt)
    except Exception as e:
        print(f"pdf layout split error: {e}")

    return {"left": "\n".join(left_chunks).strip(), "right": "\n".join(right_chunks).strip()}

# =========================
# Patterns & parsing helpers
# =========================
MM   = r"-?\d[\d.,]*\s*mm"
UM   = r"-?\d[\d.,]*\s*(?:[µμ]m|um)"  # accept µm and μm and um
DVAL = r"-?\d[\d.,]*\s*D"
LABEL_STOP = re.compile(r"(?:\r?\n|(?=(?:AL|ACD|CCT|LT|WTW|K1|K2|K|AK|ΔK)\s*:))", re.IGNORECASE)

PATTERNS = {
    "axial_length": re.compile(rf"(?mi)\bAL\s*:\s*({MM})"),
    "acd":          re.compile(rf"(?mi)\bACD\s*:\s*({MM})"),
    "cct":          re.compile(rf"(?mi)\bCCT\s*:\s*({UM})"),
    "lt":           re.compile(rf"(?mi)\bLT\s*:\s*({MM})"),
    "wtw":          re.compile(rf"(?mi)\bWTW\s*:\s*({MM})"),
    "k1":           re.compile(rf"(?mi)\bK1\s*:\s*({DVAL})"),
    "k2":           re.compile(rf"(?mi)\bK2\s*:\s*({DVAL})"),
    # ΔK / AK / K (but NOT K1/K2)
    "ak":           re.compile(rf"(?mi)\b(?:Δ\s*K|AK|K(?!\s*1|\s*2))\s*:\s*({DVAL})"),
}

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

def parse_eye_block(txt: str) -> dict:
    out = {"axial_length":"", "acd":"", "k1":"", "k2":"", "ak":"", "wtw":"", "cct":"", "lt":""}
    if not txt or not txt.strip():
        return out
    for key, pat in PATTERNS.items():
        for m in pat.finditer(txt):
            raw = re.sub(r"\s+", " ", m.group(1)).strip()
            if key in ("k1", "k2", "ak"):
                raw = re.sub(r"@\s*.*$", "", raw)  # drop trailing axis blob
                tail = txt[m.end(1): m.end(1) + 200]
                raw = (raw + harvest_axis(tail)).strip()
            if not out[key]:
                out[key] = raw
    return out

def has_measurements(d: dict) -> bool:
    return any(d.values())

# =========================
# Source detection
# =========================
def detect_source_label(text: str) -> str:
    if re.search(r"IOL\s*Master\s*700", text, re.IGNORECASE): return "IOL Master 700"
    if re.search(r"OCULUS\s+PENTACAM", text, re.IGNORECASE):   return "Pentacam"
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "Unknown")
    return first[:60]

# =========================
# Output ordering
# =========================
FIELD_ORDER = ["source", "axial_length", "acd", "k1", "k2", "ak", "wtw", "cct", "lt"]
def enforce_field_order(eye_dict: dict) -> OrderedDict:
    return OrderedDict((k, eye_dict.get(k, "")) for k in FIELD_ORDER)

# =========================
# Core controller (with debug)
# =========================
def parse_iol(norm_text: str, pdf_bytes: bytes | None, source_label: str, want_debug: bool = False):
    def fresh():
        return OrderedDict([
            ("source", source_label),
            ("axial_length", ""), ("acd", ""), ("k1", ""), ("k2", ""),
            ("ak", ""), ("wtw", ""), ("cct", ""), ("lt", "")
        ])
    result = {"OD": fresh(), "OS": fresh()}
    debug = {"strategy": "", "left_len": 0, "right_len": 0, "left_preview": "", "right_preview": "", "mapping": ""}

    left_txt = right_txt = None
    if pdf_bytes:
        try:
            cols = pdf_split_left_right(pdf_bytes)
            left_txt, right_txt = cols.get("left", ""), cols.get("right", "")
            debug["strategy"] = "pdf_layout_split"
            debug["left_len"] = len(left_txt or "")
            debug["right_len"] = len(right_txt or "")
        except Exception as e:
            print(f"layout split failed: {e}")

    if left_txt is not None and right_txt is not None:
        # Normalize & localize columns
        left_norm  = localize_pt_to_en(normalize_for_ocr(left_txt))
        right_norm = localize_pt_to_en(normalize_for_ocr(right_txt))
        if want_debug:
            debug["left_preview"]  = left_norm[:600]
            debug["right_preview"] = right_norm[:600]

        left_data  = parse_eye_block(left_norm)
        right_data = parse_eye_block(right_norm)

        def looks_od(s: str) -> bool:
            u = s.upper(); return bool(re.search(r"\bOD\b|\bO\s*D\b|RIGHT\b", u))
        def looks_os(s: str) -> bool:
            u = s.upper(); return bool(re.search(r"\bOS\b|\bO\s*S\b|\bOE\b|\bO\s*E\b|LEFT\b", u))

        left_is_od, left_is_os = looks_od(left_txt), looks_os(left_txt)
        right_is_od, right_is_os = looks_od(right_txt), looks_os(right_txt)

        if left_is_od and right_is_os:
            mapping = {"OD": left_data, "OS": right_data}; debug["mapping"] = "OD<-left, OS<-right (labels)"
        elif left_is_os and right_is_od:
            mapping = {"OD": right_data, "OS": left_data}; debug["mapping"] = "OD<-right, OS<-left (labels)"
        else:
            mapping = {"OD": left_data, "OS": right_data};  debug["mapping"] = "OD<-left, OS<-right (default)"

        # Only one side has data → assign to OD
        if not has_measurements(mapping["OD"]) and has_measurements(mapping["OS"]):
            mapping = {"OD": mapping["OS"], "OS": {"axial_length":"", "acd":"", "k1":"", "k2":"", "ak":"", "wtw":"", "cct":"", "lt":""}}
            debug["mapping"] += " | fallback: only one side had data → assigned to OD"

        for eye in ("OD","OS"):
            for k,v in mapping[eye].items():
                if v: result[eye][k] = v

        # Enforce output order
        result["OD"] = enforce_field_order(result["OD"])
        result["OS"] = enforce_field_order(result["OS"])

        return (result, debug) if want_debug else result

    # OCR image or no layout info → single block → OD
    single = localize_pt_to_en(normalize_for_ocr(norm_text))
    parsed = parse_eye_block(single)
    for k,v in parsed.items():
        if v: result["OD"][k] = v

    # Enforce output order
    result["OD"] = enforce_field_order(result["OD"])
    result["OS"] = enforce_field_order(result["OS"])

    debug["strategy"] = "ocr_single_block_to_OD"
    return (result, debug) if want_debug else result

# =========================
# Routes
# =========================
@app.route("/api/health")
def health():
    return jsonify({
        "status": "running",
        "version": "LakeCalc.ai parser v3.3 (layout split + PT→EN + µ/μ + ΔK/AK/K + ordered)",
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
    force_pdf   = request.args.get("force_pdf") == "1"
    force_ocr   = request.args.get("force_ocr") == "1"
    debug_flag  = request.args.get("debug") == "1"

    force_mode = "pdf" if force_pdf else ("ocr" if force_ocr else None)

    try:
        text, source_tag, pdf_bytes = get_text_from_upload(fs, force_mode=force_mode)
        norm_text = normalize_for_ocr(text)
        source_label = detect_source_label(norm_text)

        if raw_only:
            loc_preview = localize_pt_to_en(norm_text)
            return jsonify({
                "filename": fs.filename,
                "text_source": source_tag,
                "raw_text": loc_preview,
                "num_chars": len(loc_preview),
                "num_lines": loc_preview.count("\n") + 1
            })

        parsed, dbg = parse_iol(norm_text, pdf_bytes, source_label, want_debug=debug_flag) if debug_flag else (parse_iol(norm_text, pdf_bytes, source_label), None)

        if include_raw or debug_flag:
            payload = {
                "filename": fs.filename,
                "text_source": source_tag,
                "structured": parsed,
                "raw_text_preview": localize_pt_to_en(norm_text)[:1500]
            }
            if dbg is not None:
                payload["debug"] = dbg
            return jsonify(payload)

        return jsonify(parsed)

    except Exception as e:
        print(f"Error in /api/parse-file: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/")
def root():
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
