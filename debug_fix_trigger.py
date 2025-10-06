#!/usr/bin/env python3
"""
Debug script to check if the fix is being triggered.
"""

import sys
import os
import re
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.parser import parse_text

# Right Eye (OD) text from the first image
od_text = """OD
direita
Valores biométricos
AL: 23,73 mm
SD: 20 μm
WTW: 11,9 mm (!) lx: +0,3 mm
CCT: 554 μm
SD: 4 μm
P: 2,7 mm
ly: +0,0 mm
CW-Chord: 0,3 mm @ 212°
ACD: 2,89 mm
SD: 10 μm
LT: 4,90 mm
SD: 20 μm
SE: 42,30 D
K1: 40,95 D
K2: 43,74 D
AK: -2,79 D
SD: 0,01 D
TSE:
@ 100°
SD: 0,02 D
TK1:
@ 10°
@ 100°
SD: 0,01 D
TK2:
ATK:
Ref: IOLMaster700"""

def debug_fix_trigger():
    """Debug if the fix is being triggered."""
    print("=== DEBUGGING FIX TRIGGER ===")
    
    # Parse the text
    result = parse_text("test-od", od_text, llm_func=lambda t, m: {"od": {}, "os": {}})
    
    print(f"OD K1: {result.od.k1}")
    print(f"OD K2: {result.od.k2}")
    print(f"OD K1 Axis: {result.od.k1_axis}")
    print(f"OD K2 Axis: {result.od.k2_axis}")
    
    # Let's manually trace through the fallback logic to see what's happening
    print("\n=== MANUAL FALLBACK TRACE ===")
    
    # Find all axis occurrences
    axis_occurrences = []
    for m in re.finditer(r"@\s*(\d{1,3})\s*°", od_text):
        s = m.start()
        # extract the full line containing this axis
        line_start = od_text.rfind('\n', 0, s) + 1
        line_end = od_text.find('\n', s)
        line = od_text[line_start: line_end if line_end != -1 else None]
        
        # skip axes that are part of measurements in mm or explicitly CW-Chord or TSE/TK lines
        should_skip = re.search(r"\bmm\b|CW[- ]?Chord|Chord\b|\bTSE\b|\bSD\b|TK\d*", line, re.I)
        if should_skip:
            continue
        
        # skip numeric-only or very short noisy lines
        if re.fullmatch(r"\s*\d{1,4}\s*", line):
            continue
        
        # sanitize the matched token
        def sanitize_axis(raw_candidate: str) -> str | None:
            if not raw_candidate:
                return None
            groups = re.findall(r"(\d{1,3})", raw_candidate)
            if not groups:
                return None
            candidate = groups[-1]
            try:
                iv = int(candidate)
            except Exception:
                return None
            if 0 <= iv <= 180:
                return str(iv)
            return None
        
        clean = sanitize_axis(m.group(1))
        if clean:
            axis_occurrences.append((s, clean))
    
    print(f"Valid axis occurrences: {axis_occurrences}")
    
    # Find K1/K2 anchor positions
    anchors = {}
    for klabel in ("K1", "K2"):
        m = re.search(rf"\b{klabel}\b\s*[:\-]?\s*\d{{1,3}}[\.,]\d{{1,3}}\s*D", od_text, re.I)
        if m:
            anchors[klabel.lower()] = m.start()
    
    # Simulate the proximity-based assignment
    out = {}
    for kkey, apos in anchors.items():
        best = None
        best_dist = None
        for pos, val in axis_occurrences:
            dist = abs(pos - apos)
            if best is None or dist < best_dist:
                best = val
                best_dist = dist
        if best:
            out[f"{kkey}_axis"] = best
    
    print(f"After proximity assignment: {out}")
    
    # Check if the fix condition is met
    k1_axis = out.get("k1_axis")
    k2_axis = out.get("k2_axis")
    k1_val = "40,95"  # From the text
    k2_val = "43,74"  # From the text
    
    print(f"\nFix condition check:")
    print(f"  k1_axis == k2_axis: {k1_axis == k2_axis}")
    print(f"  k1_axis exists: {bool(k1_axis)}")
    print(f"  k2_axis exists: {bool(k2_axis)}")
    print(f"  k1 exists: {bool(k1_val)}")
    print(f"  k2 exists: {bool(k2_val)}")
    
    condition_met = (k1_axis == k2_axis and 
                     k1_axis and k2_axis and
                     k1_val and k2_val)
    
    print(f"  Fix condition met: {condition_met}")
    
    if condition_met:
        print("  ✅ Fix should be triggered!")
        try:
            k1_axis_num = int(k1_axis)
            k2_axis_num = (k1_axis_num + 90) % 180
            print(f"  Calculated K2 axis: {k2_axis_num}")
        except (ValueError, TypeError) as e:
            print(f"  ❌ Error calculating perpendicular: {e}")
    else:
        print("  ❌ Fix condition not met")

if __name__ == "__main__":
    debug_fix_trigger()
