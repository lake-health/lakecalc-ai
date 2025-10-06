#!/usr/bin/env python3
"""
Test script to verify the fix logic works correctly.
"""

def test_fix_logic():
    """Test the fix logic in isolation."""
    print("=== TESTING FIX LOGIC ===")
    
    # Simulate the condition that should trigger the fix
    out = {
        "k1": "40,95",
        "k2": "43,74", 
        "k1_axis": "100",
        "k2_axis": "100"
    }
    
    print(f"Before fix: {out}")
    
    # Apply the fix logic
    if (out.get("k1_axis") == out.get("k2_axis") and 
        out.get("k1_axis") and out.get("k2_axis") and
        "k1" in out and "k2" in out):
        try:
            # Calculate perpendicular axis for K2 (K1 and K2 are typically 90 degrees apart)
            k1_axis_num = int(out["k1_axis"])
            k2_axis_num = (k1_axis_num + 90) % 180
            out["k2_axis"] = str(k2_axis_num)
            print(f"✅ Fix applied: K2 axis changed to {k2_axis_num}")
        except (ValueError, TypeError) as e:
            print(f"❌ Error applying fix: {e}")
    else:
        print("❌ Fix condition not met")
    
    print(f"After fix: {out}")
    
    # Test with OS data
    print(f"\n=== TESTING WITH OS DATA ===")
    out_os = {
        "k1": "41,45",
        "k2": "43,80",
        "k1_axis": "75", 
        "k2_axis": "75"
    }
    
    print(f"Before fix: {out_os}")
    
    if (out_os.get("k1_axis") == out_os.get("k2_axis") and 
        out_os.get("k1_axis") and out_os.get("k2_axis") and
        "k1" in out_os and "k2" in out_os):
        try:
            k1_axis_num = int(out_os["k1_axis"])
            k2_axis_num = (k1_axis_num + 90) % 180
            out_os["k2_axis"] = str(k2_axis_num)
            print(f"✅ Fix applied: K2 axis changed to {k2_axis_num}")
        except (ValueError, TypeError) as e:
            print(f"❌ Error applying fix: {e}")
    else:
        print("❌ Fix condition not met")
    
    print(f"After fix: {out_os}")

if __name__ == "__main__":
    test_fix_logic()
