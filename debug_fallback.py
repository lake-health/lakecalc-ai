#!/usr/bin/env python3
"""
Debug script to understand the fallback axis assignment logic.
"""

import sys
import os
import re
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.parser import parse_text

# The actual OS text from the image
os_text = """OS
esquerda
Valores biométricos
AL: 23,77 mm
SD: 16 μm
CCT: 544 μm
SD: 4 μm
WTW: 11,6 mm (!)
P: 2,5 mm
Ix: -0,4 mm
ly: +0,0 mm
CW-Chord: 0,1 mm @ 39°
ACD: 2,83 mm
SD: 11 μm
LT: 4,95 mm
SD: 17 μm
SE: 42,59 D
SD: 0,01 D
TSE:
K1: 41,45 D
K2: 43,80 D
AK: -2,35 D
@ 75°
SD: 0,03 D
TK1:
@ 165°
SD: 0,02 D
TK2:
@
75°
ATK:
Ref: IOLMaster700"""

def debug_fallback():
    """Debug the fallback axis assignment logic."""
    print("=== DEBUGGING FALLBACK LOGIC ===")
    
    # Parse the text
    result = parse_text("test-os", os_text, llm_func=lambda t, m: {"od": {}, "os": {}})
    
    print(f"OS K1: {result.os.k1}")
    print(f"OS K2: {result.os.k2}")
    print(f"OS K1 Axis: {result.os.k1_axis}")
    print(f"OS K2 Axis: {result.os.k2_axis}")
    
    # Let's manually trace through the fallback logic
    print("\n=== MANUAL FALLBACK TRACE ===")
    
    # Find all axis occurrences
    axis_occurrences = []
    for m in re.finditer(r"@\s*(\d{1,3})\s*°", os_text):
        s = m.start()
        # extract the full line containing this axis
        line_start = os_text.rfind('\n', 0, s) + 1
        line_end = os_text.find('\n', s)
        line = os_text[line_start: line_end if line_end != -1 else None]
        
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
        m = re.search(rf"\b{klabel}\b\s*[:\-]?\s*\d{{1,3}}[\.,]\d{{1,3}}\s*D", os_text, re.I)
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
    
    # Check the first/second occurrence fallback
    print(f"\nFirst/second occurrence fallback:")
    if len(axis_occurrences) >= 1:
        print(f"  First occurrence: {axis_occurrences[0][1]}")
    if len(axis_occurrences) >= 2:
        print(f"  Second occurrence: {axis_occurrences[1][1]}")

if __name__ == "__main__":
    debug_fallback()
