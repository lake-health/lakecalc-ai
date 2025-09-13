import os
import re
import json
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
from pdfminer.high_level import extract_text
import pytesseract
from PIL import Image
import fitz  # PyMuPDF

app = Flask(__name__)

def extract_text_from_pdf(path: str) -> str:
    try:
        return extract_text(path)
    except Exception:
        return ""

def extract_text_from_image(path: str) -> str:
    try:
        img = Image.open(path)
        return pytesseract.image_to_string(img, lang="eng+por")
    except Exception:
        return ""

def split_left_right(text: str) -> tuple[str,str]:
    mid = len(text)//2
    return text[:mid], text[mid:]

def parse_eye_block(text: str) -> dict:
    out = {}
    def grab(pattern, key):
        m = re.search(pattern, text, flags=re.I)
        if m:
            out[key] = m.group(1).strip()
    grab(r"AL[: ]+([0-9.,]+ ?mm)", "axial_length")
    grab(r"CCT[: ]+([0-9.,]+ ?µm)", "cct")
    grab(r"ACD[: ]+([0-9.,]+ ?mm)", "acd")
    grab(r"LT[: ]+([0-9.,]+ ?mm)", "lt")
    grab(r"K1[: ]+([0-9.,]+ ?D.*)", "k1")
    grab(r"K2[: ]+([0-9.,]+ ?D.*)", "k2")
    grab(r"K[: ]+([-0-9.,]+ ?D.*)", "ak")
    grab(r"WTW[: ]+([0-9.,]+ ?mm)", "wtw")
    m = re.search(r"IOL ?Master ?700", text, flags=re.I)
    if m:
        out["source"] = "IOL Master 700"
    return out

def base_structured(left: str, right: str) -> dict:
    return {
        "OD": parse_eye_block(left),
        "OS": parse_eye_block(right)
    }

def _strip_code_fences(s: str) -> str:
    s = s.strip()
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", s, flags=re.S)
    return m.group(1) if m else s

def _tolerant_json_loads(s: str):
    s = _strip_code_fences(s).strip()
    s = s.replace("“", '"').replace("”", '"').replace("’", "'")
    s = s.replace("\xa0", " ").replace("\u200b", "")
    if s.count("{") > s.count("}"):
        s = s + "}"
    if s.count("[") > s.count("]"):
        s = s + "]"
    s = re.sub(r",\s*([}\]])", r"\1", s)
    return json.loads(s)

def _build_llm_prompt(raw_left: str, raw_right: str) -> str:
    return (
        "You are extracting eye biometric values from an ophthalmology report.\n"
        "Return a SINGLE JSON object ONLY, no commentary. Keys and order:\n"
        '{\n'
        '  "OD": { "source","axial_length","acd","cct","lt","k1","k2","ak","wtw" },\n'
        '  "OS": { "source","axial_length","acd","cct","lt","k1","k2","ak","wtw" }\n'
        '}\n"
        "- Units: keep units appearing in text.\n"
        "- If a value is clearly present, fill it. If absent, use an empty string.\n"
        "- 'source' is the device name like 'IOL Master 700'.\n"
        "- Typical ranges: cct 400–700 µm; axial length 20–30 mm.\n\n"
        f"LEFT BLOCK (OD tentative):\n{raw_left[:8000]}\n\n"
        f"RIGHT BLOCK (OS tentative):\n{raw_right[:8000]}\n"
    )

def call_llm_structured(raw_left: str, raw_right: str, debug: bool=False):
    dbg = {}
    if not os.getenv("ENABLE_LLM"):
        return {}, dbg
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        prompt = _build_llm_prompt(raw_left, raw_right)
        resp = client.chat.completions.create(
            model=model,
            temperature=0,
            messages=[{"role":"user","content":prompt}]
        )
        text = resp.choices[0].message.content or ""
        dbg["llm_raw"] = text[:2000]
        data = _tolerant_json_loads(text)
        return data, dbg
    except Exception as e:
        dbg["llm_error"] = repr(e)
        return {}, dbg

@app.route("/api/health")
def health():
    env_diag = {
        "ENABLE_LLM": os.getenv("ENABLE_LLM",""),
        "GOOGLE_CLOUD_CREDENTIALS_JSON_present": bool(os.getenv("GOOGLE_CLOUD_CREDENTIALS_JSON")),
        "LLM_MODEL": os.getenv("LLM_MODEL",""),
        "OPENAI_API_KEY_present": bool(os.getenv("OPENAI_API_KEY"))
    }
    return jsonify({
        "env": env_diag,
        "llm_enabled": bool(os.getenv("ENABLE_LLM")),
        "llm_model": os.getenv("LLM_MODEL"),
        "status": "running",
        "version": "5.1.2 (LLM tolerant JSON)"
    })

@app.route("/api/parse", methods=["POST"])
def parse():
    debug = request.args.get("debug") == "1"
    if "file" not in request.files:
        return jsonify({"error":"No file"}),400
    f = request.files["file"]
    filename = secure_filename(f.filename)
    path = os.path.join("/tmp", filename)
    f.save(path)

    text = ""
    if filename.lower().endswith(".pdf"):
        text = extract_text_from_pdf(path)
        if not text:
            doc = fitz.open(path)
            for page in doc:
                pix = page.get_pixmap()
                img_path = path+".png"
                pix.save(img_path)
                text += extract_text_from_image(img_path)
    else:
        text = extract_text_from_image(path)

    left,right = split_left_right(text)
    struct = base_structured(left,right)
    llm_struct,llm_dbg = call_llm_structured(left,right,debug=debug)

    def merge_eye(base,llm):
        out = base.copy()
        for k in ["source","axial_length","acd","cct","lt","k1","k2","ak","wtw"]:
            if not out.get(k) and llm.get(k):
                out[k] = llm[k]
        return out

    if llm_struct:
        struct["OD"] = merge_eye(struct.get("OD",{}), llm_struct.get("OD",{}))
        struct["OS"] = merge_eye(struct.get("OS",{}), llm_struct.get("OS",{}))

    debug_blob = {}
    if debug:
        debug_blob = {
            "left_preview": left[:400],
            "right_preview": right[:400],
            "llm": llm_dbg
        }

    return jsonify({
        "structured": struct,
        "debug": debug_blob
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
