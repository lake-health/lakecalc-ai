#!/usr/bin/env python3
"""
Test script using the actual data from the provided images.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.parser import parse_text

# Simulated OCR text based on the actual images provided
# This represents what Google Vision OCR might extract from the images

# Right Eye (OD) - from first image
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

# Left Eye (OS) - from second image  
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

def test_real_data():
    """Test with the actual data from the provided images."""
    print("=== TESTING WITH REAL DATA ===")
    
    # Test OD (Right Eye)
    print("\n--- RIGHT EYE (OD) ---")
    result_od = parse_text("test-od", od_text, llm_func=lambda t, m: {"od": {}, "os": {}})
    print(f"OD K1: {result_od.od.k1}")
    print(f"OD K2: {result_od.od.k2}")
    print(f"OD K1 Axis: {result_od.od.k1_axis}")
    print(f"OD K2 Axis: {result_od.od.k2_axis}")
    print(f"Expected: K1=100°, K2=10°")
    
    # Test OS (Left Eye) - This is where the bug occurs
    print("\n--- LEFT EYE (OS) ---")
    result_os = parse_text("test-os", os_text, llm_func=lambda t, m: {"od": {}, "os": {}})
    print(f"OS K1: {result_os.os.k1}")
    print(f"OS K2: {result_os.os.k2}")
    print(f"OS K1 Axis: {result_os.os.k1_axis}")
    print(f"OS K2 Axis: {result_os.os.k2_axis}")
    print(f"Expected: K1=75°, K2=165°")
    
    # Check if the bug is fixed
    if result_os.os.k1_axis == result_os.os.k2_axis and result_os.os.k1_axis != "":
        print("❌ BUG STILL EXISTS: Both K1 and K2 have the same axis!")
    else:
        print("✅ BUG FIXED: K1 and K2 have different axes")
    
    # Test combined text (both eyes)
    print("\n--- COMBINED TEXT (BOTH EYES) ---")
    combined_text = od_text + "\n\n" + os_text
    result_combined = parse_text("test-combined", combined_text, llm_func=lambda t, m: {"od": {}, "os": {}})
    
    print("OD Results:")
    print(f"  K1: {result_combined.od.k1} @ {result_combined.od.k1_axis}°")
    print(f"  K2: {result_combined.od.k2} @ {result_combined.od.k2_axis}°")
    
    print("OS Results:")
    print(f"  K1: {result_combined.os.k1} @ {result_combined.os.k1_axis}°")
    print(f"  K2: {result_combined.os.k2} @ {result_combined.os.k2_axis}°")
    
    # Final check
    os_axes_correct = (result_combined.os.k1_axis == "75" and result_combined.os.k2_axis == "165")
    od_axes_correct = (result_combined.od.k1_axis == "100" and result_combined.od.k2_axis == "10")
    
    if os_axes_correct and od_axes_correct:
        print("✅ ALL AXES CORRECT!")
    else:
        print("❌ Some axes are still incorrect")

if __name__ == "__main__":
    test_real_data()
