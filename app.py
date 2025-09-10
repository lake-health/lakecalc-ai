
# app.py — LakeCalc.ai parser v4.1 (FULL DROP-IN)
# - PDF-first text extraction with OCR fallback (Google Vision)
# - Symbol and OCR quirks normalization
# - Two-column PDF split using pdfminer layout (left/right eye lanes)
# - Coordinate-aware harvest (per-column) to rescue values
# - Primary regex parsing (values + SD + axes)
# - Axis backfill from label zones if axes missing
# - Always attach SD to matching fields
# - No CCT copying between eyes
# - Stable output order with 'source' first
# - Debug payload showing previews and strategy

import os, io, re, json
from io import BytesIO
from typing import Optional, Tuple, Dict, List
from statistics import median

from flask import Flask, request, jsonify, render_template

# PDF parsing
from pdfminer.high_level import extract_text as pdfminer_extract_text, extract_pages
from pdfminer.layout import LTTextBox, LTTextBoxHorizontal, LTTextLine, LTTextLineHorizontal, LAParams

# OCR and image conversion
from google.cloud import vision
from pdf2image import convert_from_bytes

app = Flask(__name__, static_folder='static', template_folder='templates')

# =========================
# Google Vision (OCR)
# =========================
vision_client: Optional[vision.ImageAnnotatorClient] = None
try:
    creds_json = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    if creds_json:
        from google.oauth2 import service_account
        info = json.loads(creds_json)
        credentials = service_account.Credentials.from_service_account_info(info)
        vision_client = vision.ImageAnnotatorClient(credentials=credentials)
    elif os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        vision_client = vision.ImageAnnotatorClient()
    else:
        print("INFO: Vision credentials not set. OCR fallback disabled.")
except Exception as e:
    print(f"Vision init error: {e}")

# =========================
# Utilities
# =========================
def clamp_axis(val: str) -> str:
    """Clamp axis to 0-180 if numeric; preserve original if not parseable."""
    m = re.search(r"@\s*(\d{1,3})\s*(?:°|º|o)\b", val)
    if not m: 
        return val
    n = int(m.group(1))
    n = max(0, min(180, n))
    return re.sub(r"@\s*\d{1,3}\s*(?:°|º|o)\b", f"@ {n}°", val)

def normalize_symbols(text: str) -> str:
    if not text:
        return text
    t = text
    # Normalize micro and degrees
    t = t.replace("μ", "µ")
    t = re.sub(r"(?i)\bum\b", "µm", t)
    t = re.sub(r"(?i)(\d)\s*um\b", r"\1 µm", t)
    t = t.replace("º", "°")
    # Replace letter 'o' used as degree mark in some exports
    t = re.sub(r"@\s*(\d{1,3})\s*o\b", r"@ \1°", t, flags=re.IGNORECASE)
    t = re.sub(r"°\s*°+", "°", t)
    # Delta
    t = t.replace("∆", "Δ")
    # Collapse excessive spaces
    t = re.sub(r"[ \t]+", " ", t)
    return t

def normalize_for_ocr(text: str) -> str:
    """Fix common line-break patterns from OCR/PDF text extraction."""
    t = text.replace("\u00A0", " ")
    # Stack-broken metric triplets: label on one line, number next, unit next
    t = re.sub(
        r"(?mi)^(AL|ACD|LT|WTW|CCT)\s*:\s*\n\s*([-\d.,]+)\s*\n\s*(mm|[µμ]m|um)\b",
        r"\1: \2 \3", t,
    )
    # Stack-broken diopter values: label, number, D
    t = re.sub(
        r"(?mi)^(K1|K2|K|AK|ΔK)\s*:\s*\n\s*([-\d.,]+)\s*\n\s*D\b",
        r"\1: \2 D", t,
    )
    # Scattered axis: "@", then digits, then "°" over multiple lines (various orders)
    t = re.sub(r"@\s*(?:\r?\n|\s)*(?:[°ºo])\s*(?:\r?\n|\s)*?(\d{1,3})\b", r"@ \1°", t)
    t = re.sub(r"@\s*(?:\r?\n|\s)*(\d{1,3})\s*(?:\r?\n|\s)*(?:[°ºo])\b", r"@ \1°", t)
    t = re.sub(r"(?:[°ºo])\s*(?:\r?\n|\s)*?(\d{1,3})\b", r" \1°", t)
    return normalize_symbols(t)

# =========================
# PDF text extraction
# =========================
def extract_pdf_text_safe(file_bytes: bytes) -> str:
    try:
        bio = BytesIO(file_bytes)
        text = pdfminer_extract_text(bio) or ""
        text = re.sub(r"[ \t]+\n", "\n", text).strip()
        return normalize_symbols(text)
    except Exception as e:
        print(f"[WARN] pdfminer failed: {e}")
        return ""

def ocr_pdf_to_text(pdf_bytes: bytes) -> str:
    if not vision_client:
        raise RuntimeError("Vision client not initialized for OCR fallback.")
    pages_txt = []
    for img in convert_from_bytes(pdf_bytes, fmt="jpeg"):
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        image = vision.Image(content=buf.getvalue())
        resp = vision_client.text_detection(image=image)
        if resp.error.message:
            raise RuntimeError(f"Vision API Error: {resp.error.message}")
        raw = resp.text_annotations[0].description if resp.text_annotations else ""
        pages_txt.append(normalize_symbols(raw))
    return "\n\n--- Page ---\n\n".join(pages_txt).strip()

def ocr_image_to_text(image_bytes: bytes) -> str:
    if not vision_client:
        raise RuntimeError("Vision client not initialized; cannot OCR image.")
    image = vision.Image(content=image_bytes)
    resp = vision_client.text_detection(image=image)
    if resp.error.message:
        raise RuntimeError(f"Vision API Error: {resp.error.message}")
    raw = resp.text_annotations[0].description if resp.text_annotations else ""
    return normalize_symbols(raw)

def get_text_from_upload(fs, force_mode: Optional[str] = None) -> Tuple[str, str, Optional[bytes]]:
    name = (fs.filename or "").lower()
    is_pdf = name.endswith(".pdf")
    file_bytes = fs.read()
    if is_pdf:
        if force_mode == "pdf":
            return extract_pdf_text_safe(file_bytes), "pdf_text", file_bytes
        if force_mode == "ocr":
            return ocr_pdf_to_text(file_bytes), "ocr_pdf", file_bytes
        txt = extract_pdf_text_safe(file_bytes)
        return (txt, "pdf_text", file_bytes) if txt else (ocr_pdf_to_text(file_bytes), "ocr_pdf", file_bytes)
    if force_mode == "ocr" or not force_mode:
        return ocr_image_to_text(file_bytes), "ocr_image", None
    return "", "unknown", None

# =========================
# Column split + coordinate harvest
# =========================
def split_pdf_columns_with_layout(file_bytes: bytes) -> Tuple[str, str, dict]:
    """Split by global median x-center; return left/right text and debug."""
    try:
        bio = BytesIO(file_bytes)
        laparams = LAParams(line_margin=0.15, char_margin=2.0, word_margin=0.1)
        x_centers = []
        for page_layout in extract_pages(bio, laparams=laparams):
            for element in page_layout:
                if isinstance(element, (LTTextBoxHorizontal, LTTextBox, LTTextLineHorizontal, LTTextLine)):
                    txt = element.get_text()
                    if not txt or not txt.strip():
                        continue
                    x0, y0, x1, y1 = element.bbox
                    xc = 0.5*(x0+x1)
                    x_centers.append(xc)
        if not x_centers:
            raise RuntimeError("No text boxes found for layout split.")
        x_mid = median(x_centers)

        bio2 = BytesIO(file_bytes)
        left_chunks, right_chunks = [], []
        for page_layout in extract_pages(bio2, laparams=laparams):
            for element in page_layout:
                if isinstance(element, (LTTextBoxHorizontal, LTTextBox, LTTextLineHorizontal, LTTextLine)):
                    txt = element.get_text()
                    if not txt or not txt.strip():
                        continue
                    x0, y0, x1, y1 = element.bbox
                    xc = 0.5*(x0+x1)
                    if xc <= x_mid:
                        left_chunks.append(txt)
                    else:
                        right_chunks.append(txt)

        left_text = normalize_for_ocr("".join(left_chunks))
        right_text = normalize_for_ocr("".join(right_chunks))

        dbg = {
            "strategy": "pdf_layout_split + coord_harvest",
            "x_mid": x_mid,
            "left_len": len(left_text),
            "right_len": len(right_text),
            "left_preview": left_text[:600],
            "right_preview": right_text[:600],
        }
        return left_text, right_text, dbg
    except Exception as e:
        return "", "", {"strategy": "split_failed", "error": str(e)}

# =========================
# Parsing helpers
# =========================
LABEL_BOUNDARY = re.compile(r"(?mi)^(?:AL|ACD|CCT|LT|WTW|K1|K2|AK|ΔK)\s*:\s*$")

def _value_has_axis(v: str) -> bool:
    return bool(re.search(r"@\s*\d{1,3}\s*(?:°|º|o)\b", v or ""))

def _pick_axis_from_segment(seg: str) -> Optional[str]:
    m = re.search(r"@\s*(\d{2,3})\s*(?:°|º|o)\b", seg)
    if m: return f" @ {m.group(1)}°"
    m = re.search(r"@\s*(\d)\s*(?:°|º|o)\b", seg)
    if m: return f" @ {m.group(1)}°"
    lines = seg.splitlines()
    for i, ln in enumerate(lines):
        if "@" in ln:
            chunk = "\n".join(lines[i:i+3])
            m = re.search(r"@\s*(\d{1,3})\s*(?:°|º|o)\b", chunk)
            if m: return f" @ {m.group(1)}°"
    m = re.search(r"\b(\d{2,3})\s*(?:°|º|o)\b", seg)
    if m: return f" @ {m.group(1)}°"
    m = re.search(r"\b(\d)\s*(?:°|º|o)\b", seg)
    if m: return f" @ {m.group(1)}°"
    return None

def backfill_axes_from_labels(eye_text: str, data: dict) -> dict:
    out = dict(data)
    def fill_one(label: str, key: str):
        val = out.get(key, "")
        if not val or _value_has_axis(val): return
        m = re.search(rf"(?mi)^{label}\s*:\s*$", eye_text) or re.search(rf"(?mi)\b{label}\s*:\s*", eye_text)
        if not m: return
        start = m.end()
        nxt = LABEL_BOUNDARY.search(eye_text, pos=start)
        end = nxt.start() if nxt else min(len(eye_text), start+400)
        seg = eye_text[start:end]
        axis = _pick_axis_from_segment(seg)
        if axis: out[key] = val.strip() + axis
    fill_one("K1","k1"); fill_one("K2","k2"); fill_one("(?:AK|ΔK|K(?!\\s*1|\\s*2))","ak")
    return out

def _first(pattern: str, text: str) -> str:
    m = re.search(pattern, text)
    return m.group(1).strip() if m else ""

def attach_sd(eye_text: str, data: Dict[str,str]) -> Dict[str,str]:
    sd_vals = re.findall(r"(?mi)\bSD\s*:\s*([\-\d.,]+)\s*(mm|[µμ]m|um|D)\b", eye_text)
    if not sd_vals:
        return data
    candidates = [{"value": f"{v} {u}".replace("um","µm"), "unit": u.lower()} for (v,u) in sd_vals]

    def pick(unit: str) -> Optional[str]:
        unit = unit.lower()
        for c in candidates:
            if c["unit"] == unit:
                return c["value"]
        if unit == "µm":
            for c in candidates:
                if c["unit"] in ("µm","um"):
                    return c["value"]
        return None

    out = dict(data)
    field_unit = {
        "axial_length": "mm",
        "acd": "mm",
        "lt": "mm",
        "cct": "µm",
        "wtw": "mm",
        "k1": "D",
        "k2": "D",
        "ak": "D",
    }
    for k,unit in field_unit.items():
        if k in out and out[k]:
            sd = pick(unit)
            if sd:
                out[k] = f"{out[k]} (SD {sd})"
    return out

def parse_eye_block(text: str) -> Dict[str, str]:
    t = normalize_for_ocr(text)
    MM = r"[\-\d.,]+\s*mm"
    UM = r"[\-\d.,]+\s*(?:µm|um)"
    D  = r"[\-\d.,]+\s*D(?:\s*@\s*\d{1,3}\s*(?:°|º|o))?"

    out = {
        "source": "IOL Master 700",
        "axial_length": _first(rf"(?mi)\bAL\s*:\s*({MM})", t),
        "acd":          _first(rf"(?mi)\bACD\s*:\s*({MM})", t),
        "lt":           _first(rf"(?mi)\bLT\s*:\s*({MM})", t),
        "cct":          _first(rf"(?mi)\bCCT\s*:\s*({UM})", t),
        "wtw":          _first(rf"(?mi)\bWTW\s*:\s*({MM})", t),
        "k1":           _first(rf"(?mi)\bK1\s*:\s*({D})", t),
        "k2":           _first(rf"(?mi)\bK2\s*:\s*({D})", t),
        "ak":           _first(rf"(?mi)\b(?:AK|ΔK|K(?!\s*1|\s*2))\s*:\s*({D})", t),
    }

    # Axis backfill
    out = backfill_axes_from_labels(t, out)

    # Clamp axes
    for k in ("k1","k2","ak"):
        if out.get(k):
            out[k] = clamp_axis(out[k])

    # Always attach SD
    out = attach_sd(t, out)

    # Clean
    for k,v in list(out.items()):
        if v:
            out[k] = re.sub(r"\s+", " ", v).strip()

    return out

def enforce_field_order(d: Dict[str,str]) -> Dict[str,str]:
    order = ["source","axial_length","acd","k1","k2","ak","wtw","cct","lt"]
    return {k: d.get(k,"") for k in order if d.get(k,"")}

def parse_iol_from_text(full_text: str, pdf_bytes: Optional[bytes]) -> Tuple[Dict[str,Dict[str,str]], Dict]:
    normalized = normalize_for_ocr(full_text)
    left_txt = right_txt = ""
    dbg = {"strategy": "text_only"}

    if pdf_bytes:
        lt, rt, dbg = split_pdf_columns_with_layout(pdf_bytes)
        if lt or rt:
            left_txt, right_txt = lt, rt
        else:
            left_txt = normalized
            right_txt = normalized
            dbg["strategy"] = "text_only (layout split failed)"
    else:
        left_txt = normalized
        right_txt = normalized
        dbg["strategy"] = "text_only (no pdf bytes)"

    mapping = "OD<-left, OS<-right (default)"
    dbg["mapping"] = mapping
    dbg["left_len"] = len(left_txt)
    dbg["right_len"] = len(right_txt)
    dbg["left_preview"] = left_txt[:600]
    dbg["right_preview"] = right_txt[:600]

    od_raw = parse_eye_block(left_txt)
    os_raw = parse_eye_block(right_txt)

    od = enforce_field_order(od_raw)
    os = enforce_field_order(os_raw)

    structured = {"OD": od, "OS": os}
    return structured, dbg

# =========================
# Routes
# =========================
@app.route("/api/parse-file", methods=["POST"])
def parse_file():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400
    fs = request.files["file"]
    if fs.filename == "":
        return jsonify({"error": "No selected file"}), 400

    force = request.args.get("mode")  # pdf | ocr | None
    debug_flag = request.args.get("debug", "0") == "1"

    try:
        fs.stream.seek(0)
        text, source, pdf_bytes = get_text_from_upload(fs, force_mode=force)
        structured, dbg = parse_iol_from_text(text, pdf_bytes)
        payload = {
            "filename": fs.filename,
            "raw_text_preview": text[:1000],
            "structured": structured,
            "text_source": source,
        }
        if debug_flag:
            payload["debug"] = dbg
        return jsonify(payload)
    except Exception as e:
        print(f"Error in /api/parse-file: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/health")
def health():
    return jsonify({"status": "running", "version": "4.1", "ocr_enabled": bool(vision_client)})

@app.route("/")
def index():
    try:
        return render_template("index.html")
    except Exception:
        return (
            """
            <!doctype html>
            <html>
              <head>
                <meta charset="utf-8" />
                <meta name="viewport" content="width=device-width, initial-scale=1" />
                <title>LakeCalc.ai — Parser v4.1</title>
                <style>
                  body{font-family:system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; padding:24px; max-width:900px; margin:auto;}
                  .card{border:1px solid #ddd; border-radius:10px; padding:20px;}
                  .row{margin-top:14px;}
                  pre{white-space:pre-wrap; background:#fafafa; border:1px solid #eee; padding:12px; border-radius:6px;}
                  .muted{color:#777;}
                </style>
              </head>
              <body>
                <h1>LakeCalc.ai — Parser v4.1</h1>
                <div class="card">
                  <form id="f">
                    <div class="row">
                      <label>File (PDF/JPG/PNG): <input type="file" name="file" required /></label>
                    </div>
                    <div class="row">
                      <label>Mode:
                        <select name="mode">
                          <option value="">Auto</option>
                          <option value="pdf">Force PDF text</option>
                          <option value="ocr">Force OCR</option>
                        </select>
                      </label>
                      <label style="margin-left:16px;">
                        <input type="checkbox" name="debug" value="1" /> Debug
                      </label>
                    </div>
                    <div class="row">
                      <button>Parse</button>
                    </div>
                  </form>
                  <div id="out" class="row"></div>
                </div>

                <script>
                const f = document.getElementById('f');
                const out = document.getElementById('out');
                f.addEventListener('submit', async (e) => {
                  e.preventDefault();
                  out.innerHTML = '<p class="muted">Parsing…</p>';
                  const fd = new FormData(f);
                  const params = new URLSearchParams();
                  const mode = fd.get('mode'); if (mode) params.set('mode', mode);
                  if (fd.get('debug')) params.set('debug','1');
                  const res = await fetch('/api/parse-file?' + params.toString(), { method:'POST', body: fd });
                  const j = await res.json();
                  out.innerHTML = '<pre>'+ JSON.stringify(j, null, 2) +'</pre>';
                });
                </script>
              </body>
            </html>
            """,
            200,
            {"Content-Type": "text/html; charset=utf-8"},
        )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
