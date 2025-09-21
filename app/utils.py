# LLM fallback for missing fields
import openai
import os

def llm_extract_missing_fields(ocr_text: str, missing_fields: dict, model: str = "gpt-4o-mini") -> dict:
    """
    Calls OpenAI LLM to extract only the missing fields for OD/OS from the OCR text.
    missing_fields: dict like {"od": ["axial_length", ...], "os": ["lt", ...]}
    Returns: dict with structure {"od": {...}, "os": {...}}. On error, returns error info in 'llm_error' key.
    """
    import logging
    logger = logging.getLogger("llm_fallback")
    if not missing_fields.get("od") and not missing_fields.get("os"):
        return {"od": {}, "os": {}}

    # Build prompt
    prompt = [
        "Extract the following fields for both eyes (OD and OS) from the text below. OD and OS data may appear on either of the first two pages, and the order/layout may vary. Carefully match the correct values to each eye, even if the pages are inverted or the layout is mirrored. For K1 and K2, always extract both the value (in diopters) and the axis (in degrees), and output them as an object with 'value' and 'axis' keys. Do not repeat K1/K2 values for the same eye. If a field is missing, return an empty string. Output as JSON.",
        f"OD fields: {', '.join([f'{f} (for K1/K2: value and axis)' if f in ['k1','k2'] else f for f in missing_fields.get('od', [])])}",
        f"OS fields: {', '.join([f'{f} (for K1/K2: value and axis)' if f in ['k1','k2'] else f for f in missing_fields.get('os', [])])}",
        "Text:",
        '"""',
        ocr_text.strip(),
        '"""',
        "Example output:",
        '{',
        '  "od": {',
        '    "axial_length": "",',
        '    "lt": "",',
        '    "cct": "",',
        '    "k1": {"value": "", "axis": ""},',
        '    "k2": {"value": "", "axis": ""},',
        '    "ak": ""',
        '  },',
        '  "os": {',
        '    "axial_length": "",',
        '    "lt": "",',
        '    "cct": "",',
        '    "k1": {"value": "", "axis": ""},',
        '    "k2": {"value": "", "axis": ""},',
        '    "ak": ""',
        '  }',
        '}'
    ]
    prompt_str = "\n".join(prompt)

    openai.api_key = os.getenv("OPENAI_API_KEY")
    try:
        response = openai.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt_str}],
            temperature=0.0,
            max_completion_tokens=256,
        )
        content = response.choices[0].message.content
        # Remove Markdown code block markers if present
        if content.strip().startswith("```"):
            # Remove the first line (``` or ```json) and the last line (```)
            lines = content.strip().splitlines()
            # Remove first line if it starts with ```
            if lines[0].startswith("```"):
                lines = lines[1:]
            # Remove last line if it is ```
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines)
        import json
        try:
            result = json.loads(content)
        except Exception as je:
            logger.error(f"LLM JSON parse error: {je}; content: {content}")
            return {"od": {}, "os": {}, "llm_error": f"JSON parse error: {je}"}
        return result
    except Exception as e:
        logger.error(f"LLM API error: {e}")
        return {"od": {}, "os": {}, "llm_error": str(e)}
import re, hashlib

DECIMAL_RX = re.compile(r"(?P<num>\d{1,3}[\.,]\d{1,3})")
UNIT_RX = re.compile(r"(mm|µm|um|D|°)")

RANGES = {
    "axial_length": (20.0, 30.0, "mm"),
    "acd": (2.0, 5.0, "mm"),
    "cct": (400.0, 700.0, "µm"),
    "wtw": (10.0, 13.0, "mm"),
    "lt": (3.0, 6.0, "mm"),
}

UNIT_NORMAL = {"um": "µm"}

def to_float(s: str) -> float | None:
    if not s:
        return None
    s = s.strip().replace(",", ".")
    try:
        return float(re.findall(r"-?\d+(?:\.\d+)?", s)[0])
    except Exception:
        return None

def normalize_unit(u: str | None) -> str | None:
    if not u:
        return u
    return UNIT_NORMAL.get(u, u)

def check_range(name: str, value: float | None) -> tuple[bool, str | None]:
    if value is None:
        return False, f"{name} missing"
    lo, hi, unit = RANGES.get(name, (None, None, None))
    if lo is None:
        return True, None
    if not (lo <= value <= hi):
        return False, f"{name} out of range ({value} {unit}, expected {lo}-{hi})"
    return True, None

def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def safe_filename(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]", "_", s)
