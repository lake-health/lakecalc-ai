import io
import os
import json
import re
from collections import OrderedDict

from flask import Flask, jsonify, request, render_template, send_file

# -------- Optional LLM fallback (OpenAI) --------
ENABLE_LLM = os.environ.get("ENABLE_LLM", "0").strip() in {"1", "true", "yes", "on"}
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini").strip()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
openai_client = None
if ENABLE_LLM and OPENAI_API_KEY:
    try:
        from openai import OpenAI
        openai_client = OpenAI(api_key=OPENAI_API_KEY)
    except Exception as e:
        # If OpenAI isn't available, just run without LLM
        openai_client = None
        ENABLE_LLM = False

# -------- PDF text extraction --------
import pdfplumber

APP_VERSION = "5.1 (Universal Parser + LLM fallback)"


app = Flask(__name__, static_folder='static', template_folder='templates')


def normalize(text: str) -> str:
    """Normalize weird glyphs/diacritics that commonly show up in these exports."""
    if not text:
        return ""
    # Greek mu variants, degree symbols, odd hyphens, commas vs dots
    rep = {
        "µ": "µ", "μ": "µ", "u": "µ",  # we prefer the micro sign "µ"
        "º": "°", "˚": "°", "o": "°",
        "–": "-", "—": "-",
    }
    for k, v in rep.items():
        text = text.replace(k, v)
    # Collapse multiple spaces/newlines
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def extract_pdf_halves(pdf_bytes: bytes):
    """
    Return (full_text, left_text, right_text, debug)
    We split each page at the mid x between margins, collect words by x center.
    """
    full_text_parts = []
    left_parts = []
    right_parts = []
    debug = {"strategy": "pdf_layout_split + coord_harvest"}

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        x_mids = []
        for page in pdf.pages:
            # page.extract_words returns words with x0, x1 — we use the center
            words = page.extract_words(use_text_flow=True, keep_blank_chars=False)
            mid = page.width / 2.0
            x_mids.append(mid)

            left_words = []
            right_words = []

            for w in words:
                x_center = (w["x0"] + w["x1"]) / 2.0
                if x_center <= mid:
                    left_words.append(w["text"])
                else:
                    right_words.append(w["text"])

            # Build line-ish strings (simple join is usually sufficient on these exports)
            left_parts.append(" ".join(left_words))
            right_parts.append(" ".join(right_words))

            # Full text (page-wise text)
            full_text_parts.append(page.extract_text() or "")

        debug["x_mid"] = sum(x_mids) / max(1, len(x_mids))

    full_text = normalize("\n\n".join(full_text_parts))
    left_text = normalize("\n\n".join(left_parts))
    right_text = normalize("\n\n".join(right_parts))

    debug["left_len"] = len(left_text)
    debug["right_len"] = len(right_text)
    debug["left_preview"] = left_text[:900]
    debug["right_preview"] = right_text[:900]
    return full_text, left_text, right_text, debug


# ---------------- Parsing ----------------

MM = r"-?\d{1,2}(?:[\.,]\d{1,2})?\s*mm"
UM = r"\d{2,4}\s*(?:µm|um)"
DIOP = r"-?\d{1,2}(?:[\.,]\d{1,2})?\s*D"
AXIS_INLINE = r"@\s*(\d{1,3})\s*°"
AXIS_NEXTLINE = r"(?:^|\n)\s*(\d{1,3})\s*°"

def _first(pattern, text, flags=0):
    m = re.search(pattern, text, flags)
    return m.group(0) if m else ""

def _first_group(pattern, text, flags=0):
    m = re.search(pattern, text, flags)
    return m.group(1) if m else ""

def _axis_after(pos, text):
    """Find axis number either inline '@ 100°' or on the next few tokens/line breaks."""
    tail = text[pos: pos + 80]
    m = re.search(AXIS_INLINE, tail)
    if m:
        return m.group(1)
    m = re.search(AXIS_NEXTLINE, tail)
    if m:
        return m.group(1)
    return ""


def parse_eye_block(text: str):
    """
    Parse a single eye block (left column or right column).
    Return an OrderedDict with fields in the order requested.
    """
    out = OrderedDict()
    out["source"] = "IOL Master 700"  # default/assumed
    out["axial_length"] = ""
    out["acd"] = ""
    out["k1"] = ""
    out["k2"] = ""
    out["ak"] = ""
    out["wtw"] = ""
    out["cct"] = ""
    out["lt"] = ""

    t = text

    # Straight pulls
    out["axial_length"] = _first(rf"AL\s*:\s*({MM})", t, re.I) or _first(rf"\b({MM})\b(?=.*\bAL\b)", t, re.I)
    out["acd"]          = _first(rf"ACD\s*:\s*({MM})", t, re.I) or _first(rf"\b({MM})\b(?=.*\bACD\b)", t, re.I)
    out["lt"]           = _first(rf"LT\s*:\s*({MM})", t, re.I)  or _first(rf"\b({MM})\b(?=.*\bLT\b)", t, re.I)
    out["wtw"]          = _first(rf"WTW\s*:\s*({MM})", t, re.I)

    # CCT (µm) – accept either Greek µ or 'um'
    out["cct"]          = _first(rf"CCT\s*:\s*({UM})", t, re.I)
    if not out["cct"]:
        # Sometimes "CCT:" is near, value is on next token
        m = re.search(r"CCT\s*:\s*", t, re.I)
        if m:
            after = t[m.end(): m.end() + 40]
            m2 = re.search(rf"\b{UM}\b", after, re.I)
            if m2:
                out["cct"] = m2.group(0)

    # K1 / K2 / AK including axis possibly in the next line(s)
    for label, key in (("K1", "k1"), ("K2", "k2")):
        m = re.search(rf"{label}\s*:\s*({DIOP})", t, re.I)
        if m:
            base = m.group(1)
            axis = _axis_after(m.end(1), t)
            out[key] = f"{base} @{axis}°" if axis else base

    # ΔK or AK (cylinder)
    m = re.search(rf"(?:ΔK|AK)\s*:\s*({DIOP})", t, re.I)
    if m:
        base = m.group(1)
        axis = _axis_after(m.end(1), t)
        out["ak"] = f"{base} @{axis}°" if axis else base

    # SD row just after K lines (optionally append)
    # We attach SD only if present immediately after the diopter lines
    def attach_sd(label, key):
        if out[key]:
            # Look around the label region
            mm = re.search(rf"{label}\s*:\s*{DIOP}.*?(?:SD\s*:\s*([0-9][\.,]?\d*)\s*D)", t, re.I | re.S)
            if mm:
                sd = mm.group(1).replace(",", ".")
                out[key] = f"{out[key]} (SD {sd} D)"

    attach_sd("K1", "k1")
    attach_sd("K2", "k2")
    attach_sd("(?:ΔK|AK)", "ak")

    # Tidy formats (prefer comma for decimals as in sample)
    def fix_commas(val):
        if not val:
            return val
        val = re.sub(r"(\d)\.(\d)", r"\1,\2", val)
        return re.sub(r"\s+", " ", val).strip()

    for k in list(out.keys()):
        out[k] = fix_commas(out[k])

    return out


def merge_with_llm(eye_text: str, current: OrderedDict, llm_stats: dict):
    """If any field is missing, ask the LLM to fill ONLY the missing ones from eye_text."""
    if not (ENABLE_LLM and openai_client):
        return current

    missing = [k for k, v in current.items() if k != "source" and not v]
    if not missing:
        return current

    system = (
        "You extract ophthalmology measurements from a raw IOLMaster-like report. "
        "Return a strict JSON object with ONLY the keys you can confidently fill among: "
        "['axial_length','acd','k1','k2','ak','wtw','cct','lt'].\n"
        "- Values should include units exactly as shown in the text (mm, µm, D) and axis with ' @ ###°' if present.\n"
        "- Do not guess; if a field isn't present, omit it from the JSON."
    )
    user = f"TEXT (one eye column):\n```\n{eye_text}\n```\nExtract the fields."

    try:
        resp = openai_client.chat.completions.create(
            model=LLM_MODEL,
            temperature=0,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content
        data = json.loads(content)

        # Merge only the missing keys
        for k in missing:
            if k in data and data[k]:
                current[k] = data[k]

        # minimal accounting info (optional)
        llm_stats["llm_calls"] = llm_stats.get("llm_calls", 0) + 1
    except Exception:
        # If anything goes wrong, we just keep the original
        pass

    return current


def structure_output(left_text: str, right_text: str, debug: dict, include_llm=True):
    # Heuristic mapping: left column is OD, right column is OS (matches your sample)
    debug["mapping"] = "OD<-left, OS<-right (default)"

    result = OrderedDict()
    result["OD"] = parse_eye_block(left_text)
    result["OS"] = parse_eye_block(right_text)

    # LLM fallback for missing fields
    llm_stats = {}
    if include_llm:
        result["OD"] = merge_with_llm(left_text, result["OD"], llm_stats)
        result["OS"] = merge_with_llm(right_text, result["OS"], llm_stats)
    if llm_stats:
        debug.update(llm_stats)

    return result


# ---------------- Routes ----------------

@app.route("/")
def index():
    # Simple UI shipped inline so you can keep working without extra files
    return """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>LakeCalc.ai — IOL Parser</title>
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Inter, Arial; padding: 28px; max-width: 1100px; margin: 0 auto; }
    .box { border: 2px dashed #bbb; padding: 16px; border-radius: 10px; margin: 10px 0 20px; color: #666; }
    pre { background:#0b0b0b; color:#f1f1f1; padding:18px; border-radius:10px; overflow:auto; }
    button { padding:10px 16px; border-radius:8px; border:0; background:#1c64f2; color:white; font-weight:600; }
    label { margin-right:14px; }
    .row { margin: 10px 0 18px; }
  </style>
</head>
<body>
  <h1>LakeCalc.ai — IOL Parser</h1>

  <div class="row">
    <input id="file" type="file" accept=".pdf,.png,.jpg,.jpeg"/>
    <button id="go">Upload & Parse</button>
  </div>

  <div class="row">
    <label><input type="checkbox" id="include_raw"> Include raw text preview</label>
    <label><input type="checkbox" id="debug"> Debug</label>
  </div>

  <div class="box">Drag & drop a PDF/image here</div>

  <div class="row">Health: <a href="/api/health" target="_blank">/api/health</a></div>
  <h3>Response</h3>
  <pre id="out">{}</pre>

<script>
const box = document.querySelector('.box');
box.addEventListener('dragover', e => { e.preventDefault(); box.style.borderColor='#1c64f2'; });
box.addEventListener('dragleave', e => { e.preventDefault(); box.style.borderColor='#bbb'; });
box.addEventListener('drop', async e => {
  e.preventDefault(); box.style.borderColor='#bbb';
  const f = e.dataTransfer.files[0]; if (!f) return;
  await send(f);
});
document.getElementById('go').onclick = async () => {
  const f = document.getElementById('file').files[0]; if (!f) return;
  await send(f);
}
async function send(file) {
  const form = new FormData();
  form.append('file', file);
  form.append('include_raw', document.getElementById('include_raw').checked ? '1' : '0');
  form.append('debug', document.getElementById('debug').checked ? '1' : '0');
  const res = await fetch('/api/parse-file', { method:'POST', body:form });
  const data = await res.json();
  document.getElementById('out').textContent = JSON.stringify(data, null, 2);
}
</script>
</body>
</html>
    """


@app.route("/api/health")
def health():
    return jsonify({
        "status": "running",
        "version": APP_VERSION,
        "llm_enabled": ENABLE_LLM and bool(openai_client),
        "llm_model": LLM_MODEL if (ENABLE_LLM and openai_client) else None
    })


@app.route("/api/parse-file", methods=["POST"])
def parse_file():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "No selected file"}), 400

    include_raw = request.form.get("include_raw") in {"1", "true", "yes", "on"}
    debug_flag = request.form.get("debug") in {"1", "true", "yes", "on"}

    try:
        b = f.read()
        full_text, left_text, right_text, dbg = extract_pdf_halves(b)

        structured = structure_output(left_text, right_text, dbg, include_llm=True)

        payload = OrderedDict()
        if debug_flag:
            payload["debug"] = dbg
        payload["filename"] = f.filename
        if include_raw:
            payload["raw_text_preview"] = (full_text or "")[:1200]
        payload["structured"] = structured
        payload["text_source"] = "pdf_text"

        return jsonify(payload)
    except Exception as e:
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
