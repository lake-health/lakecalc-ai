import re
from typing import Tuple, Dict, Optional
from app.models.schema import ExtractedBiometry, ExtractedKs

MM = r"(?:(?:mm)|(?:\s?mm))"
UM = r"(?:(?:µm)|(?:um)|(?:microns?))"
D  = r"(?:D|diopters?)"
DEG = r"(?:°|deg|degrees?)"

def _find_float(pattern: str, text: str) -> Tuple[Optional[float], float]:
    m = re.search(pattern, text, flags=re.IGNORECASE)
    if not m:
        return None, 0.0
    try:
        return float(m.group(1).replace(',', '.')), 0.8
    except Exception:
        return None, 0.0

def parse_biometry(raw_text: str) -> ExtractedBiometry:
    device_match = re.search(r"(IOLMaster\s*700|NIDEK[-\s]?ALScan|Pentacam|Galilei|Atlas\s*9000|EyeSys)", raw_text, re.I)
    device = device_match.group(1) if device_match else None
    device_conf = 0.6 if device else 0.0

    eye_match = re.search(r"\b(OD|OS)\b", raw_text)
    eye = eye_match.group(1) if eye_match else None
    eye_conf = 0.7 if eye else 0.0

    # Extract gender from patient information
    gender = None
    gender_conf = 0.0
    
    # Try multiple gender patterns
    gender_patterns = [
        (r"Sexo[:\s]*(Masculino|Male|M)", "M"),
        (r"Sexo[:\s]*(Feminino|Female|F)", "F"),
        (r"Gender[:\s]*(Male|M|Masculino)", "M"),
        (r"Gender[:\s]*(Female|F|Feminino)", "F"),
        (r"\b(Male|Masculino)\b", "M"),
        (r"\b(Female|Feminino)\b", "F")
    ]
    
    for pattern, gender_code in gender_patterns:
        match = re.search(pattern, raw_text, re.I)
        if match:
            gender = gender_code
            gender_conf = 0.9
            break

    al, al_c   = _find_float(r"AL[:\s]*([0-9]+(?:[.,][0-9]+)?)\s*" + MM, raw_text)
    acd, acd_c = _find_float(r"ACD[:\s]*([0-9]+(?:[.,][0-9]+)?)\s*" + MM, raw_text)
    lt, lt_c   = _find_float(r"LT[:\s]*([0-9]+(?:[.,][0-9]+)?)\s*" + MM, raw_text)
    wtw, wtw_c = _find_float(r"WTW[:\s]*([0-9]+(?:[.,][0-9]+)?)\s*" + MM, raw_text)
    cct, cct_c = _find_float(r"CCT[:\s]*([0-9]+)\s*" + UM, raw_text)

    k1_power, k1c   = _find_float(r"K1[:\s]*([0-9]+(?:[.,][0-9]+)?)\s*" + D, raw_text)
    k2_power, k2c   = _find_float(r"K2[:\s]*([0-9]+(?:[.,][0-9]+)?)\s*" + D, raw_text)
    k1_axis, k1ax_c = _find_float(r"K1[^@\n]*@\s*([0-9]+(?:[.,][0-9]+)?)\s*" + DEG, raw_text)
    k2_axis, k2ax_c = _find_float(r"K2[^@\n]*@\s*([0-9]+(?:[.,][0-9]+)?)\s*" + DEG, raw_text)

    delta_k = None
    if k1_power is not None and k2_power is not None:
        delta_k = round(abs(k2_power - k1_power), 2)

    ks = ExtractedKs(
        k1_power=k1_power,
        k1_axis=k1_axis,
        k2_power=k2_power,
        k2_axis=k2_axis,
        delta_k=delta_k,
    )

    confidence: Dict[str, float] = {
        "device": device_conf,
        "eye": eye_conf,
        "gender": gender_conf,
        "al_mm": al_c,
        "acd_mm": acd_c,
        "lt_mm": lt_c,
        "wtw_mm": wtw_c,
        "cct_um": cct_c,
        "k1_power": k1c,
        "k1_axis": k1ax_c,
        "k2_power": k2c,
        "k2_axis": k2ax_c,
    }

    return ExtractedBiometry(
        device=device,
        eye=eye,
        al_mm=al,
        acd_mm=acd,
        lt_mm=lt,
        wtw_mm=wtw,
        cct_um=int(cct) if cct is not None else None,
        gender=gender,
        ks=ks,
        notes=None,
        confidence=confidence,
    )

