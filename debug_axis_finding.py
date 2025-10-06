#!/usr/bin/env python3
"""
Debug script to understand why the parser isn't finding the second axis.
"""

import re

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

def debug_axis_finding():
    """Debug why the parser isn't finding both axes."""
    print("=== DEBUGGING AXIS FINDING ===")
    print("OS Text:")
    print(os_text)
    print("\n" + "="*50)
    
    # Find all axis occurrences
    axis_matches = list(re.finditer(r"@\s*(\d{1,3})\s*°", os_text))
    print(f"Found {len(axis_matches)} axis occurrences:")
    for i, match in enumerate(axis_matches):
        print(f"  {i+1}: '{match.group(0)}' at position {match.start()}")
    
    # Find K1 and K2 positions
    k1_match = re.search(r"K1:\s*(\d{1,3}[\.,]\d{1,3})\s*D", os_text, re.I)
    k2_match = re.search(r"K2:\s*(\d{1,3}[\.,]\d{1,3})\s*D", os_text, re.I)
    
    print(f"\nK1 position: {k1_match.start() if k1_match else 'Not found'}")
    print(f"K2 position: {k2_match.start() if k2_match else 'Not found'}")
    
    # Check what the parser's axis finding logic would do
    print("\n=== PARSER LOGIC SIMULATION ===")
    
    lines = os_text.splitlines()
    k_results = {"K1": {"val": None, "axis": None}, "K2": {"val": None, "axis": None}}
    
    for i, line in enumerate(lines):
        m = re.search(r"\b(K1|K2)\b\s*[:\-]?\s*(\d{1,3}[\.,]\d{1,3})\s*D", line, re.I)
        if m:
            kname = m.group(1).upper()
            kval = m.group(2)
            print(f"\nFound {kname}: {kval} on line {i}: '{line}'")
            
            # Try to find axis on same line
            axis_m = re.search(r"@\s*(\d{1,3})\s*°", line)
            kaxis = axis_m.group(1) if axis_m else None
            print(f"  Axis on same line: {kaxis}")
            
            # If not found, look at next lines
            if not kaxis:
                window = 6  # IOLMaster700 window
                for j in range(1, window):
                    if i + j < len(lines):
                        next_line = lines[i + j].strip()
                        if not next_line:
                            continue
                        print(f"  Checking line {i+j}: '{next_line}'")
                        
                        # Accept both '@ 100°' and '75°' formats
                        axis_only = re.fullmatch(r"@?\s*(\d{1,3})\s*°", next_line)
                        if axis_only:
                            kaxis = axis_only.group(1)
                            print(f"    Found axis: {kaxis}")
                            break
                        
                        # If next line contains known measurements, break
                        if re.search(r"(CW[- ]?Chord|AL|WTW|CCT|ACD|LT|AK|SE|SD|TK|TSE|ATK|P|Ix|ly|Fixação|Comentário|mm|μm|D|VA|Status de olho|Resultado|Paciente|Médico|Operador|Data|Versão|Página)", next_line, re.I):
                            print(f"    Breaking due to measurement label")
                            break
                        
                        # Skip numeric-only lines
                        if re.fullmatch(r"\s*\d{1,4}\s*", next_line):
                            print(f"    Breaking due to numeric-only line")
                            break
            
            k_results[kname]["val"] = kval
            k_results[kname]["axis"] = kaxis if kaxis else ""
            print(f"  Final result: {kname} = {kval}, axis = {kaxis}")
    
    print(f"\nFinal k_results: {k_results}")
    
    # The issue: both K1 and K2 are finding the same axis (@ 75°)
    # But K2 should find @ 165° which comes after TK1:
    
    print(f"\n=== THE PROBLEM ===")
    print("K1 finds @ 75° (correct)")
    print("K2 should find @ 165° but finds @ 75° instead")
    print("The issue is that @ 165° comes after 'TK1:' which breaks the search")
    print("But @ 75° comes after 'AK:' which doesn't break the search")

if __name__ == "__main__":
    debug_axis_finding()
