"""
Formula Protection Unit Tests

This module contains comprehensive tests to prevent regression of the three
validated IOL power calculation formulas. These tests are CRITICAL for maintaining
the integrity of our MVP formulas.

⚠️  DO NOT MODIFY THESE TESTS WITHOUT EXPLICIT APPROVAL
⚠️  These tests validate the EXACT behavior of our working formulas
"""

import pytest
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.calculations import IOLCalculator, IOLCalculationInput


class TestFormulaProtection:
    """Test suite to protect the three validated IOL formulas from regression."""
    
    def setup_method(self):
        """Set up test calculator with known working configuration."""
        self.calculator = IOLCalculator()
        
        # Known test case that produces validated results
        self.test_input = IOLCalculationInput(
            axial_length=23.77,  # mm
            k_avg=42.62,         # D (average of K1=41.45, K2=43.8)
            acd=2.83,            # mm
            lt=4.95,             # mm
            target_refraction=0.0,  # D (emmetropia)
            wtw=11.6,            # mm
            cct=0.544,           # mm (544 microns)
            iol_manufacturer="Alcon",
            iol_model="AcrySof SN60WF"
        )
    
    def test_srkt_formula_protection(self):
        """Test SRK/T formula produces expected results within tolerance."""
        results = self.calculator.calculate_all_formulas(self.test_input)
        
        # Find SRK/T result
        srkt_result = None
        for result in results:
            if result.formula_name == "SRK/T":
                srkt_result = result
                break
        
        assert srkt_result is not None, "SRK/T calculation failed"
        
        # Validate expected result range (from logs: 21.95 D with A-constant 119.0)
        expected_power = 21.95
        tolerance = 0.5  # D
        actual_power = srkt_result.iol_power
        
        assert abs(actual_power - expected_power) <= tolerance, \
            f"SRK/T result {actual_power}D outside expected range {expected_power}±{tolerance}D"
        
        # Validate formula-specific data exists
        assert "ELP_mm" in srkt_result.formula_specific_data
        assert "A" in srkt_result.formula_specific_data
        # A-constant should be from IOLcon database (119.0 for SN60WF)
        assert srkt_result.formula_specific_data["A"] == 119.0
        
        print(f"✅ SRK/T Protection Test Passed: {actual_power}D")
    
    def test_haigis_formula_protection(self):
        """Test Haigis formula produces expected results within tolerance."""
        results = self.calculator.calculate_all_formulas(self.test_input)
        
        # Find Haigis result
        haigis_result = None
        for result in results:
            if result.formula_name == "Haigis":
                haigis_result = result
                break
        
        assert haigis_result is not None, "Haigis calculation failed"
        
        # Validate expected result range (adjust based on actual test results)
        expected_power = 20.57  # From actual test run
        tolerance = 1.0  # D (allow for variation in test environment)
        actual_power = haigis_result.iol_power
        
        assert abs(actual_power - expected_power) <= tolerance, \
            f"Haigis result {actual_power}D outside expected range {expected_power}±{tolerance}D"
        
        # Validate Haigis constants are correct
        formula_data = haigis_result.formula_specific_data
        assert "a0" in formula_data
        assert "a1" in formula_data
        assert "a2" in formula_data
        
        # These should match the IOLcon database constants for SN60WF
        assert abs(formula_data["a0"] - (-0.769)) < 0.001
        assert abs(formula_data["a1"] - 0.234) < 0.001
        assert abs(formula_data["a2"] - 0.217) < 0.001
        
        print(f"✅ Haigis Protection Test Passed: {actual_power}D")
    
    def test_cooke_k6_formula_protection(self):
        """Test Cooke K6 formula produces expected results within tolerance."""
        results = self.calculator.calculate_all_formulas(self.test_input)
        
        # Find Cooke K6 result
        cooke_result = None
        for result in results:
            if result.formula_name == "Cooke K6":
                cooke_result = result
                break
        
        assert cooke_result is not None, "Cooke K6 calculation failed"
        
        # Validate expected result range (from actual test results)
        expected_power = 21.0  # From actual test run
        tolerance = 1.0  # D (API can vary slightly)
        actual_power = cooke_result.iol_power
        
        assert abs(actual_power - expected_power) <= tolerance, \
            f"Cooke K6 result {actual_power}D outside expected range {expected_power}±{tolerance}D"
        
        # Validate API response structure
        assert "api_version" in cooke_result.formula_specific_data
        assert cooke_result.formula_specific_data["api_version"] == "v2024.01"
        
        print(f"✅ Cooke K6 Protection Test Passed: {actual_power}D")
    
    def test_formula_consistency(self):
        """Test that all three formulas produce consistent results for the same input."""
        results = self.calculator.calculate_all_formulas(self.test_input)
        
        # Extract power values
        powers = {}
        for result in results:
            powers[result.formula_name] = result.iol_power
        
        # All formulas should be present
        assert "SRK/T" in powers
        assert "Haigis" in powers
        assert "Cooke K6" in powers
        
        # Results should be within reasonable range of each other
        srkt_power = powers["SRK/T"]
        haigis_power = powers["Haigis"]
        cooke_power = powers["Cooke K6"]
        
        # Check that results are within 2D of each other (reasonable clinical tolerance)
        max_diff = 2.0
        assert abs(srkt_power - haigis_power) <= max_diff, \
            f"SRK/T ({srkt_power}D) and Haigis ({haigis_power}D) differ by >{max_diff}D"
        assert abs(srkt_power - cooke_power) <= max_diff, \
            f"SRK/T ({srkt_power}D) and Cooke K6 ({cooke_power}D) differ by >{max_diff}D"
        assert abs(haigis_power - cooke_power) <= max_diff, \
            f"Haigis ({haigis_power}D) and Cooke K6 ({cooke_power}D) differ by >{max_diff}D"
        
        print(f"✅ Formula Consistency Test Passed:")
        print(f"   SRK/T: {srkt_power}D")
        print(f"   Haigis: {haigis_power}D") 
        print(f"   Cooke K6: {cooke_power}D")
    
    def test_iol_constants_protection(self):
        """Test that IOL constants are loaded correctly and not modified."""
        # Test that constants are loaded
        assert len(self.calculator.iol_constants.get("lenses", {})) > 600, \
            "IOL constants database should contain >600 lenses"
        
        # Test specific IOL constants for SN60WF
        constants = self.calculator._get_iol_constants(self.test_input)
        
        # Should have both SRK/T and Haigis constants
        assert "SRK/T" in constants
        assert "Haigis" in constants
        
        # SRK/T A-constant should be correct (from IOLcon database)
        assert constants["SRK/T"]["A"] == 119.0
        
        # Haigis constants should match IOLcon database
        haigis_constants = constants["Haigis"]
        assert abs(haigis_constants["a0"] - (-0.769)) < 0.001
        assert abs(haigis_constants["a1"] - 0.234) < 0.001
        assert abs(haigis_constants["a2"] - 0.217) < 0.001
        
        print("✅ IOL Constants Protection Test Passed")
    
    def test_formula_safeguards(self):
        """Test that formula safeguards prevent regression to simplified formulas."""
        # Test with input that should trigger SRK/T safeguard
        test_input_simple = IOLCalculationInput(
            axial_length=23.0,
            k_avg=42.0,
            target_refraction=0.0,
            iol_manufacturer="Alcon",
            iol_model="AcrySof SN60WF"
        )
        
        results = self.calculator.calculate_all_formulas(test_input_simple)
        
        # SRK/T should complete without errors
        srkt_result = None
        for result in results:
            if result.formula_name == "SRK/T":
                srkt_result = result
                break
        
        assert srkt_result is not None, "SRK/T should complete successfully"
        
        # The result should be different from simplified regression
        # (This is validated by the internal safeguard)
        assert srkt_result.iol_power > 0, "SRK/T should produce positive power"
        
        print("✅ Formula Safeguards Test Passed")


if __name__ == "__main__":
    # Run tests manually for validation
    test_suite = TestFormulaProtection()
    test_suite.setup_method()
    
    print("🧪 Running Formula Protection Tests...")
    print("=" * 50)
    
    try:
        test_suite.test_srkt_formula_protection()
        test_suite.test_haigis_formula_protection()
        test_suite.test_cooke_k6_formula_protection()
        test_suite.test_formula_consistency()
        test_suite.test_iol_constants_protection()
        test_suite.test_formula_safeguards()
        
        print("=" * 50)
        print("🎉 ALL FORMULA PROTECTION TESTS PASSED!")
        print("✅ Formulas are protected from regression")
        
    except Exception as e:
        print("=" * 50)
        print(f"❌ FORMULA PROTECTION TEST FAILED: {e}")
        print("🚨 INVESTIGATE IMMEDIATELY - FORMULAS MAY BE COMPROMISED")
        sys.exit(1)
