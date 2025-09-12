# app.py
# LakeCalc.ai — IOL Parser
# Version: 5.1.1 (Universal Parser + LLM fallback, with env diagnostics)

import io
import os
import re
import json
import logging
from dataclasses import dataclass, asdict
from typing import Dict, Tuple, Optional

from flask import Flask, request, jsonify, render_template, send_from_directory, Response

# --- PDF/text helpers (pure-Python; no system deps) ---
import pdfplumber

# --- Optional: OpenAI (loaded lazily; app works without it) ---
_OPENAI_IMPORTED = False
try:
    # New-style OpenAI client
    from openai import OpenAI
    _OPENAI_IMPORTED = True
except Exception:
    _OPENAI_IMPORTED = False


APP_VERSION = "5.1.1 (Universal Parser + LLM fallback + env diagnostics)"

app = Flask(__name__, template_folder="templates", static_folder="static")

# ------------------------------------------------------------------------------
# Logging & ENV diagnostics
# ------------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("lakecalc")

MASK = "*******"


def _mask(s: Optional[str]) -> str:
    if not s:
        return ""
    if len(s) <= 8:
        return MASK
    return s[:2] + "****" + s[-2:]


def _bool_from_env(name: str, default: bool = False) -> bool:
    v = os.getenv(name, "")
    if not v:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


def _env_snapshot() -> Dict:
    return {
        "ENABLE_LLM": os.getenv("ENABLE_LLM", ""),
        "LLM_MODEL": os.getenv("LLM_MODEL", ""),
        "OPENAI_API_KEY_present": bool(os.getenv("OPENAI_API_KEY")),
        "GOOGLE_APPLICATION_CREDENTIALS_present": bool(os.getenv("GOOGLE_APPLICATION_CREDENTIALS")),
        "GOOGLE_CLOUD_CREDENTIALS_JSON_present": bool(os.getenv("GOOGLE_CLOUD_CREDENTIALS_JSON")),
        "PYTHONANYWHERE": os.getenv("PYTHONANYWHERE", ""),  # just to show a random extra
        "PATH_sample": os.getenv("PATH", "")[:64] + "…",
    }


def _log_env_on_startup():
    snap = _env_snapshot()
    pretty = json.dumps(snap, indent=2)
    log.info("Environment snapshot (keys, masked where appropriate):\n%s", pretty)


_log_env_on_startup()

ENABLE_LLM = _bool_from_env("ENABLE_LLM", False)
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
OPENAI_API_KEY_PRESENT = bool(os.getenv("OPENAI_API_KEY"))

if ENABLE_LLM:
    if not OPENAI_API_KEY_PRESENT:
        log.warning("ENABLE_LLM=1 but OPENAI_API_KEY is missing — LLM will be disabled at runtime.")
    elif not _OPENAI_IMPORTED:
        log.warning("OpenAI client not importable — install `openai` package. LLM will be disabled.")
    else:
        log.info("LLM integration enabled with model=%s", LLM_MODEL)
else:
    log.info("LLM integration disabled (set ENABLE_LLM=1 to enable).")


# ------------------------------------------------------------------------------
# Simple domain model
# ------------------------------------------------------------------------------
EYE_FIELDS_ORDER = [
    "source",
    "axial_length",
    "acd",
    "cct",
    "lt",
    "k1",
    "k2",
    "ak",
    "wtw",
]


@dataclass
class EyeData:
    source: str = "IOL Master 700"
    axial_length: str = ""
    acd: str = ""
    cct: str = ""
    lt: str = ""
    k1: str = ""
    k2: str = ""
    ak: str = ""
    wtw: str = ""


def _clean_text(s: str) -> str:
    # normalize frequent OCR substitutions (µ/° issues etc.)
    # NOTE: keep gentle to avoid breaking real numbers
    s = s.replace("µ", "u")            # keep units readable but distinct
    s = s.replace("°", "°")            # leave as-is; pdfminer usually preserves "°"
    s = re.sub(r"[ \t]+", " ", s)
    return s


def extract_pdf_text(file_bytes: bytes) -> str:
    """Extract text from PDF using pdfplumber (layout-preserving-ish)."""
    out = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            # text() already follows reading order; extract_words for coord harvesting if needed
            out.append(page.extract_text() or "")
    return "\n".join(out)


def split_left_right(text: str) -> Tuple[str, str]:
    """
    Naive left/right split: if the page is two columns, the left block tends to contain OD lines.
    If not, we still return (text, text) so both parsers can try.
    """
    # Cheap heuristic: if explicit OS labels exist later, prefer classic mapping
    # Otherwise return full text for both so we don't miss anything.
    if "OS" in text or "esquerda" in text.lower():
        return text, text
    return text, text


def find_value(patterns, hay) -> Optional[str]:
    for pat in patterns:
        m = re.search(pat, hay, flags=re.IGNORECASE | re.MULTILINE)
        if m:
            g = next((g for g in m.groups() if g), None)
            return g.strip() if g else m.group(0).strip()
    return None


def parse_eye_block(block: str, prefer_units: bool = True) -> EyeData:
    t = _clean_text(block)

    # Patterns
    num_mm = r"([\d]+[.,]\d+)\s*mm"
    num_um = r"([\d]+[.,]\d+)\s*(?:um|µm|u m)"
    diopter = r"([\d]+[.,]\d+)\s*D"
    axis = r"@?\s*([0-9]{1,3})\s*°"
    k_pair = r"([\d]+[.,]\d+)\s*D(?:\s*@\s*([0-9]{1,3})\s*°)?"

    eye = EyeData()

    # Source (device) — keep default but allow override if visible
    src = find_value([r"(IOL ?Master ?700)"], t)
    if src:
        eye.source = src

    # AL, ACD, CCT, LT
    eye.axial_length = find_value([rf"(?:AL|Axial(?: Length)?)[^\S\r\n]*[: ]\s*{num_mm}",
                                   rf"{num_mm}\s*(?:AL|Axial Length)"], t) or ""

    eye.acd = find_value([rf"(?:ACD)[^\S\r\n]*[: ]\s*{num_mm}",
                          rf"{num_mm}\s*ACD"], t) or ""

    # cct: prefer µm but accept mm if present
    cct_um = find_value([rf"(?:CCT)[^\S\r\n]*[: ]\s*{num_um}",
                         rf"{num_um}\s*CCT"], t)
    cct_mm = find_value([rf"(?:CCT)[^\S\r\n]*[: ]\s*{num_mm}",
                         rf"{num_mm}\s*CCT"], t)
    eye.cct = cct_um or cct_mm or ""

    eye.lt = find_value([rf"(?:LT)[^\S\r\n]*[: ]\s*{num_mm}",
                         rf"{num_mm}\s*LT"], t) or ""

    # Keratometry (K1/K2) and cylinder (AK)
    k1 = re.search(rf"(?:K1)[^\S\r\n]*[: ]\s*{k_pair}", t, flags=re.IGNORECASE)
    if k1:
        d = k1.group(1)
        ax = k1.group(2)
        eye.k1 = f"{d} D" + (f" @ {ax}°" if ax else "")

    k2 = re.search(rf"(?:K2)[^\S\r\n]*[: ]\s*{k_pair}", t, flags=re.IGNORECASE)
    if k2:
        d = k2.group(1)
        ax = k2.group(2)
        eye.k2 = f"{d} D" + (f" @ {ax}°" if ax else "")

    # SE / AK (cylinder)
    ak = re.search(rf"(?:SE|AK|\(cid:706\)K)[^\S\r\n]*[: ]\s*(-?{diopter})(?:\s*@\s*{axis})?", t,
                   flags=re.IGNORECASE)
    if ak:
        # ak.group(1) contains value with unit D due to nested capture: "-2,79 D"
        val = ak.group(1).replace(" ", "")
        ax = ak.group(2)
        eye.ak = f"{val}" + (f" @ {ax}°" if ax else "")

    # WTW
    eye.wtw = find_value([rf"(?:WTW|Branco a branco)[^\S\r\n]*[: ]\s*{num_mm}",
                          rf"{num_mm}\s*(?:WTW|Branco a branco)"], t) or ""

    return eye


def needs_llm(od: EyeData, os_: EyeData) -> bool:
    # If any critical field is missing (especially CCT), we can escalate to LLM (if allowed)
    def incomplete(e: EyeData) -> bool:
        return not (e.axial_length and e.acd and e.lt and e.k1 and e.k2 and e.ak and e.wtw and e.cct)

    return incomplete(od) or incomplete(os_)


def llm_structurize(raw_text: str) -> Optional[Dict]:
    """Ask the LLM to structure the text. Returns dict or None."""
    if not (ENABLE_LLM and OPENAI_API_KEY_PRESENT and _OPENAI_IMPORTED):
        return None

    try:
        client = OpenAI()
        system = (
            "You are a medical report parser. Extract a JSON with two objects 'OD' and 'OS'. "
            "Each must include, in this order: source (device), axial_length (mm), acd (mm), "
            "cct (µm or mm), lt (mm), k1 (with diopters and axis), k2 (with diopters and axis), "
            "ak (cylinder with diopters and axis), wtw. Keep original units and decimals. "
            "Do not invent values."
        )
        user = f"Text:\n{raw_text[:45000]}\n\nReturn ONLY the JSON."
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=0
        )
        content = resp.choices[0].message.content.strip()
        # Try to locate JSON
        j = re.search(r"\{.*\}", content, flags=re.S)
        if not j:
            return None
        data = json.loads(j.group(0))
        return data
    except Exception as e:
        log.warning("LLM structurize failed: %s", e)
        return None


# ------------------------------------------------------------------------------
# Flask routes
# ------------------------------------------------------------------------------
@app.route("/")
def index():
    # Simple HTML served from templates/index.html if you have it; otherwise a tiny page
    try:
        return render_template("index.html")
    except Exception:
        return Response(
            """<!doctype html><meta charset="utf-8">
            <title>LakeCalc.ai — IOL Parser</title>
            <h1>LakeCalc.ai — IOL Parser</h1>
            <p>Health: <a href="/api/health">/api/health</a></p>
            """,
            mimetype="text/html",
        )


@app.route("/api/health")
def health():
    # Return what the app actually sees right now, not expectations
    snap = _env_snapshot()
    return jsonify({
        "llm_enabled": bool(ENABLE_LLM and OPENAI_API_KEY_PRESENT and _OPENAI_IMPORTED),
        "llm_model": LLM_MODEL if ENABLE_LLM else None,
        "status": "running",
        "version": APP_VERSION,
        "env": snap,  # helpful while we’re debugging Railway
    })


@app.route("/api/parse", methods=["POST"])
def parse_endpoint():
    include_raw = request.args.get("include_raw") == "1"
    force_pdf_text = request.args.get("force_pdf_text") == "1"  # kept for UI compatibility
    debug = request.args.get("debug") == "1"

    if "file" not in request.files:
        return jsonify({"error": "No file uploaded (field 'file')"}), 400

    f = request.files["file"]
    data = f.read()

    # 1) Text extraction (PDF)
    raw_text = extract_pdf_text(data)
    left, right = split_left_right(raw_text)

    # 2) Heuristic parse
    od = parse_eye_block(left)
    os_ = parse_eye_block(right)

    # 3) If incomplete and LLM is allowed, try LLM
    llm_used = False
    if ENABLE_LLM and OPENAI_API_KEY_PRESENT and _OPENAI_IMPORTED and needs_llm(od, os_):
        structured = llm_structurize(raw_text)
        if structured and "OD" in structured and "OS" in structured:
            # Merge: fill only missing fields from LLM result
            def merge(dst: EyeData, src: Dict):
                for k in EYE_FIELDS_ORDER:
                    v = getattr(dst, k)
                    if not v and src.get(k):
                        setattr(dst, k, src[k])

            merge(od, structured.get("OD", {}))
            merge(os_, structured.get("OS", {}))
            llm_used = True

    result = {
        "OD": {k: getattr(od, k) for k in EYE_FIELDS_ORDER},
        "OS": {k: getattr(os_, k) for k in EYE_FIELDS_ORDER},
    }

    # Optional debug payload so we can see exactly what the app saw
    dbg = None
    if debug:
        dbg = {
            "strategy": "pdf_layout_split + heuristics" + (" + LLM" if llm_used else ""),
            "xtra": {
                "notes": "See /api/health for env. LLM used only when ENABLE_LLM=1, key present, and fields were missing."
            }
        }

    payload = {
        "filename": f.filename,
        "structured": result,
        "text_source": "pdf_text",
    }
    if include_raw:
        payload["raw_text_preview"] = raw_text[:2000]
    if dbg:
        payload["debug"] = dbg

    return jsonify(payload)


# Static passthrough (if needed)
@app.route("/static/<path:fn>")
def static_files(fn):
    return send_from_directory(app.static_folder or "static", fn)


if __name__ == "__main__":
    # Local debug
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
