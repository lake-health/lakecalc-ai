#!/usr/bin/env python3
"""
Test script for the universal parser.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.parsing.universal_parser import UniversalParser
from app.services.parsing.cost_tracker import CostTracker
from app.services.parsing.text_extractor import TextExtractor
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_text_extractor():
    """Test text extraction with sample biometry data."""
    print("🧪 Testing Text Extractor")
    print("=" * 40)
    
    # Create sample text with biometry data
    sample_text = """
    Patient Biometry Report
    
    Axial Length: 23.77 mm
    K1: 42.25 D
    K2: 43.00 D
    K1 Axis: 90°
    K2 Axis: 180°
    ACD: 2.83 mm
    LT: 4.52 mm
    WTW: 11.6 mm
    CCT: 540 μm
    
    Patient Age: 65 years
    Target Refraction: 0.00 D
    
    Eye: OD
    """
    
    # Save to temporary file
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(sample_text)
        temp_file = f.name
    
    try:
        # Test text extractor
        extractor = TextExtractor()
        
        print(f"📄 Testing file: {temp_file}")
        print(f"📝 Sample text length: {len(sample_text)} characters")
        
        result = extractor.parse(temp_file, "test_user")
        
        print(f"✅ Success: {result.success}")
        print(f"🎯 Confidence: {result.confidence:.2f}")
        print(f"⚡ Method: {result.method.value}")
        print(f"💰 Cost: ${result.cost:.2f}")
        print(f"⏱️  Processing time: {result.processing_time:.3f}s")
        
        if result.warnings:
            print(f"⚠️  Warnings: {len(result.warnings)}")
            for warning in result.warnings:
                print(f"   - {warning}")
        
        print("\n📊 Extracted Data:")
        for key, value in result.extracted_data.items():
            print(f"   {key}: {value}")
        
        return result.success and result.confidence > 0.8
        
    finally:
        # Clean up
        os.unlink(temp_file)


def test_cost_tracker():
    """Test cost tracking functionality."""
    print("\n💰 Testing Cost Tracker")
    print("=" * 40)
    
    cost_tracker = CostTracker()
    user_id = "test_user_123"
    
    # Test budget creation
    budget = cost_tracker.get_user_budget(user_id)
    print(f"👤 User: {user_id}")
    print(f"🎫 Tier: {budget.tier}")
    print(f"📊 OCR Limit: {budget.monthly_ocr_limit}")
    print(f"🤖 LLM Limit: {budget.monthly_llm_limit}")
    print(f"💵 Cost Limit: ${budget.monthly_cost_limit}")
    
    # Test service availability
    print(f"\n🔍 Service Availability:")
    services = cost_tracker.get_available_services(user_id)
    for service, info in services.items():
        status = "✅" if info["available"] else "❌"
        cost = info["cost"]
        print(f"   {status} {service}: ${cost:.2f} - {info['reason']}")
    
    # Test usage tracking
    print(f"\n📈 Usage Tracking:")
    can_use, reason = cost_tracker.can_use_service(user_id, "text_extraction")
    print(f"   Text Extraction: {can_use} - {reason}")
    
    can_use, reason = cost_tracker.can_use_service(user_id, "ocr_easyocr")
    print(f"   OCR EasyOCR: {can_use} - {reason}")
    
    # Track some usage
    cost_tracker.track_usage(user_id, "text_extraction", 0.0)
    print(f"   ✅ Tracked text extraction usage")
    
    # Get usage summary
    summary = cost_tracker.get_usage_summary(user_id)
    print(f"\n📊 Usage Summary:")
    print(f"   OCR Used: {summary['current_month']['ocr_used']}/{summary['current_month']['ocr_limit']}")
    print(f"   LLM Used: {summary['current_month']['llm_used']}/{summary['current_month']['llm_limit']}")
    print(f"   Cost Used: ${summary['current_month']['cost_used']:.2f}/${summary['current_month']['cost_limit']:.2f}")
    
    return True


def test_universal_parser():
    """Test the universal parser."""
    print("\n🌍 Testing Universal Parser")
    print("=" * 40)
    
    # Create sample text with biometry data
    sample_text = """
    IOLMaster 700 Biometry Report
    
    Patient: John Doe
    Date: 2024-01-15
    
    OD (Right Eye):
    Axial Length: 23.45 mm
    K1: 42.75 D @ 90°
    K2: 43.50 D @ 180°
    ACD: 2.95 mm
    LT: 4.32 mm
    WTW: 11.8 mm
    
    OS (Left Eye):
    Axial Length: 23.77 mm
    K1: 42.25 D @ 88°
    K2: 43.00 D @ 178°
    ACD: 2.83 mm
    LT: 4.52 mm
    WTW: 11.6 mm
    
    Target: Emmetropia (0.00 D)
    """
    
    # Save to temporary file
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(sample_text)
        temp_file = f.name
    
    try:
        # Test universal parser
        parser = UniversalParser()
        user_id = "test_user_456"
        
        print(f"📄 Testing file: {temp_file}")
        print(f"📝 Sample text length: {len(sample_text)} characters")
        
        result = parser.parse(temp_file, user_id)
        
        print(f"✅ Success: {result.success}")
        print(f"🎯 Confidence: {result.confidence:.2f}")
        print(f"⚡ Method: {result.method.value}")
        print(f"💰 Cost: ${result.cost:.2f}")
        print(f"⏱️  Processing time: {result.processing_time:.3f}s")
        
        if result.warnings:
            print(f"⚠️  Warnings: {len(result.warnings)}")
            for warning in result.warnings:
                print(f"   - {warning}")
        
        print("\n📊 Extracted Data:")
        for key, value in result.extracted_data.items():
            if not key.startswith('_'):
                print(f"   {key}: {value}")
        
        return result.success
        
    finally:
        # Clean up
        os.unlink(temp_file)


def main():
    """Run all tests."""
    print("🚀 Universal Parser Test Suite")
    print("=" * 50)
    
    tests = [
        ("Text Extractor", test_text_extractor),
        ("Cost Tracker", test_cost_tracker),
        ("Universal Parser", test_universal_parser)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
            print(f"\n{'✅ PASSED' if result else '❌ FAILED'}: {test_name}")
        except Exception as e:
            print(f"\n❌ ERROR in {test_name}: {e}")
            results.append((test_name, False))
    
    print("\n" + "=" * 50)
    print("📊 Test Results Summary:")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"   {status}: {test_name}")
    
    print(f"\n🎯 Overall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Parser is ready for integration.")
    else:
        print("⚠️  Some tests failed. Check the output above for details.")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
