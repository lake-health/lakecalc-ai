#!/usr/bin/env python3
"""
Debug script for the OD (right eye) axis issue.
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

def debug_od():
    """Debug the OD axis assignment."""
    print("=== DEBUGGING OD (RIGHT EYE) ===")
    
    # Parse the text
    result = parse_text("test-od", od_text, llm_func=lambda t, m: {"od": {}, "os": {}})
    
    print(f"OD K1: {result.od.k1}")
    print(f"OD K2: {result.od.k2}")
    print(f"OD K1 Axis: {result.od.k1_axis}")
    print(f"OD K2 Axis: {result.od.k2_axis}")
    print(f"Expected: K1=100°, K2=10°")
    
    # Let's manually trace through the axis finding
    print("\n=== MANUAL AXIS TRACE ===")
    
    # Find all axis occurrences
    axis_occurrences = []
    for m in re.finditer(r"@\s*(\d{1,3})\s*°", od_text):
        s = m.start()
        # extract the full line containing this axis
        line_start = od_text.rfind('\n', 0, s) + 1
        line_end = od_text.find('\n', s)
        line = od_text[line_start: line_end if line_end != -1 else None]
        
        print(f"Axis occurrence: '{m.group(0)}' at position {s}")
        print(f"  Line: '{line}'")
        
        # skip axes that are part of measurements in mm or explicitly CW-Chord or TSE/TK lines
        should_skip = re.search(r"\bmm\b|CW[- ]?Chord|Chord\b|\bTSE\b|\bSD\b|TK\d*", line, re.I)
        if should_skip:
            print(f"  ❌ Skipping due to: {should_skip.group(0)}")
            continue
        
        # skip numeric-only or very short noisy lines
        if re.fullmatch(r"\s*\d{1,4}\s*", line):
            print(f"  ❌ Skipping due to numeric-only line")
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
            print(f"  ✅ Added: {clean}")
        else:
            print(f"  ❌ Failed sanitization")
    
    print(f"\nValid axis occurrences: {axis_occurrences}")
    
    # Find K1/K2 anchor positions
    anchors = {}
    for klabel in ("K1", "K2"):
        m = re.search(rf"\b{klabel}\b\s*[:\-]?\s*\d{{1,3}}[\.,]\d{{1,3}}\s*D", od_text, re.I)
        if m:
            anchors[klabel.lower()] = m.start()
            print(f"{klabel} anchor at position: {m.start()}")
    
    # For each anchor, choose nearest axis occurrence
    for kkey, apos in anchors.items():
        print(f"\nProcessing {kkey} anchor at position {apos}:")
        best = None
        best_dist = None
        for pos, val in axis_occurrences:
            dist = abs(pos - apos)
            print(f"  Axis {val} at position {pos}: distance = {dist}")
            if best is None or dist < best_dist:
                best = val
                best_dist = dist
        print(f"  Best axis for {kkey}: {best} (distance: {best_dist})")

if __name__ == "__main__":
    debug_od()
