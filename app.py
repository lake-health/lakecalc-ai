# app.py — LakeCalc.ai parser v3.6
# layout split + strict binder + CCT sanity + rescue + reconcile + PT→EN + µ/μ + ΔK/AK/K + ordered + safe PDF extract

import os, io, re
from collections import OrderedDict
from io import BytesIO
from typing import Optional, Tuple

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
vision_client: Optional[vision.ImageAnnotatorClient] = None
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
        print("INFO: Vision credentials not set. OCR fallback disabled.")
except Exception as e:
    print(f"Vision init error: {e}")


# =========================
# Safe PDF text extraction
# =========================
def extract_pdf_text_safe(file_bytes: bytes) -> str:
    """Robust wrapper around pdfminer to avoid TypeError / bad streams."""
    try:
        bio = BytesIO(file_bytes)
        text = pdfminer_extract_text(bio) or ""
        # Tidy trailing spaces before newlines to stabilize regexes
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
    """
    Returns (text, source_tag, pdf_bytes_or_None).
    source_tag: 'pdf_text'|'ocr_pdf'|'ocr_image'
    """
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
        # fallback to OCR if no text
        return ocr_pdf_to_text(file_bytes), "ocr_pdf", file_bytes

    # images
    if force_mode == "ocr" or not force_mode:
        return ocr_image_to_text(file_bytes), "ocr_image", None

    # default
    return "", "unknown", None


# =========================
# Normalization (OCR/PDF quirks)
# =========================
def normalize_for_ocr(text: str) -> str:
    t = text.replace("\u00A0", " ")

    # Join AL/ACD/LT/WTW/CCT split across lines: "AL:\n23,73\nmm" -> "AL: 23,73 mm"
    t = re.sub(
        r"(?mi)^(AL|ACD|LT|WTW|CCT)\s*:\s*\n\s*([-\d.,]+)\s*\n\s*(mm|[µμ]m|um)\b",
        r"\1: \2 \3",
        t,
    )

    # Join K* value + 'D' split across lines
    t = re.sub(
        r"(?mi)^(K1|K2|K|AK|ΔK)\s*:\s*\n\s*([-\d.,]+)\s*\n\s*D\b",
        r"\1: \2 D",
        t,
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
# Strict binder: numbers/units above labels
# =========================
def bind_disjoint_scalars(text: str) -> str:
    """
    Strict binder for AL/ACD/LT/WTW/CCT when numbers/units sit above labels.
    - Requires explicit unit (no bare-number fallback).
    - Looks back a short window (<=180 chars), then *cuts off* any trailing noise
      block (SD:, CVD:, WTW:, P:, TK*, etc.) so we don't grab '20/4/10/20'.
    - Supports 'number + unit' and 'unit \\n number' layouts.
    """

    NOISE = re.compile(r"(?mi)\b(?:CVD|SD|WTW|P|TK1|TK2|TSE)\s*:")

    def patch_label(t: str, label: str, unit_kind: str) -> str:
        unit_pat = r"mm" if unit_kind == "mm" else r"(?:[µμ]m|um)"
        lab_re = re.compile(rf"(?mi)^({label})\s*:\s*$")

        def _repl(m):
            idx = m.start()
            win = t[max(0, idx - 180): idx]  # wider but still local

            # Cut back window at the last noise marker (closest to label)
            cut = NOISE.search(win)
            if cut:
                win = win[: cut.start()]

            # 1) number + expected unit, choose the CLOSEST to the label
            m1_iter = list(re.finditer(rf"(-?\d[\d.,]*)\s*{unit_pat}\b", win, flags=re.IGNORECASE))
            if m1_iter:
                m1 = m1_iter[-1]  # closest
                val = f"{m1.group(1)} {'mm' if unit_kind=='mm' else 'µm'}"
                return f"{m.group(1)}: {val}"

            # 2) expected unit then newline then number (choose the closest)
            m2_iter = list(re.finditer(rf"{unit_pat}\s*\n\s*(-?\d[\d.,]*)\b", win, flags=re.IGNORECASE))
            if m2_iter:
                m2 = m2_iter[-1]
                val = f"{m2.group(1)} {'mm' if unit_kind=='mm' else 'µm'}"
                return f"{m.group(1)}: {val}"

            # Strict: do NOT invent values without explicit unit
            return m.group(0)

        return lab_re.sub(_repl, t)

    t = text
    t = patch_label(t, "AL", "mm")
    t = patch_label(t, "CCT", "um")
    t = patch_label(t, "ACD", "mm")
    t = patch_label(t, "LT", "mm")
    t = patch_label(t, "WTW", "mm")
    return t


# =========================
# CCT sanity correction
# =========================
def smart_fix_cct_bound(text_with_bindings: str) -> str:
    """
    If CCT got bound to something implausible (e.g., '23,73 µm'), look around the
    CCT label for a more plausible 3-digit µm value (400–700) and replace it.
    """
    def replace(match: re.Match) -> str:
        full = match.group(0)
        val = match.group(1)
        # Normalize decimal comma
        try:
            num = float(val.replace('.', '').replace(',', '.'))
        except ValueError:
            num = -1.0
        # If it's already plausible (400–700), keep it
        if 400 <= num <= 700:
            return full
        # Search forward a little for a better µm number
        tail = text_with_bindings[match.end(): match.end() + 200]
        mnext = re.search(r"(-?\d[\d.,]*)\s*(?:[µμ]m|um)\b", tail)
        if mnext:
            try:
                cand = float(mnext.group(1).replace('.', '').replace(',', '.'))
            except ValueError:
                cand = -1.0
            if 400 <= cand <= 700:
                return full.replace(val, mnext.group(1))
        return full

    return re.sub(r"(?mi)\bCCT\s*:\s*([-\d.,]+)\s*(?:[µμ]m|um)\b", replace, text_with_bindings)


# =========================
# Controlled PT→EN localization (header clues only)
# =========================
def localize_pt_to_en(text: str) -> str:
    t = text
    replacements = [
        (r"\b(direita|olho\s+direito)\b", "RIGHT"),
        (r"\b(esquerda|esquerdo|olho\s+esquerdo)\b", "LEFT"),
        (r"\bpaciente\b", "PATIENT"),
        (r"\ban[aá]lise\b", "ANALYSIS"),
        (r"\bbranco a branco\b", "WHITE TO WHITE"),
    ]
    for pat, repl in replacements:
        t = re.sub(pat, repl, t, flags=re.IGNORECASE)
    return t  # never touch 'os' or 'olhos'


# =========================
# PDF layout split: left/right columns
# =========================
def pdf_split_left_right(pdf_bytes: bytes) -> dict:
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
MM = r"-?\d[\d.,]*\s*mm"
UM = r"-?\d[\d.,]*\s*(?:[µμ]m|um)"  # accept µm and μm and um
DVAL = r"-?\d[\d.,]*\s*D"
LABEL_STOP = re.compile(r"(?:\r?\n|(?=(?:AL|ACD|CCT|LT|WTW|K1|K2|K|AK|ΔK)\s*:))", re.IGNORECASE)

PATTERNS = {
    "axial_length": re.compile(rf"(?mi)\bAL\s*:\s*({MM})"),
    "acd": re.compile(rf"(?mi)\bACD\s*:\s*({MM})"),
    "cct": re.compile(rf"(?mi)\bCCT\s*:\s*({UM})"),
    "lt": re.compile(rf"(?mi)\bLT\s*:\s*({MM})"),
    "wtw": re.compile(rf"(?mi)\bWTW\s*:\s*({MM})"),
    "k1": re.compile(rf"(?mi)\bK1\s*:\s*({DVAL})"),
    "k2": re.compile(rf"(?mi)\bK2\s*:\s*({DVAL})"),
    # ΔK / AK / K (but NOT K1/K2)
    "ak": re.compile(rf"(?mi)\b(?:Δ\s*K|AK|K(?!\s*1|\s*2))\s*:\s*({DVAL})"),
}


def harvest_axis(field_tail: str) -> str:
    mstop = LABEL_STOP.search(field_tail)
    seg = field_tail[: mstop.start()] if mstop else field_tail
    seg = seg[:120]
    if "@" in seg:
        after = seg.split("@", 1)[1]
        digits = re.findall(r"\d", after)
        axis = "".join(digits)[:3]
        return f" @ {axis}°" if axis else ""
    m = re.search(r"(\d{1,3})\s*(?:°|º|o)\b", seg)
    return f" @ {m.group(1)}°" if m else ""


def parse_eye_block(txt: str) -> dict:
    out = {"axial_length": "", "acd": "", "k1": "", "k2": "", "ak": "", "wtw": "", "cct": "", "lt": ""}
    if not txt or not txt.strip():
        return out
    for key, pat in PATTERNS.items():
        for m in pat.finditer(txt):
            raw = re.sub(r"\s+", " ", m.group(1)).strip()
            if key in ("k1", "k2", "ak"):
                raw = re.sub(r"@\s*.*$", "", raw)  # drop trailing axis blob
                tail = txt[m.end(1) : m.end(1) + 200]
                raw = (raw + harvest_axis(tail)).strip()
            if not out[key]:
                out[key] = raw
    return out


def has_measurements(d: dict) -> bool:
    return any(d.values())


# Rescue harvester (tolerant)
RESCUE = {
    "axial_length": re.compile(r"(?mi)\bAL\s*[:=]?\s*(-?\d[\d.,]*)\s*mm\b"),
    "acd": re.compile(r"(?mi)\bACD\s*[:=]?\s*(-?\d[\d.,]*)\s*mm\b"),
    "lt": re.compile(r"(?mi)\bLT\s*[:=]?\s*(-?\d[\d.,]*)\s*mm\b"),
    "wtw": re.compile(r"(?mi)\bWTW\s*[:=]?\s*(-?\d[\d.,]*)\s*mm\b"),
    "cct": re.compile(
        r"(?mi)\bCCT\s*[:=]?\s*(?:(-?\d[\d.,]*)\s*(?:[µμ]m|um)|(?:[µμ]m|um)\s*\n\s*(-?\d[\d.,]*))"
    ),
    "k1": re.compile(r"(?mi)\bK1\s*[:=]?\s*(-?\d[\d.,]*)\s*D(?:.*?@\s*(\d{1,3}))?"),
    "k2": re.compile(r"(?mi)\bK2\s*[:=]?\s*(-?\d[\d.,]*)\s*D(?:.*?@\s*(\d{1,3}))?"),
    "ak": re.compile(r"(?mi)\b(?:Δ\s*K|AK|K(?!\s*1|\s*2))\s*[:=]?\s*(-?\d[\d.,]*)\s*D(?:.*?@\s*(\d{1,3}))?"),
}


def rescue_harvest(raw_text: str) -> dict:
    out = {}

    def setv(k, v):
        if v and k not in out:
            out[k] = v.strip()

    for k in ("axial_length", "acd", "lt", "wtw"):
        m = RESCUE[k].search(raw_text)
        if m:
            setv(k, f"{m.group(1)} mm")

    m = RESCUE["cct"].search(raw_text)
    if m:
        num = m.group(1) or m.group(2)
        if num:
            setv("cct", f"{num} µm")

    for k in ("k1", "k2", "ak"):
        m = RESCUE[k].search(raw_text)
        if m:
            diop = m.group(1)
            axis = m.group(2)
            val = f"{diop} D"
            if axis:
                val += f" @ {axis}°"
            setv(k, val)

    return out


# Reconcile
def reconcile(base: dict, binder: dict | None, rescue: dict | None) -> dict:
    res = dict(base)
    if binder:
        for k, v in binder.items():
            if k in res and (not res[k]) and v:
                res[k] = v
    if rescue:
        for k, v in rescue.items():
            if k in res and (not res[k]) and v:
                res[k] = v
    return res


# Detect device
def detect_source_label(text: str) -> str:
    if re.search(r"IOL\s*Master\s*700", text, re.IGNORECASE):
        return "IOL Master 700"
    if re.search(r"OCULUS\s+PENTACAM", text, re.IGNORECASE):
        return "Pentacam"
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "Unknown")
    return first[:60]


# Output ordering
FIELD_ORDER = ["source", "axial_length", "acd", "k1", "k2", "ak", "wtw", "cct", "lt"]


def enforce_field_order(eye_dict: dict) -> OrderedDict:
    return OrderedDict((k, eye_dict.get(k, "")) for k in FIELD_ORDER)


# =========================
# Controller
# =========================
def parse_iol(norm_text: str, pdf_bytes: Optional[bytes], source_label: str, want_debug: bool = False):
    def fresh():
        return OrderedDict(
            [
                ("source", source_label),
                ("axial_length", ""),
                ("acd", ""),
                ("k1", ""),
                ("k2", ""),
                ("ak", ""),
                ("wtw", ""),
                ("cct", ""),
                ("lt", ""),
            ]
        )

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
        # Normalize → strict bind → CCT sanity → localize
        left_norm = localize_pt_to_en(smart_fix_cct_bound(bind_disjoint_scalars(normalize_for_ocr(left_txt))))
        right_norm = localize_pt_to_en(smart_fix_cct_bound(bind_disjoint_scalars(normalize_for_ocr(right_txt))))
        if want_debug:
            debug["left_preview"] = left_norm[:600]
            debug["right_preview"] = right_norm[:600]

        # Primary parse
        left_data = parse_eye_block(left_norm)
        right_data = parse_eye_block(right_norm)

        # Bound scalar dicts (from normalized text)
        def scalars_from_bound(nrm: str) -> dict:
            d = {}
            for lab, key, unit in [
                ("AL", "axial_length", "mm"),
                ("ACD", "acd", "mm"),
                ("LT", "lt", "mm"),
                ("WTW", "wtw", "mm"),
                ("CCT", "cct", "µm"),
            ]:
                m = re.search(rf"(?mi)\b{lab}\s*:\s*(-?\d[\d.,]*)\s*(?:mm|[µμ]m|um)\b", nrm)
                if m:
                    d[key] = f"{m.group(1)} {('µm' if lab=='CCT' else 'mm')}"
            return d

        left_bound = scalars_from_bound(left_norm)
        right_bound = scalars_from_bound(right_norm)

        # Rescue (tolerant)
        left_rescue = rescue_harvest(left_norm)
        right_rescue = rescue_harvest(right_norm)

        # Reconcile
        left_final = reconcile(left_data, left_bound, left_rescue)
        right_final = reconcile(right_data, right_bound, right_rescue)

        # Map OD/OS by clues
        def looks_od(s: str) -> bool:
            u = s.upper()
            return bool(re.search(r"\bOD\b|\bO\s*D\b|RIGHT\b", u))

        def looks_os(s: str) -> bool:
            u = s.upper()
            return bool(re.search(r"\bOS\b|\bO\s*S\b|\bOE\b|\bO\s*E\b|LEFT\b", u))

        left_is_od, left_is_os = looks_od(left_txt), looks_os(left_txt)
        right_is_od, right_is_os = looks_od(right_txt), looks_os(right_txt)

        if left_is_od and right_is_os:
            mapping = {"OD": left_final, "OS": right_final}
            debug["mapping"] = "OD<-left, OS<-right (labels)"
        elif left_is_os and right_is_od:
            mapping = {"OD": right_final, "OS": left_final}
            debug["mapping"] = "OD<-right, OS<-left (labels)"
        else:
            mapping = {"OD": left_final, "OS": right_final}
            debug["mapping"] = "OD<-left, OS<-right (default)"

        # Copy into result
        for eye in ("OD", "OS"):
            for k, v in mapping[eye].items():
                if v:
                    result[eye][k] = v

        # Last-chance global rescue if any eye is still empty
        if not has_measurements(mapping["OD"]):
            od_rescue = rescue_harvest(left_norm + "\n" + right_norm)
            for k, v in od_rescue.items():
                if not result["OD"].get(k):
                    result["OD"][k] = v

        if not has_measurements(mapping["OS"]):
            os_rescue = rescue_harvest(right_norm + "\n" + left_norm)
            for k, v in os_rescue.items():
                if not result["OS"].get(k):
                    result["OS"][k] = v

        # Enforce order
        result["OD"] = enforce_field_order(result["OD"])
        result["OS"] = enforce_field_order(result["OS"])

        return (result, debug) if want_debug else result

    # No layout info → treat as single block → OD
    single = localize_pt_to_en(smart_fix_cct_bound(bind_disjoint_scalars(normalize_for_ocr(norm_text))))
    parsed = parse_eye_block(single)
    for k, v in parsed.items():
        if v:
            result["OD"][k] = v

    result["OD"] = enforce_field_order(result["OD"])
    result["OS"] = enforce_field_order(result["OS"])

    debug["strategy"] = "ocr_single_block_to_OD"
    return (result, debug) if want_debug else result


# =========================
# Routes
# =========================
@app.route("/api/health")
def health():
    return jsonify(
        {
            "status": "running",
            "version": "LakeCalc.ai parser v3.6 (strict binder + CCT sanity + rescue + reconcile + ordered)",
            "ocr_enabled": bool(vision_client),
        }
    )


@app.route("/api/parse-file", methods=["POST"])
def parse_file():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400
    fs = request.files["file"]
    if not fs or fs.filename == "":
        return jsonify({"error": "No selected file"}), 400

    include_raw = request.args.get("include_raw") == "1"
    raw_only = request.args.get("raw_only") == "1"
    force_pdf = request.args.get("force_pdf") == "1"
    force_ocr = request.args.get("force_ocr") == "1"
    debug_flag = request.args.get("debug") == "1"

    force_mode = "pdf" if force_pdf else ("ocr" if force_ocr else None)

    try:
        text, source_tag, pdf_bytes = get_text_from_upload(fs, force_mode=force_mode)
        norm_text = normalize_for_ocr(text)
        source_label = detect_source_label(norm_text)

        if raw_only:
            loc_preview = localize_pt_to_en(smart_fix_cct_bound(bind_disjoint_scalars(norm_text)))
            return jsonify(
                {
                    "filename": fs.filename,
                    "text_source": source_tag,
                    "raw_text": loc_preview,
                    "num_chars": len(loc_preview),
                    "num_lines": loc_preview.count("\n") + 1,
                }
            )

        parsed, dbg = (
            parse_iol(norm_text, pdf_bytes, source_label, want_debug=debug_flag)
            if debug_flag
            else (parse_iol(norm_text, pdf_bytes, source_label), None)
        )

        if include_raw or debug_flag:
            payload = {
                "filename": fs.filename,
                "text_source": source_tag,
                "structured": parsed,
                "raw_text_preview": localize_pt_to_en(smart_fix_cct_bound(bind_disjoint_scalars(norm_text)))[:1500],
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
