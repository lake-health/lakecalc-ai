#!/usr/bin/env python3
"""
Debug script to understand why the axis duplication fix isn't working.
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

def debug_axis_assignment():
    """Debug the axis assignment process."""
    print("Debugging axis assignment...")
    
    # Parse the text
    result = parse_text("test-file", sample_text, llm_func=lambda t, m: {"od": {}, "os": {}})
    
    print(f"OS K1: {result.os.k1}")
    print(f"OS K2: {result.os.k2}")
    print(f"OS K1 Axis: {result.os.k1_axis}")
    print(f"OS K2 Axis: {result.os.k2_axis}")
    
    # Let's also check the confidence values
    print(f"Confidence os.k1_axis: {result.confidence.get('os.k1_axis', 'N/A')}")
    print(f"Confidence os.k2_axis: {result.confidence.get('os.k2_axis', 'N/A')}")
    
    # Check if the issue is in the pair_k_values function or elsewhere
    print("\nLet's trace through the parsing manually...")
    
    # Import the parser functions directly
    from app.parser import detect_device, PATTERNS, _grab, pair_k_values
    
    dev = detect_device(sample_text)
    print(f"Detected device: {dev}")
    
    patterns = PATTERNS.get(dev, PATTERNS["Generic"])
    
    # Extract scalars manually
    scalars = {}
    for key, rx in patterns.items():
        raw, val = _grab(rx, sample_text)
        if raw:
            scalars[key] = (raw, val)
            print(f"Found {key}: {raw} (value: {val})")
    
    # Test the pair_k_values function
    pairs = pair_k_values(scalars, sample_text)
    print(f"Paired results: {pairs}")

if __name__ == "__main__":
    debug_axis_assignment()
