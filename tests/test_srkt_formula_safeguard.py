"""
Unit test to ensure SRK/T formula is never reverted to simplified SRK regression formula.

This test will FAIL if someone accidentally replaces the full theoretical SRK/T 
with the simplified regression formula P = A - 2.5*AL - 0.9*K.
"""

import pytest
import sys
import os

# Add the app directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.calculations import IOLCalculator, IOLCalculationInput


def test_srkt_uses_full_theoretical_formula():
    """
    Test that SRK/T uses the full theoretical formula, not the simplified regression.
    
    Expected behavior:
    - Full SRK/T formula should give significantly different results than simplified SRK regression
    - The difference should be substantial (>0.5 D) to ensure we're using the correct formula
    """
    calculator = IOLCalculator()
    
    # Test data with known values
    input_data = IOLCalculationInput(
        axial_length=23.73,
        k_avg=42.34,
        acd=2.89,
        lt=4.9,
        target_refraction=0.0,  # emmetropia
        iol_manufacturer='Alcon',
        iol_model='SA60WF'
    )
    
    # Calculate using our SRK/T implementation
    results = calculator.calculate_all_formulas(input_data)
    srkt_result = None
    for result in results:
        if result.formula_name == "SRK/T":
            srkt_result = result
            break
    
    assert srkt_result is not None, "SRK/T calculation failed"
    
    # Calculate what the simplified SRK regression would give
    A_constant = 119.0  # Known A-constant for SA60WF
    AL = 23.73
    K = 42.34
    simplified_srk = A_constant - 2.5 * AL - 0.9 * K
    
    # The full SRK/T should differ significantly from simplified SRK regression
    difference = abs(srkt_result.iol_power - simplified_srk)
    
    print(f"\n🔍 SRK/T Formula Safeguard Test:")
    print(f"   Full SRK/T result: {srkt_result.iol_power:.2f} D")
    print(f"   Simplified SRK regression: {simplified_srk:.2f} D")
    print(f"   Difference: {difference:.2f} D")
    
    # Critical assertion: The difference must be substantial
    assert difference > 0.5, f"""
    🚨 CRITICAL ERROR: SRK/T result ({srkt_result.iol_power:.2f}D) is too close to 
    simplified SRK regression ({simplified_srk:.2f}D). Difference: {difference:.2f}D.
    
    This indicates the SRK/T formula has been reverted to the simplified regression formula!
    The full theoretical SRK/T formula must be used, not P = A - 2.5*AL - 0.9*K.
    """
    
    # Additional validation: Check that the result is reasonable for emmetropia
    assert 20.0 <= srkt_result.iol_power <= 23.0, f"""
    SRK/T result ({srkt_result.iol_power:.2f}D) is outside reasonable range for emmetropia.
    Expected range: 20.0-23.0 D for AL=23.73mm, K=42.34D, A=119.
    """
    
    print(f"✅ SRK/T Formula Safeguard Test PASSED")
    print(f"   Full theoretical formula is being used correctly")


if __name__ == "__main__":
    test_srkt_uses_full_theoretical_formula()

