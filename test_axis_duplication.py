#!/usr/bin/env python3
"""
Test script to reproduce and fix the K1/K2 axis duplication issue.
This script demonstrates the problem where both K1 and K2 get the same axis value.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.parser import parse_text

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

def test_axis_duplication():
    """Test that reproduces the K1/K2 axis duplication issue."""
    print("Testing axis duplication issue...")
    
    # Parse the text
    result = parse_text("test-file", sample_text, llm_func=lambda t, m: {"od": {}, "os": {}})
    
    print(f"OS K1: {result.os.k1}")
    print(f"OS K2: {result.os.k2}")
    print(f"OS K1 Axis: {result.os.k1_axis}")
    print(f"OS K2 Axis: {result.os.k2_axis}")
    
    # Check if both axes are the same (the bug)
    if result.os.k1_axis == result.os.k2_axis and result.os.k1_axis != "":
        print("❌ BUG CONFIRMED: Both K1 and K2 have the same axis value!")
        return True
    else:
        print("✅ No axis duplication detected")
        return False

if __name__ == "__main__":
    test_axis_duplication()
