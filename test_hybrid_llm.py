#!/usr/bin/env python3
"""
Test script for hybrid LLM integration
Tests local development with RunPod LLM API
"""

import asyncio
import sys
import os
import json
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

async def test_hybrid_llm():
    """Test the hybrid LLM processing"""
    print("🧪 Testing Hybrid LLM Integration")
    print("=" * 50)
    
    try:
        from app.services.parsing.runpod_llm_client import RunPodLLMConfig, RunPodLLMClient
        from app.services.parsing.universal_llm_parser import UniversalLLMParser
        
        # Define test text for all tests
        test_text = """
        Patient: John Doe
        Birth Date: 01/15/1950
        Age: 74
        
        OD (Right Eye):
        Axial Length: 25.25 mm
        K1: 42.60 D
        K2: 43.52 D
        K1 Axis: 14°
        K2 Axis: 104°
        ACD: 3.25 mm
        LT: 4.50 mm
        WTW: 12.25 mm
        CCT: 540 µm
        
        OS (Left Eye):
        Axial Length: 24.85 mm
        K1: 43.10 D
        K2: 44.25 D
        K1 Axis: 165°
        K2 Axis: 75°
        ACD: 3.15 mm
        LT: 4.65 mm
        WTW: 12.30 mm
        CCT: 535 µm
        """
        
        # Test RunPod LLM API client
        print("\n1. Testing RunPod LLM API Client...")
        
        # Configure for local development (RunPod API running on localhost:8001)
        config = RunPodLLMConfig(
            base_url="https://nko8ymjws3px2s-8001.proxy.runpod.net",  # Using actual RunPod URL
            timeout=30,
            confidence_threshold=0.7
        )
        
        client = RunPodLLMClient(config)
        
        # Test health check
        print("   📡 Checking RunPod LLM API health...")
        health = await client.health_check()
        print(f"   Status: {health.get('status', 'unknown')}")
        print(f"   Ollama Available: {health.get('ollama_available', False)}")
        print(f"   Models Loaded: {health.get('models_loaded', [])}")
        
        if health.get("status") == "healthy":
            print("   ✅ RunPod LLM API is healthy!")
            
            # Test biometry parsing
            print("\n2. Testing Biometry Parsing...")
            
        
        print("   📝 Testing with sample biometry text...")
        result = await client.parse_biometry(test_text)
        
        if result["success"]:
            print(f"   ✅ Parsing successful!")
            print(f"   Confidence: {result['confidence']:.2f}")
            print(f"   Processing Time: {result['processing_time']:.2f}s")
            print(f"   Method: {result['method']}")
            
            # Pretty print extracted data
            print("\n   📊 Extracted Data:")
            extracted = result["extracted_data"]
            for key, value in extracted.items():
                if isinstance(value, dict):
                    print(f"   {key}:")
                    for sub_key, sub_value in value.items():
                        print(f"     {sub_key}: {sub_value}")
                else:
                    print(f"   {key}: {value}")
            else:
                print(f"   ❌ Parsing failed: {result.get('error', 'Unknown error')}")
        else:
            print("   ⚠️ RunPod LLM API is not available - will use local fallback")
        
        # Test Universal LLM Parser with hybrid approach
        print("\n3. Testing Universal LLM Parser (Hybrid)...")
        
        # Create a test file
        test_file_path = "test_biometry.txt"
        with open(test_file_path, "w") as f:
            f.write(test_text)
        
        try:
            parser = UniversalLLMParser()
            result = await parser.parse(test_file_path)
            
            if result.success:
                print(f"   ✅ Universal parser succeeded!")
                print(f"   Method: {result.method}")
                print(f"   Confidence: {result.confidence:.2f}")
                print(f"   Processing Time: {result.processing_time:.2f}s")
            else:
                print(f"   ❌ Universal parser failed: {result.error_message}")
                
        except Exception as e:
            print(f"   ❌ Universal parser error: {e}")
        finally:
            # Clean up test file
            if os.path.exists(test_file_path):
                os.remove(test_file_path)
        
        print("\n✅ Hybrid LLM integration test completed!")
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure you're running from the project root directory")
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

async def test_local_fallback():
    """Test local LLM fallback when RunPod is not available"""
    print("\n🔄 Testing Local LLM Fallback")
    print("=" * 50)
    
    try:
        from app.services.parsing.local_llm_processor import LocalLLMProcessor
        
        processor = LocalLLMProcessor()
        
        test_text = """
        Patient: Jane Smith
        Age: 65
        
        OD: AL 24.50, K1 42.00, K2 43.25
        OS: AL 24.75, K1 42.50, K2 43.75
        """
        
        print("📝 Testing local LLM with sample text...")
        result = await processor.parse(document_path="", raw_text=test_text)
        
        if result.get("success"):
            print(f"✅ Local LLM succeeded!")
            print(f"Confidence: {result.get('confidence', 0):.2f}")
            print(f"Processing Time: {result.get('processing_time', 0):.2f}s")
        else:
            print(f"❌ Local LLM failed: {result.get('error', 'Unknown error')}")
            
    except Exception as e:
        print(f"❌ Local fallback test failed: {e}")

if __name__ == "__main__":
    print("🚀 LakeCalc-AI Hybrid LLM Integration Test")
    print("=" * 60)
    
    # Run tests
    asyncio.run(test_hybrid_llm())
    asyncio.run(test_local_fallback())
    
    print("\n🎉 All tests completed!")
    print("\nNext steps:")
    print("1. Set up RunPod LLM API service")
    print("2. Update RunPod URL in the configuration")
    print("3. Test with real biometry files")
