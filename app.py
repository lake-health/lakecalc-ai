# app.py — LakeCalc.ai parser v3.8
# v3.7 + coordinate-based harvesting (per-column) to rescue missing CCT in OS
# layout split + strict binder (+CCT special) + CCT sanity (fwd/back)
# + rescue + reconcile + plausibility re-score + PT→EN (clues only)
# + µ/μ + ΔK/AK/K + ordered + safe PDF extract + coord harvester

import os, io, re
from collections import OrderedDict
from io import BytesIO
from typing import Optional, Tuple, List, Dict

from flask import Flask, request, jsonify, render_template

# PDF text & geometry
from pdfminer.high_level import extract_text as pdfminer_extract_text, extract_pages
from pdfminer.layout import (
    LTTextBox, LTTextBoxHorizontal, LTTextLine, LTTextLineHorizontal, LAParams, LTChar
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
# Normalization (OCR/PDF quirks)
# =========================
def normalize_for_ocr(text: str) -> str:
    t = text.replace("\u00A0", " ")
    t = re.sub(
        r"(?mi)^(AL|ACD|LT|WTW|CCT)\s*:\s*\n\s*([-\d.,]+)\s*\n\s*(mm|[µμ]m|um)\b",
        r"\1: \2 \3", t,
    )
    t = re.sub(
        r"(?mi)^(K1|K2|K|AK|ΔK)\s*:\s*\n\s*([-\d.,]+)\s*\n\s*D\b",
        r"\1: \2 D", t,
    )
    t = re.sub(r"@\s*(?:\r?\n|\s)*(?:[°ºo])\s*(?:\r?\n|\s)*?(\d{1,3})\b", r"@ \1°", t)
    t = re.sub(r"@\s*(?:\r?\n|\s)*(\d{1,3})\s*(?:\r?\n|\s)*(?:[°ºo])\b", r"@ \1°", t)
    t = re.sub(r"(?:[°ºo])\s*(?:\r?\n|\s)*?(\d{1,3})\b", r" \1°", t)
    t = re.sub(r"[ \t]+", " ", t)
    return t


# =========================
# Strict binder (CCT special)
# =========================
def bind_disjoint_scalars(text: str) -> str:
    NOISE = re.compile(r"(?mi)\b(?:CVD|SD|WTW|P|TK1|TK2|TSE)\s*:")

    def patch_label(t: str, label: str, unit_kind: str) -> str:
        unit_pat = r"mm" if unit_kind == "mm" else r"(?:[µμ]m|um)"
        lab_re = re.compile(rf"(?mi)^({label})\s*:\s*$")

        def _repl(m):
            idx = m.start()
            win = t[max(0, idx - 180): idx]
            cut = NOISE.search(win)
            if cut:
                win = win[: cut.start()]

            m1_iter = list(re.finditer(rf"(-?\d[\d.,]*)\s*{unit_pat}\b", win, flags=re.IGNORECASE))
            m2_iter = list(re.finditer(rf"{unit_pat}\s*\n\s*(-?\d[\d.,]*)\b", win, flags=re.IGNORECASE))

            if label == "CCT":
                last_um = None
                for um in re.finditer(rf"{unit_pat}\b", win, flags=re.IGNORECASE):
                    last_um = um
                if last_um:
                    tail_after_um = win[last_um.end():]
                    for mnum in re.finditer(r"(-?\d[\d.,]*)", tail_after_um):
                        try:
                            cand = float(mnum.group(1).replace('.', '').replace(',', '.'))
                        except ValueError:
                            continue
                        if 400 <= cand <= 700:
                            return f"{m.group(1)}: {mnum.group(1)} µm"

            if m1_iter:
                m1 = m1_iter[-1]
                val = f"{m1.group(1)} {'mm' if unit_kind=='mm' else 'µm'}"
                return f"{m.group(1)}: {val}"

            if m2_iter:
                m2 = m2_iter[-1]
                val = f"{m2.group(1)} {'mm' if unit_kind=='mm' else 'µm'}"
                return f"{m.group(1)}: {val}"

            return m.group(0)

        return lab_re.sub(_repl, t)

    t = text
    t = patch_label(t, "AL",  "mm")
    t = patch_label(t, "CCT", "um")
    t = patch_label(t, "ACD", "mm")
    t = patch_label(t, "LT",  "mm")
    t = patch_label(t, "WTW", "mm")
    return t


# =========================
# CCT sanity (fwd/back)
# =========================
def smart_fix_cct_bound(text_with_bindings: str) -> str:
    def plausible_um(val: str) -> bool:
        try:
            num = float(val.replace('.', '').replace(',', '.'))
        except ValueError:
            return False
        return 400 <= num <= 700

    def replace(match: re.Match) -> str:
        full = match.group(0)
        val  = match.group(1)
        if plausible_um(val):
            return full
        fwd = text_with_bindings[match.end(): match.end() + 200]
        mf  = re.search(r"(-?\d[\d.,]*)\s*(?:[µμ]m|um)\b", fwd)
        if mf and plausible_um(mf.group(1)):
            return full.replace(val, mf.group(1))
        start = match.start()
        bgn   = max(0, start - 200)
        bwd   = text_with_bindings[bgn:start]
        mb_iter = list(re.finditer(r"(-?\d[\d.,]*)\s*(?:[µμ]m|um)\b", bwd))
        if mb_iter:
            mb = mb_iter[-1]
            if plausible_um(mb.group(1)):
                return full.replace(val, mb.group(1))
        return full

    return re.sub(r"(?mi)\bCCT\s*:\s*([-\d.,]+)\s*(?:[µμ]m|um)\b", replace, text_with_bindings)


# =========================
# PT→EN (clues only)
# =========================
def localize_pt_to_en(text: str) -> str:
    t = text
    for pat, repl in [
        (r"\b(direita|olho\s+direito)\b", "RIGHT"),
        (r"\b(esquerda|esquerdo|olho\s+esquerdo)\b", "LEFT"),
        (r"\bpaciente\b", "PATIENT"),
        (r"\ban[aá]lise\b", "ANALYSIS"),
        (r"\bbranco a branco\b", "WHITE TO WHITE"),
    ]:
        t = re.sub(pat, repl, t, flags=re.IGNORECASE)
    return t


# =========================
# PDF layout split (text)
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

            blobs.sort(key=lambda t: -t[0])
            left_txt = "".join([b[1] for b in blobs if b[2]])
            right_txt = "".join([b[1] for b in blobs if not b[2]])
            left_chunks.append(left_txt)
            right_chunks.append(right_txt)
    except Exception as e:
        print(f"pdf layout split error: {e}")

    return {"left": "\n".join(left_chunks).strip(), "right": "\n".join(right_chunks).strip()}


# =========================
# Coordinate-based harvester (per column)
# =========================
_num_token = r"-?\d[\d.,]*"
MM = r"-?\d[\d.,]*\s*mm"
UM = r"-?\d[\d.,]*\s*(?:[µμ]m|um)"
DVAL = r"-?\d[\d.,]*\s*D"
LABEL_STOP = re.compile(r"(?:\r?\n|(?=(?:AL|ACD|CCT|LT|WTW|K1|K2|K|AK|ΔK)\s*:))", re.IGNORECASE)

def _clean(s: str) -> str:
    return re.sub(r"[ \t]+", " ", (s or "")).strip()

def coordinate_harvest(pdf_bytes: bytes) -> Dict[str, Dict[str, str]]:
    """
    Harvest scalars by PDF coordinates per column:
      - Find label lines (AL/ACD/LT/WTW/CCT, K1/K2/AK)
      - Search a vertical window *above* each label within same column for number+unit
      - Use plausibility ranges for tie-breaks (esp. CCT 400–700 µm)
    Returns: {"left": {...fields...}, "right": {...fields...}}
    """
    out_left = {"axial_length":"", "acd":"", "lt":"", "wtw":"", "cct":"", "k1":"", "k2":"", "ak":""}
    out_right = {"axial_length":"", "acd":"", "lt":"", "wtw":"", "cct":"", "k1":"", "k2":"", "ak":""}

    laparams = LAParams(all_texts=True)
    try:
        for page_layout in extract_pages(BytesIO(pdf_bytes), laparams=laparams):
            width = getattr(page_layout, "width", 1000.0)
            midx = width / 2.0

            # Collect lines with positions
            lines: List[tuple] = []  # (x0, y0, x1, y1, text)
            for el in page_layout:
                if isinstance(el, (LTTextLine, LTTextLineHorizontal, LTTextBoxHorizontal, LTTextBox)):
                    try:
                        x0, y0, x1, y1 = el.bbox
                        txt = el.get_text()
                        if txt and txt.strip():
                            for ln in txt.splitlines():
                                s = _clean(ln)
                                if s:
                                    lines.append((x0, y0, x1, y1, s))
                    except Exception:
                        continue

            # Split per column
            left_lines  = [ln for ln in lines if (ln[0]+ln[2])/2.0 <  midx]
            right_lines = [ln for ln in lines if (ln[0]+ln[2])/2.0 >= midx]

            # Sort top→bottom in each column
            left_lines.sort(key=lambda r: -r[3])
            right_lines.sort(key=lambda r: -r[3])

            def harvest_column(col_lines: List[tuple]) -> Dict[str,str]:
                found = {"axial_length":"", "acd":"", "lt":"", "wtw":"", "cct":"", "k1":"", "k2":"", "ak":""}

                # Build quick search helpers
                label_map = {
                    "AL":  "axial_length",
                    "ACD": "acd",
                    "LT":  "lt",
                    "WTW": "wtw",
                    "CCT": "cct",
                    "K1":  "k1",
                    "K2":  "k2",
                    "AK":  "ak",
                    "ΔK":  "ak",
                    "K":   "ak",  # later we will ignore K1/K2 for this
                }
                # Capture label rows (text exactly the label or "LABEL:")
                label_rows = []
                for x0,y0,x1,y1,txt in col_lines:
                    t = txt.upper().rstrip(":")
                    if t in ("AL","ACD","LT","WTW","CCT","K1","K2","AK","ΔK","K"):
                        label_rows.append((x0,y0,x1,y1,txt))

                # For each label row, look upward within ~120 pts for value+unit in the same column box
                def plaus_mm(v: float, key: str) -> bool:
                    if key == "axial_length": return 17.0 <= v <= 32.0
                    if key == "acd":          return 1.5  <= v <= 6.0
                    if key == "lt":           return 2.0  <= v <= 7.0
                    if key == "wtw":          return 9.0  <= v <= 15.0
                    return True

                def to_num(s: str) -> Optional[float]:
                    try:
                        s2 = s
                        for token in [" ", "µ", "μ", "um", "mm", "D", "°"]:
                            s2 = s2.replace(token, "")
                        s2 = s2.replace(".", "").replace(",", ".")
                        return float(s2)
                    except:
                        return None

                # index lines by y to search above efficiently
                for lx0,ly0,lx1,ly1,lbl in label_rows:
                    L = lbl.upper().rstrip(":")
                    key = label_map.get(L)
                    if not key: 
                        continue

                    # Skip K if it's actually K1 or K2; we handle AK as cylinder
                    if L == "K" and any("K1" in r[4].upper() or "K2" in r[4].upper() for r in col_lines):
                        continue

                    # search window: from label baseline up by ~140 points
                    top = ly1 + 140.0
                    bot = ly0 - 4.0  # include same line slight overlap
                    cand = []

                    for x0,y0,x1,y1,txt in col_lines:
                        if y1 <= top and y0 >= bot:
                            # same column region horizontally (loose overlap with label box)
                            if not (x1 < lx0 - 5 or x0 > lx1 + 5):
                                # collect candidates by unit
                                if key == "cct":
                                    # µm only
                                    m = re.search(rf"({_num_token})\s*(?:[µμ]m|um)\b", txt, flags=re.IGNORECASE)
                                    if m:
                                        v = to_num(m.group(1))
                                        if v is not None and 350 <= v <= 800:
                                            dist = abs((ly0 + ly1)/2.0 - (y0 + y1)/2.0)
                                            cand.append((dist, f"{m.group(1)} µm"))
                                elif key in ("axial_length","acd","lt","wtw"):
                                    m = re.search(rf"({_num_token})\s*mm\b", txt, flags=re.IGNORECASE)
                                    if m:
                                        v = to_num(m.group(1))
                                        if v is not None and plaus_mm(v, key):
                                            dist = abs((ly0 + ly1)/2.0 - (y0 + y1)/2.0)
                                            cand.append((dist, f"{m.group(1)} mm"))
                                elif key in ("k1","k2","ak"):
                                    # diopters possibly with axis nearby on same line
                                    md = re.search(rf"({_num_token})\s*D\b", txt, flags=re.IGNORECASE)
                                    if md:
                                        axis = ""
                                        ma = re.search(r"@\s*(\d{1,3})\s*(?:°|º|o)\b", txt)
                                        if ma:
                                            axis = f" @ {ma.group(1)}°"
                                        dist = abs((ly0 + ly1)/2.0 - (y0 + y1)/2.0)
                                        cand.append((dist, f"{md.group(1)} D{axis}"))

                    if cand and not found[key]:
                        cand.sort(key=lambda t: t[0])
                        found[key] = cand[0][1]

                return found

            left_vals  = harvest_column(left_lines)
            right_vals = harvest_column(right_lines)

            # Merge with page results (if multiple pages, first non-empty wins)
            for k,v in left_vals.items():
                if v and not out_left[k]:
                    out_left[k] = v
            for k,v in right_vals.items():
                if v and not out_right[k]:
                    out_right[k] = v

    except Exception as e:
        print(f"coordinate_harvest error: {e}")

    return {"left": out_left, "right": out_right}


# =========================
# Patterns & parsing helpers (text-based)
# =========================
PATTERNS = {
    "axial_length": re.compile(rf"(?mi)\bAL\s*:\s*({MM})"),
    "acd":          re.compile(rf"(?mi)\bACD\s*:\s*({MM})"),
    "cct":          re.compile(rf"(?mi)\bCCT\s*:\s*({UM})"),
    "lt":           re.compile(rf"(?mi)\bLT\s*:\s*({MM})"),
    "wtw":          re.compile(rf"(?mi)\bWTW\s*:\s*({MM})"),
    "k1":           re.compile(rf"(?mi)\bK1\s*:\s*({DVAL})"),
    "k2":           re.compile(rf"(?mi)\bK2\s*:\s*({DVAL})"),
    "ak":           re.compile(rf"(?mi)\b(?:Δ\s*K|AK|K(?!\s*1|\s*2))\s*:\s*({DVAL})"),
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
    out = {"axial_length":"", "acd":"", "k1":"", "k2":"", "ak":"", "wtw":"", "cct":"", "lt":""}
    if not txt or not txt.strip():
        return out
    for key, pat in PATTERNS.items():
        for m in pat.finditer(txt):
            raw = re.sub(r"\s+", " ", m.group(1)).strip()
            if key in ("k1", "k2", "ak"):
                raw = re.sub(r"@\s*.*$", "", raw)
                tail = txt[m.end(1): m.end(1) + 200]
                raw = (raw + harvest_axis(tail)).strip()
            if not out[key]:
                out[key] = raw
    return out

def has_measurements(d: dict) -> bool:
    return any(d.values())


# =========================
# Rescue harvester (tolerant)
# =========================
RESCUE = {
    "axial_length": re.compile(r"(?mi)\bAL\s*[:=]?\s*(-?\d[\d.,]*)\s*mm\b"),
    "acd":          re.compile(r"(?mi)\bACD\s*[:=]?\s*(-?\d[\d.,]*)\s*mm\b"),
    "lt":           re.compile(r"(?mi)\bLT\s*[:=]?\s*(-?\d[\d.,]*)\s*mm\b"),
    "wtw":          re.compile(r"(?mi)\bWTW\s*[:=]?\s*(-?\d[\d.,]*)\s*mm\b"),
    "cct":          re.compile(r"(?mi)\bCCT\s*[:=]?\s*(?:(-?\d[\d.,]*)\s*(?:[µμ]m|um)|(?:[µμ]m|um)\s*\n\s*(-?\d[\d.,]*))"),
    "k1":           re.compile(r"(?mi)\bK1\s*[:=]?\s*(-?\d[\d.,]*)\s*D(?:.*?@\s*(\d{1,3}))?"),
    "k2":           re.compile(r"(?mi)\bK2\s*[:=]?\s*(-?\d[\d.,]*)\s*D(?:.*?@\s*(\d{1,3}))?"),
    "ak":           re.compile(r"(?mi)\b(?:Δ\s*K|AK|K(?!\s*1|\s*2))\s*[:=]?\s*(-?\d[\d.,]*)\s*D(?:.*?@\s*(\d{1,3}))?")
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
        if num: setv("cct", f"{num} µm")

    for k in ("k1", "k2", "ak"):
        m = RESCUE[k].search(raw_text)
        if m:
            diop = m.group(1)
            axis = m.group(2)
            val = f"{diop} D"
            if axis: val += f" @ {axis}°"
            setv(k, val)

    return out


# =========================
# Reconcile
# =========================
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


# =========================
# Plausibility re-score (final safety net)
# =========================
PLAUSIBLE = {
    "axial_length": lambda x: 17.0 <= x <= 32.0,
    "acd":          lambda x: 1.5  <= x <= 6.0,
    "lt":           lambda x: 2.0  <= x <= 7.0,
    "wtw":          lambda x: 9.0  <= x <= 15.0,
    "cct_um":       lambda x: 350  <= x <= 800,
    "k_diopters":   lambda x: 30.0 <= x <= 55.0,
    "cyl_diopters": lambda x: 0.0  <= x <= 10.0,
    "axis_deg":     lambda x: 0    <= x <= 180,
}
NOISE_LABELS = re.compile(r"(?mi)\b(?:CVD|SD|WTW|P|TK1|TK2|TSE|B-Scan|Fixação)\b")

def _num(s: str) -> Optional[float]:
    try:
        s2 = s
        for token in [" ", "µ", "μ", "um", "mm", "D", "°"]:
            s2 = s2.replace(token, "")
        s2 = s2.replace(".", "").replace(",", ".")
        return float(s2)
    except:
        return None

def _score_candidate(label: str, value_str: str, ctx: str, unit_kind: str) -> float:
    vlow = value_str.lower()
    unit_ok = (unit_kind=="mm" and "mm" in vlow) or \
              (unit_kind=="um" and ("µm" in vlow or "μm" in vlow or "um" in vlow)) or \
              (unit_kind=="D"  and "d" in vlow)
    if not unit_ok: return -1.0

    v = _num(value_str)
    plaus = 0.0
    if v is not None:
        if label == "CCT":
            plaus = 1.0 if PLAUSIBLE["cct_um"](v) else -0.5
        elif label in ("AL", "ACD", "LT", "WTW"):
            key = {"AL":"axial_length", "ACD":"acd", "LT":"lt", "WTW":"wtw"}[label]
            plaus = 1.0 if PLAUSIBLE[key](v) else -0.5

    noise = -0.6 if NOISE_LABELS.search(ctx) else 0.0
    prox = max(0.0, 0.8 - 0.001*len(ctx))
    return (1.5 if unit_ok else 0) + plaus + noise + prox

def plausibility_rescore(eye_text: str, data: dict) -> dict:
    out = dict(data)
    def current_ok(key: str, unit: str) -> bool:
        cur = (out.get(key) or "").strip()
        if not cur: return False
        valn = _num(cur)
        if valn is None: return False
        if unit == "um": return PLAUSIBLE["cct_um"](valn)
        return PLAUSIBLE[{"axial_length":"axial_length","acd":"acd","lt":"lt","wtw":"wtw"}[key]](valn)

    for lab, key, unit in [("AL","axial_length","mm"), ("ACD","acd","mm"),
                           ("LT","lt","mm"), ("WTW","wtw","mm"), ("CCT","cct","um")]:
        if current_ok(key, unit):
            continue
        best = (None, -9e9)
        for m in re.finditer(rf"(?mi)\b{lab}\s*:", eye_text):
            anchor = m.end()
            win_beg, win_end = max(0, anchor-220), min(len(eye_text), anchor+220)
            win = eye_text[win_beg:win_end]
            for cand in re.finditer(r"(-?\d[\d.,]*)\s*(mm|[µμ]m|um|D)\b", win, flags=re.IGNORECASE):
                s = f"{cand.group(1)} {cand.group(2)}"
                sc = _score_candidate(lab, s, win, "um" if unit=="um" else ("mm" if unit=="mm" else "D"))
                if sc > best[1]: best = (s, sc)
            for cand in re.finditer(r"(mm|[µμ]m|um|D)\s*\n\s*(-?\d[\d.,]*)\b", win, flags=re.IGNORECASE):
                s = f"{cand.group(2)} {cand.group(1)}"
                sc = _score_candidate(lab, s, win, "um" if unit=="um" else ("mm" if unit=="mm" else "D"))
                if sc > best[1]: best = (s, sc)
        if best[0]:
            out[key] = re.sub(r"(?i)\bum\b", "µm", best[0]) if unit == "um" else best[0]

    # CCT extra fallback (nearest plausible µm near any scalar label)
    if not current_ok("cct", "um"):
        anchors = []
        for lab in ("AL", "ACD", "LT", "WTW"):
            for m in re.finditer(rf"(?mi)\b{lab}\s*:", eye_text):
                anchors.append(m.end())
        if not anchors:
            anchors = [len(eye_text)//2]
        candidates = []
        for m in re.finditer(r"(-?\d[\d.,]{2,})\s*(?:[µμ]m|um)\b", eye_text):
            val = m.group(1); v = _num(val)
            if v is None or not PLAUSIBLE["cct_um"](v): continue
            pos = m.start()
            dist = min(abs(pos - a) for a in anchors)
            candidates.append((dist, f"{val} µm"))
        if candidates:
            candidates.sort(key=lambda x: x[0])
            out["cct"] = candidates[0][1]

    return out


# =========================
# Detect device & ordering
# =========================
def detect_source_label(text: str) -> str:
    if re.search(r"IOL\s*Master\s*700", text, re.IGNORECASE):
        return "IOL Master 700"
    if re.search(r"OCULUS\s+PENTACAM", text, re.IGNORECASE):
        return "Pentacam"
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "Unknown")
    return first[:60]

FIELD_ORDER = ["source", "axial_length", "acd", "k1", "k2", "ak", "wtw", "cct", "lt"]
def enforce_field_order(eye_dict: dict) -> OrderedDict:
    return OrderedDict((k, eye_dict.get(k, "")) for k in FIELD_ORDER)


# =========================
# Controller
# =========================
def parse_iol(norm_text: str, pdf_bytes: Optional[bytes], source_label: str, want_debug: bool = False):
    def fresh():
        return OrderedDict(
            [("source", source_label), ("axial_length",""), ("acd",""), ("k1",""), ("k2",""),
             ("ak",""), ("wtw",""), ("cct",""), ("lt","")]
        )

    result = {"OD": fresh(), "OS": fresh()}
    debug = {"strategy":"", "left_len":0, "right_len":0, "left_preview":"", "right_preview":"", "mapping":""}

    left_txt = right_txt = None
    coord_vals = {"left": {}, "right": {}}
    if pdf_bytes:
        try:
            cols = pdf_split_left_right(pdf_bytes)
            left_txt, right_txt = cols.get("left",""), cols.get("right","")
            # NEW: coordinate-based harvest (per column)
            coord_vals = coordinate_harvest(pdf_bytes)
            debug["strategy"] = "pdf_layout_split + coord_harvest"
            debug["left_len"] = len(left_txt or "")
            debug["right_len"] = len(right_txt or "")
        except Exception as e:
            print(f"layout/coord split failed: {e}")

    if left_txt is not None and right_txt is not None:
        # Normalize → strict bind → CCT sanity → localize
        left_norm  = localize_pt_to_en(smart_fix_cct_bound(bind_disjoint_scalars(normalize_for_ocr(left_txt))))
        right_norm = localize_pt_to_en(smart_fix_cct_bound(bind_disjoint_scalars(normalize_for_ocr(right_txt))))
        if want_debug:
            debug["left_preview"]  = left_norm[:600]
            debug["right_preview"] = right_norm[:600]

        # Primary text parse
        left_data  = parse_eye_block(left_norm)
        right_data = parse_eye_block(right_norm)

        # Bound scalar dicts (from normalized text)
        def scalars_from_bound(nrm: str) -> dict:
            d = {}
            for lab, key in [("AL","axial_length"), ("ACD","acd"), ("LT","lt"), ("WTW","wtw"), ("CCT","cct")]:
                m = re.search(rf"(?mi)\b{lab}\s*:\s*(-?\d[\d.,]*)\s*(?:mm|[µμ]m|um)\b", nrm)
                if m:
                    unit = "µm" if lab == "CCT" else "mm"
                    d[key] = f"{m.group(1)} {unit}"
            return d

        left_bound  = scalars_from_bound(left_norm)
        right_bound = scalars_from_bound(right_norm)

        # Rescue (tolerant)
        left_rescue  = rescue_harvest(left_norm)
        right_rescue = rescue_harvest(right_norm)

        # Reconcile text-based
        left_final  = reconcile(left_data,  left_bound,  left_rescue)
        right_final = reconcile(right_data, right_bound, right_rescue)

        # NEW: Merge coordinate-based values to fill any empties (esp. OS CCT)
        for k,v in coord_vals.get("left", {}).items():
            if v and not left_final.get(k):
                left_final[k] = v
        for k,v in coord_vals.get("right", {}).items():
            if v and not right_final.get(k):
                right_final[k] = v

        # Plausibility re-score pass
        left_final  = plausibility_rescore(left_norm,  left_final)
        right_final = plausibility_rescore(right_norm, right_final)

        # Map OD/OS by clues
        def looks_od(s: str) -> bool:
            u = s.upper()
            return bool(re.search(r"\bOD\b|\bO\s*D\b|RIGHT\b", u))
        def looks_os(s: str) -> bool:
            u = s.upper()
            return bool(re.search(r"\bOS\b|\bO\s*S\b|\bOE\b|\bO\s*E\b|LEFT\b", u))

        left_is_od, left_is_os   = looks_od(left_txt),  looks_os(left_txt)
        right_is_od, right_is_os = looks_od(right_txt), looks_os(right_txt)

        if left_is_od and right_is_os:
            mapping = {"OD": left_final, "OS": right_final};  debug["mapping"] = "OD<-left, OS<-right (labels)"
        elif left_is_os and right_is_od:
            mapping = {"OD": right_final, "OS": left_final};  debug["mapping"] = "OD<-right, OS<-left (labels)"
        else:
            mapping = {"OD": left_final, "OS": right_final};  debug["mapping"] = "OD<-left, OS<-right (default)"

        # Copy into result
        for eye in ("OD","OS"):
            for k,v in mapping[eye].items():
                if v: result[eye][k] = v

        # OPTIONAL: assume_same_cct=1 copies OD->OS if OS missing
        assume_same_cct = request.args.get("assume_same_cct") == "1"
        if assume_same_cct and not result["OS"].get("cct") and result["OD"].get("cct"):
            result["OS"]["cct"] = result["OD"]["cct"]

        # Enforce output order (source first)
        result["OD"] = enforce_field_order(result["OD"])
        result["OS"] = enforce_field_order(result["OS"])

        return (result, debug) if want_debug else result

    # No layout info → single block → OD
    single = localize_pt_to_en(smart_fix_cct_bound(bind_disjoint_scalars(normalize_for_ocr(norm_text))))
    parsed = parse_eye_block(single)
    for k,v in parsed.items():
        if v: result["OD"][k] = v

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
        "version": "LakeCalc.ai parser v3.8 (coord harvest + strict binder + sanity + rescue + plausibility + ordered)",
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
            loc_preview = localize_pt_to_en(smart_fix_cct_bound(bind_disjoint_scalars(norm_text)))
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
                "raw_text_preview": localize_pt_to_en(smart_fix_cct_bound(bind_disjoint_scalars(norm_text)))[:1500]
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