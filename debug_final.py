#!/usr/bin/env python3
"""
Debug script to check what's happening in the final assignment.
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

def debug_final():
    """Debug the final assignment."""
    print("=== DEBUGGING FINAL ASSIGNMENT ===")
    
    # Parse the text
    result = parse_text("test-od", od_text, llm_func=lambda t, m: {"od": {}, "os": {}})
    
    print(f"Final result:")
    print(f"  OD K1: {result.od.k1}")
    print(f"  OD K2: {result.od.k2}")
    print(f"  OD K1 Axis: {result.od.k1_axis}")
    print(f"  OD K2 Axis: {result.od.k2_axis}")
    
    # Let's check if the final proximity assignment is being called
    print(f"\nFinal proximity assignment check:")
    print(f"  K1 exists: {bool(result.od.k1)}")
    print(f"  K2 exists: {bool(result.od.k2)}")
    print(f"  K1 axis exists: {bool(result.od.k1_axis)}")
    print(f"  K2 axis exists: {bool(result.od.k2_axis)}")
    
    need_k1 = bool(result.od.k1) and not result.od.k1_axis
    need_k2 = bool(result.od.k2) and not result.od.k2_axis
    
    print(f"  need_k1: {need_k1}")
    print(f"  need_k2: {need_k2}")
    print(f"  final_proximity_assign should run: {need_k1 or need_k2}")
    
    if not (need_k1 or need_k2):
        print("  ✅ Final proximity assignment is NOT running (axes already assigned)")
    else:
        print("  ❌ Final proximity assignment IS running (axes missing)")

if __name__ == "__main__":
    debug_final()
