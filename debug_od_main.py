#!/usr/bin/env python3
"""
Debug script to check if OD axes are being assigned in the main parsing logic.
"""

import re

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

def debug_od_main():
    """Debug the main parsing logic for OD."""
    print("=== DEBUGGING OD MAIN PARSING LOGIC ===")
    
    lines = od_text.splitlines()
    k_results = {"K1": {"val": None, "axis": None}, "K2": {"val": None, "axis": None}}
    
    for i, line in enumerate(lines):
        m = re.search(r"\b(K1|K2)\b\s*[:\-]?\s*(\d{1,3}[\.,]\d{1,3})\s*D", line, re.I)
        if m:
            kname = m.group(1).upper()
            kval = m.group(2)
            print(f"\n=== PROCESSING {kname} ===")
            print(f"Line {i}: '{line}'")
            print(f"Value: {kval}")
            
            # Try to find axis on same line
            axis_m = re.search(r"@\s*(\d{1,3})\s*°", line)
            kaxis = axis_m.group(1) if axis_m else None
            print(f"Axis on same line: {kaxis}")
            
            # If not found, look at next lines
            if not kaxis:
                window = 6  # IOLMaster700 window
                print(f"Looking forward {window} lines...")
                for j in range(1, window):
                    if i + j < len(lines):
                        next_line = lines[i + j].strip()
                        if not next_line:
                            print(f"  Line {i+j}: (empty)")
                            continue
                        print(f"  Line {i+j}: '{next_line}'")
                        
                        # Accept both '@ 100°' and '75°' formats
                        axis_only = re.fullmatch(r"@?\s*(\d{1,3})\s*°", next_line)
                        if axis_only:
                            kaxis = axis_only.group(1)
                            print(f"    ✅ Found axis: {kaxis}")
                            break
                        
                        # Check if this line should break the search
                        should_break = re.search(r"(CW[- ]?Chord|AL|WTW|CCT|ACD|LT|SE|SD|TK|TSE|ATK|P|Ix|ly|Fixação|Comentário|mm|μm|D|VA|Status de olho|Resultado|Paciente|Médico|Operador|Data|Versão|Página)", next_line, re.I)
                        if should_break:
                            print(f"    ❌ Breaking due to measurement label: {should_break.group(0)}")
                            break
                        
                        # Skip numeric-only lines
                        if re.fullmatch(r"\s*\d{1,4}\s*", next_line):
                            print(f"    ❌ Breaking due to numeric-only line")
                            break
                        
                        print(f"    ➡️  Continuing search...")
            
            k_results[kname]["val"] = kval
            k_results[kname]["axis"] = kaxis if kaxis else ""
            print(f"Final result: {kname} = {kval}, axis = {kaxis}")
    
    print(f"\n=== FINAL RESULTS ===")
    print(f"K1: {k_results['K1']['val']} @ {k_results['K1']['axis']}°")
    print(f"K2: {k_results['K2']['val']} @ {k_results['K2']['axis']}°")
    
    # Check if the issue is that both are finding the same axis
    if k_results['K1']['axis'] == k_results['K2']['axis'] and k_results['K1']['axis']:
        print("❌ BUG: Both K1 and K2 have the same axis!")
        print("The issue is that the main parsing logic is finding the same axis for both K values.")
    else:
        print("✅ SUCCESS: K1 and K2 have different axes!")

if __name__ == "__main__":
    debug_od_main()
