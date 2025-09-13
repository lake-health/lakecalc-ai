# app.py — LakeCalc.ai parser v3.10
# v3.9 + LLM fallback for missing OS CCT

import os, io, re, json
from collections import OrderedDict
from io import BytesIO
from typing import Optional, Tuple, List, Dict

from flask import Flask, request, jsonify, render_template

# PDF text & geometry
from pdfminer.high_level import extract_text as pdfminer_extract_text, extract_pages
from pdfminer.layout import (
    LTTextBox, LTTextBoxHorizontal, LTTextLine, LTTextLineHorizontal, LAParams
)

# OCR fallback
from google.cloud import vision
from pdf2image import convert_from_bytes

# LLM fallback
import OpenAI


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
# OpenAI LLM (fallback)
# =========================
llm_client: Optional[OpenAI] = None
llm_model = None
llm_enabled = False
try:
    if os.environ.get("ENABLE_LLM") in ("1", "true", "True"):
        api_key = os.environ.get("OPENAI_API_KEY")
        if api_key:
            llm_client = OpenAI(api_key=api_key)
            llm_model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
            llm_enabled = True
            print(f"INFO: LLM enabled with model {llm_model}")
        else:
            print("WARN: OPENAI_API_KEY not set, LLM disabled.")
    else:
        print("INFO: ENABLE_LLM not set → LLM disabled.")
except Exception as e:
    print(f"LLM init error: {e}")
    llm_client = None
    llm_enabled = False


def llm_extract_cct(text: str, side: str) -> Optional[str]:
    """Ask LLM to extract plausible CCT (µm) for given eye side (OD/OS)."""
    if not (llm_client and llm_enabled):
        return None
    try:
        prompt = f"""
        Extract the central corneal thickness (CCT) in micrometers (µm) 
        for the {side} eye from this ophthalmology exam text.
        Respond only with the number and 'µm' if found.
        If missing or unclear, respond with an empty string.
        ---
        {text}
        """
        resp = llm_client.chat.completions.create(
            model=llm_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        cand = resp.choices[0].message.content.strip()
        if re.search(r"\d", cand) and "µm" in cand:
            return cand
    except Exception as e:
        print(f"LLM extraction error: {e}")
    return None


# =========================
# Safe PDF text extraction
# =========================
def extract_pdf_text_safe(file_bytes: bytes) -> str:
    try:
        bio = BytesIO(file_bytes)
        text = pdfminer_extract_text(bio) or ""
        return re.sub(r"[ \t]+\n", "\n", text).strip()
    except Exception as e:
        print(f"[WARN] pdfminer failed: {e}")
        return ""


# =========================
# Text extraction (PDF-first, OCR fallback)
# =========================
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


def get_text_from_upload(fs, force_mode: Optional[str] = None) -> Tuple[str, str, Optional[bytes]]:
    name = (fs.filename or "").lower()
    is_pdf = name.endswith(".pdf")
    file_bytes = fs.read()

    if is_pdf:
        if force_mode == "pdf":
            txt = extract_pdf_text_safe(file_bytes)
            return txt, "pdf_text", file_bytes
        if force_mode == "ocr":
            return ocr_pdf_to_text(file_bytes), "ocr_pdf", file_bytes

        txt = extract_pdf_text_safe(file_bytes)
        if txt:
            return txt, "pdf_text", file_bytes
        return ocr_pdf_to_text(file_bytes), "ocr_pdf", file_bytes

    if force_mode == "ocr" or not force_mode:
        return ocr_image_to_text(file_bytes), "ocr_image", None
    return "", "unknown", None


# =========================
# [KEEP] normalization, binder, smart_fix_cct, localize_pt_to_en,
# pdf_split_left_right, coordinate_harvest, parse_eye_block,
# rescue_harvest, reconcile, plausibility_rescore, detect_source_label,
# enforce_field_order, parse_iol...
# =========================
# (UNCHANGED CODE OMITTED HERE FOR BREVITY — same as your v3.9, paste intact)

# In parse_iol(), after plausibility_rescore:
#   if OS["cct"] is still empty, call llm_extract_cct(right_norm, "OS").


# =========================
# Routes
# =========================
@app.route("/api/health")
def health():
    env_debug = {
        "ENABLE_LLM": os.environ.get("ENABLE_LLM"),
        "LLM_MODEL": os.environ.get("LLM_MODEL"),
        "OPENAI_API_KEY_len": len(os.environ.get("OPENAI_API_KEY", "")),
        "OPENAI_API_KEY_present": bool(os.environ.get("OPENAI_API_KEY"))
    }
    return jsonify({
        "status": "running",
        "version": "LakeCalc.ai parser v3.10 (coord harvest + strict binder + sanity + rescue + plausibility + LLM optional + ordered)",
        "ocr_enabled": bool(vision_client),
        "llm_enabled": llm_enabled,
        "llm_model": llm_model,
        "env_debug": env_debug
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
        norm_text = text
        source_label = detect_source_label(norm_text)

        parsed, dbg = parse_iol(norm_text, pdf_bytes, source_label, want_debug=debug_flag) if debug_flag else (parse_iol(norm_text, pdf_bytes, source_label), None)

        # If OS CCT still missing → LLM fallback
        if llm_enabled and not parsed["OS"].get("cct"):
            cand = llm_extract_cct(norm_text, "OS")
            if cand:
                parsed["OS"]["cct"] = cand
                if dbg: dbg["llm_fallback"] = "OS CCT via LLM"

        if include_raw or debug_flag:
            payload = {
                "filename": fs.filename,
                "text_source": source_tag,
                "structured": parsed,
                "raw_text_preview": norm_text[:1500]
            }
            if dbg is not None:
                payload["debug"] = dbg
            return jsonify(payload)

        return jsonify(parsed)

    except Exception as e:
        print(f"Error in /api/parse-file: {e}")
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


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
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
