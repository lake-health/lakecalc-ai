#!/usr/bin/env python3
"""
Comprehensive debug script to understand the axis assignment flow.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.parser import parse_text
import re

# Sample text that reproduces the issue - OS eye with only one axis occurrence
sample_text = """OS
esquerda
Valores biométricos
AL: 23,77 mm
ACD: 2,83 mm
LT: 4,95 mm
CCT: 544 μm
WTW: 11,6 mm
K1: 41,45 D
K2: 43,80 D
AK: -2,35 D
@ 75°
Ref: IOLMaster700"""

def debug_comprehensive():
    """Comprehensive debugging of the axis assignment."""
    print("=== COMPREHENSIVE DEBUG ===")
    print(f"Input text:\n{sample_text}\n")
    
    # Parse the text
    result = parse_text("test-file", sample_text, llm_func=lambda t, m: {"od": {}, "os": {}})
    
    print("=== RESULTS ===")
    print(f"OS K1: {result.os.k1}")
    print(f"OS K2: {result.os.k2}")
    print(f"OS K1 Axis: {result.os.k1_axis}")
    print(f"OS K2 Axis: {result.os.k2_axis}")
    
    # Let's manually trace through what should happen
    print("\n=== MANUAL TRACE ===")
    
    # Find K1 and K2 values
    k1_match = re.search(r"K1:\s*(\d{1,3}[\.,]\d{1,3})\s*D", sample_text, re.I)
    k2_match = re.search(r"K2:\s*(\d{1,3}[\.,]\d{1,3})\s*D", sample_text, re.I)
    
    print(f"K1 match: {k1_match.group(1) if k1_match else 'None'}")
    print(f"K2 match: {k2_match.group(1) if k2_match else 'None'}")
    
    # Find axis occurrences
    axis_matches = list(re.finditer(r"@\s*(\d{1,3})\s*°", sample_text))
    print(f"Axis matches: {[m.group(1) for m in axis_matches]}")
    
    # Expected behavior: K1 should get 75, K2 should get 165 (75 + 90)
    print(f"Expected: K1=75, K2=165")
    print(f"Actual: K1={result.os.k1_axis}, K2={result.os.k2_axis}")
    
    # Check if the issue is in the final proximity assignment
    print(f"\n=== FINAL PROXIMITY CHECK ===")
    print("The final proximity assignment might be overriding our fix...")
    
    # Let's check what happens if we disable the final proximity assignment
    # by modifying the text slightly to see if that's where the issue is
    print("\n=== TESTING WITH MODIFIED TEXT ===")
    
    # Add a second axis to see if that changes behavior
    modified_text = sample_text.replace("@ 75°", "@ 75°\n@ 165°")
    result2 = parse_text("test-file-2", modified_text, llm_func=lambda t, m: {"od": {}, "os": {}})
    
    print(f"With two axes - K1: {result2.os.k1_axis}, K2: {result2.os.k2_axis}")

if __name__ == "__main__":
    debug_comprehensive()
