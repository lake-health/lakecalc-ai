# app.py — LakeCalc.ai parser v3.11
# v3.10 + per-page column detection + front-page-first strategy
# Keeps original flow: normalize → strict binder (CCT special) → sanity → parse → rescue → plausibility → order
# Adds:
#   - page counting
#   - page-wise 1/2-column classifier
#   - per-page text harvest (left/right)
#   - early-stop when both eyes are sufficiently populated from first pages

import os, io, re, math
from collections import OrderedDict, defaultdict
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
# Utils
# =========================
def _clean_spaces(s: str) -> str:
    return re.sub(r"[ \t]+", " ", s or "").strip()

def _num(s: str) -> Optional[float]:
    try:
        s2 = s
        for token in [" ", "µ", "μ", "um", "mm", "D", "°"]:
            s2 = s2.replace(token, "")
        s2 = s2.replace(".", "").replace(",", ".")
        return float(s2)
    except:
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
# OCR helpers
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
# Patterns & parsing helpers (text-based)
# =========================
_num_token = r"-?\d[\d.,]*"
MM = r"-?\d[\d.,]*\s*mm"
UM = r"-?\d[\d.,]*\s*(?:[µμ]m|um)"
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

# =========================
# Rescue (tolerant)
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
}
NOISE_LABELS = re.compile(r"(?mi)\b(?:CVD|SD|WTW|P|TK1|TK2|TSE|B-Scan|Fixação)\b")

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
# Per-page column detection & harvest
# =========================
def classify_columns_for_page(page_layout) -> str:
    """
    Heuristic: build a histogram of text line center-x; if we see two clusters
    with a big gap between them (and both are populous), call it 'double' else 'single'.
    """
    centers = []
    xs = []
    for el in page_layout:
        if isinstance(el, (LTTextLine, LTTextLineHorizontal, LTTextBox, LTTextBoxHorizontal)):
            x0, y0, x1, y1 = el.bbox
            centers.append((x0+x1)/2.0)
            xs += [x0, x1]
    if not centers:
        return "single"
    page_width = max(xs) if xs else 1000.0
    # simple 2-bin split at midx
    midx = page_width/2.0
    left_count = sum(1 for c in centers if c < midx*0.98)
    right_count = sum(1 for c in centers if c > midx*1.02)  # small dead zone
    # also check gap density near mid
    near_mid = sum(1 for c in centers if abs(c - midx) < 25)
    if left_count > 8 and right_count > 8 and near_mid < 0.25*(left_count+right_count):
        return "double"
    return "single"

def harvest_page_texts(pdf_bytes: bytes) -> Dict[int, Dict[str, str]]:
    """
    Return per-page dict:
      page_map[p] = {"mode": "single"|"double", "left": "...", "right": "...", "full": "..."}
    """
    laparams = LAParams(all_texts=True)
    out = {}
    try:
        for pnum, page_layout in enumerate(extract_pages(BytesIO(pdf_bytes), laparams=laparams), start=1):
            mode = classify_columns_for_page(page_layout)
            # gather lines with bbox
            lines = []
            xs = []
            for el in page_layout:
                if isinstance(el, (LTTextLine, LTTextLineHorizontal, LTTextBox, LTTextBoxHorizontal)):
                    x0, y0, x1, y1 = el.bbox
                    txt = el.get_text()
                    if txt and txt.strip():
                        for ln in txt.splitlines():
                            s = _clean_spaces(ln)
                            if s:
                                lines.append((x0, y0, x1, y1, s))
                    xs += [x0, x1]
            page_width = max(xs) if xs else 1000.0
            midx = page_width/2.0
            # order by top→bottom
            lines.sort(key=lambda r: -r[3])
            if mode == "single":
                full = "\n".join([t[4] for t in lines])
                out[pnum] = {"mode":"single", "left":"", "right":"", "full":full}
            else:
                left_lines = [t for t in lines if (t[0]+t[2])/2.0 < midx]
                right_lines = [t for t in lines if (t[0]+t[2])/2.0 >= midx]
                left_txt = "\n".join([t[4] for t in left_lines])
                right_txt = "\n".join([t[4] for t in right_lines])
                out[pnum] = {"mode":"double", "left":left_txt, "right":right_txt, "full":""}
    except Exception as e:
        print(f"[WARN] harvest_page_texts: {e}")
    return out

# =========================
# Front-page-first orchestration
# =========================
def enough_fields(d: dict) -> bool:
    """Define what 'good enough' means to stop early (tune as needed)."""
    have = 0
    for k in ("axial_length","acd","k1","k2","wtw","cct","lt","ak"):
        if d.get(k): have += 1
    return have >= 5  # threshold

def parse_eye_block_ordered(txt: str) -> dict:
    parsed = parse_eye_block(txt)
    return OrderedDict((k, parsed.get(k, "")) for k in ["axial_length","acd","k1","k2","ak","wtw","cct","lt"])

def scalars_from_bound(nrm: str) -> dict:
    d = {}
    for lab, key in [("AL","axial_length"), ("ACD","acd"), ("LT","lt"), ("WTW","wtw"), ("CCT","cct")]:
        m = re.search(rf"(?mi)\b{lab}\s*:\s*(-?\d[\d.,]*)\s*(?:mm|[µμ]m|um)\b", nrm)
        if m:
            unit = "µm" if lab == "CCT" else "mm"
            d[key] = f"{m.group(1)} {unit}"
    return d

def process_eye_text(raw: str) -> dict:
    nrm = localize_pt_to_en(smart_fix_cct_bound(bind_disjoint_scalars(normalize_for_ocr(raw))))
    base   = parse_eye_block_ordered(nrm)
    bound  = scalars_from_bound(nrm)
    rescue = rescue_harvest(nrm)
    merged = reconcile(base, bound, rescue)
    final  = plausibility_rescore(nrm, merged)
    return final

def map_eyes_by_clues(left_txt: str, right_txt: str) -> Tuple[str, str]:
    def looks_od(s: str) -> bool:
        u = (s or "").upper()
        return bool(re.search(r"\bOD\b|\bO\s*D\b|RIGHT\b", u))
    def looks_os(s: str) -> bool:
        u = (s or "").upper()
        return bool(re.search(r"\bOS\b|\bO\s*S\b|\bOE\b|\bO\s*E\b|LEFT\b", u))
    left_is_od, left_is_os   = looks_od(left_txt),  looks_os(left_txt)
    right_is_od, right_is_os = looks_od(right_txt), looks_os(right_txt)
    if left_is_od and right_is_os:
        return "left->OD,right->OS"
    if left_is_os and right_is_od:
        return "left->OS,right->OD"
    # default to left->OD, right->OS
    return "left->OD,right->OS"

def parse_across_pages(pdf_bytes: bytes, source_label: str, want_debug: bool=False):
    page_map = harvest_page_texts(pdf_bytes)
    pages = sorted(page_map.keys())
    debug = {
        "page_count": len(pages),
        "page_modes": {p: page_map[p]["mode"] for p in pages},
        "early_stop": False,
        "strategy": "per-page harvest + front-page-first",
        "mapping": "",
    }

    # Accumulators
    OD = OrderedDict([("source", source_label), ("axial_length",""),("acd",""),("k1",""),("k2",""),("ak",""),("wtw",""),("cct",""),("lt","")])
    OS = OrderedDict([("source", source_label), ("axial_length",""),("acd",""),("k1",""),("k2",""),("ak",""),("wtw",""),("cct",""),("lt","")])

    # Phase 1: first two pages preferred
    preferred = [p for p in pages if p <= 2]
    if not preferred:
        preferred = pages[:2]

    def merge_if_empty(dst: OrderedDict, src: dict):
        for k, v in src.items():
            if k == "source": continue
            if v and not dst.get(k):
                dst[k] = v

    # pass 1: preferred pages
    for p in preferred:
        pm = page_map[p]
        if pm["mode"] == "single":
            full = pm["full"]
            # Heuristic: single column pages are often headers/summary; run once and try to detect OD/OS by clues
            parsed_full = process_eye_text(full)
            # We don't know side, so only merge safe fields that clearly look like global scalars? We'll be conservative:
            # In practice these pages often have either OD or OS label inside; try mapping via clues chunking.
            # Split by OD/OS markers roughly:
            blocks = re.split(r"(?mi)\b(OD|OS|RIGHT|LEFT)\b", full)
            if len(blocks) >= 3:
                # Reconstruct simple pairs: [text_before, LABEL, block_after, LABEL, block_after, ...]
                for i in range(1, len(blocks), 2):
                    lab = blocks[i].upper()
                    blk = blocks[i+1] if i+1 < len(blocks) else ""
                    parsed_blk = process_eye_text(blk)
                    if lab in ("OD","RIGHT"):
                        merge_if_empty(OD, parsed_blk)
                    elif lab in ("OS","LEFT"):
                        merge_if_empty(OS, parsed_blk)
            else:
                # If we cannot split, do nothing on single page pass here.
                pass
        else:
            left_txt, right_txt = pm["left"], pm["right"]
            # Decide mapping
            mapping = map_eyes_by_clues(left_txt, right_txt)
            debug["mapping"] = mapping or debug["mapping"]
            if mapping == "left->OS,right->OD":
                left_dst, right_dst = OS, OD
            else:  # default left->OD,right->OS
                left_dst, right_dst = OD, OS
            left_parsed  = process_eye_text(left_txt)
            right_parsed = process_eye_text(right_txt)
            merge_if_empty(left_dst,  left_parsed)
            merge_if_empty(right_dst, right_parsed)

        if enough_fields(OD) and enough_fields(OS):
            debug["early_stop"] = True
            break

    # Phase 2: if still incomplete, scan remaining pages
    if not (enough_fields(OD) and enough_fields(OS)):
        for p in pages:
            if p in preferred: 
                continue
            pm = page_map[p]
            if pm["mode"] == "single":
                full = pm["full"]
                # Same conservative logic as above
                blocks = re.split(r"(?mi)\b(OD|OS|RIGHT|LEFT)\b", full)
                if len(blocks) >= 3:
                    for i in range(1, len(blocks), 2):
                        lab = blocks[i].upper()
                        blk = blocks[i+1] if i+1 < len(blocks) else ""
                        parsed_blk = process_eye_text(blk)
                        if lab in ("OD","RIGHT"):
                            merge_if_empty(OD, parsed_blk)
                        elif lab in ("OS","LEFT"):
                            merge_if_empty(OS, parsed_blk)
            else:
                left_txt, right_txt = pm["left"], pm["right"]
                mapping = map_eyes_by_clues(left_txt, right_txt)
                debug["mapping"] = mapping or debug["mapping"]
                if mapping == "left->OS,right->OD":
                    left_dst, right_dst = OS, OD
                else:
                    left_dst, right_dst = OD, OS
                left_parsed  = process_eye_text(left_txt)
                right_parsed = process_eye_text(right_txt)
                merge_if_empty(left_dst,  left_parsed)
                merge_if_empty(right_dst, right_parsed)

            if enough_fields(OD) and enough_fields(OS):
                debug["early_stop"] = True
                break

    return {
        "OD": enforce_field_order(OD),
        "OS": enforce_field_order(OS),
    }, debug

# =========================
# Controller
# =========================
def parse_iol(norm_text: str, pdf_bytes: Optional[bytes], source_label: str, want_debug: bool = False):
    # If we have the PDF bytes, prefer structured per-page pipeline
    if pdf_bytes:
        try:
            structured, dbg = parse_across_pages(pdf_bytes, source_label, want_debug)
            if want_debug:
                return structured, dbg
            return structured
        except Exception as e:
            print(f"[WARN] parse_across_pages failed: {e}")

    # Fallback: single-block to OD (legacy)
    def fresh():
        return OrderedDict(
            [("source", source_label), ("axial_length",""), ("acd",""), ("k1",""), ("k2",""),
             ("ak",""), ("wtw",""), ("cct",""), ("lt","")]
        )
    result = {"OD": fresh(), "OS": fresh()}
    single = localize_pt_to_en(smart_fix_cct_bound(bind_disjoint_scalars(normalize_for_ocr(norm_text))))
    parsed = parse_eye_block(single)
    for k,v in parsed.items():
        if v: result["OD"][k] = v
    result["OD"] = enforce_field_order(result["OD"])
    result["OS"] = enforce_field_order(result["OS"])
    dbg = {"strategy":"ocr_single_block_to_OD"}
    return (result, dbg) if want_debug else result

# =========================
# Routes
# =========================
@app.route("/api/health")
def health():
    return jsonify({
        "status": "running",
        "version": "LakeCalc.ai parser v3.11 (per-page columns + front-page-first + original pipeline)",
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
