import os
import io
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename

# Optional CORS (ok to remove if you don't need it)
try:
    from flask_cors import CORS
    CORS_ENABLED = True
except Exception:
    CORS_ENABLED = False

# Optional: pdf text extraction via pdfminer.six
try:
    from pdfminer.high_level import extract_text
    PDFMINER_AVAILABLE = True
except Exception:
    PDFMINER_AVAILABLE = False

app = Flask(__name__)
if CORS_ENABLED:
    CORS(app)

# ---- Config helpers ---------------------------------------------------------

def env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return str(val).strip().lower() in {"1", "true", "yes", "on"}

def env_str(name: str, default: str = "") -> str:
    val = os.getenv(name)
    return default if val is None else str(val).strip()

ENABLE_LLM = env_bool("ENABLE_LLM", False)
OPENAI_API_KEY = env_str("OPENAI_API_KEY")
OPENAI_BASE_URL = env_str("OPENAI_BASE_URL")  # optional
OPENAI_MODEL = env_str("OPENAI_MODEL", "gpt-4o-mini")  # default, can be anything
ENABLE_DEBUG = env_bool("ENABLE_DEBUG", True)

# ---- Health endpoint (no hand-built JSON!) ----------------------------------

@app.route("/api/health", methods=["GET"])
def api_health():
    return jsonify({
        "ok": True,
        "service": "pdf-parser",
        "llm": {
            "enabled": ENABLE_LLM,
            "model": OPENAI_MODEL if OPENAI_MODEL else None,
            "base_url": OPENAI_BASE_URL if OPENAI_BASE_URL else None,
            "api_key_present": bool(OPENAI_API_KEY),
        },
        "pdfminer_available": PDFMINER_AVAILABLE,
        "debug": ENABLE_DEBUG,
        "env": {
            # Useful when debugging env propagation; redact actual secrets
            "ENABLE_LLM": os.getenv("ENABLE_LLM"),
            "OPENAI_MODEL": os.getenv("OPENAI_MODEL"),
            "OPENAI_BASE_URL": os.getenv("OPENAI_BASE_URL"),
            "OPENAI_API_KEY_set": "yes" if OPENAI_API_KEY else "no",
        }
    })

# ---- Simple index -----------------------------------------------------------

@app.route("/", methods=["GET"])
def index():
    return "PDF parser is up. POST a file to /api/parse", 200

# ---- PDF parse endpoint -----------------------------------------------------

@app.route("/api/parse", methods=["POST"])
def api_parse():
    """
    Accepts multipart/form-data with a 'file' field.
    Returns a JSON payload with raw text preview and some debug info.
    (This is intentionally simple and safe; your advanced parsing can be
    reconnected here once the service is stable.)
    """
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "No file part"}), 400

    f = request.files["file"]
    if not f or f.filename == "":
        return jsonify({"ok": False, "error": "No selected file"}), 400

    filename = secure_filename(f.filename)
    data = f.read()  # bytes

    text = ""
    error = None

    # Try pdfminer if available; otherwise just store bytes length
    try:
        if PDFMINER_AVAILABLE:
            # Use in-memory bytes
            text = extract_text(io.BytesIO(data)) or ""
        else:
            error = "pdfminer.six not installed; returning metadata only"
    except Exception as e:
        error = f"pdf extraction error: {type(e).__name__}: {e}"

    # Build a conservative, stable response
    raw_preview = (text[:1200] + "...") if text and len(text) > 1200 else text
    resp = {
        "ok": True,
        "filename": filename,
        "bytes": len(data),
        "text_chars": len(text),
        "raw_text_preview": raw_preview,
        "structured": {
            # Leave placeholders; reconnect your real parser later
            "OD": {},
            "OS": {}
        },
        "debug": {
            "pdfminer_available": PDFMINER_AVAILABLE,
            "note": "Minimal parser path; no LLM invoked here.",
            "error": error
        }
    }
    return jsonify(resp), 200

# ---- (Optional) LLM endpoint stub ------------------------------------------
# You can call this from your parser when you're ready.
# It won't run unless ENABLE_LLM is true and an API key is present.

@app.route("/api/llm-summarize", methods=["POST"])
def api_llm_summarize():
    if not ENABLE_LLM or not OPENAI_API_KEY:
        return jsonify({"ok": False, "error": "LLM disabled or API key missing"}), 400

    # Minimal echo — wire up your actual OpenAI call here later
    payload = request.get_json(silent=True) or {}
    prompt = payload.get("prompt", "")
    # Return a stub now to avoid pulling extra dependencies in this fix:
    return jsonify({"ok": True, "model": OPENAI_MODEL, "summary": f"(stub) {prompt[:200]}"}), 200

# ---- Main -------------------------------------------------------------------

if __name__ == "__main__":
    # For local testing; Railway uses Gunicorn via Dockerfile/Procfile
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
