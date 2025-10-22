#!/usr/bin/env python3
"""
Update RunPod LLM API with missing /parse endpoint
"""

import requests
import json

# RunPod LLM API URL
API_URL = "https://nko8ymjws3px2s-8001.proxy.runpod.net"

def test_parse_endpoint():
    """Test the /parse endpoint"""
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
    """
    
    payload = {
        "text": test_text,
        "device_type": None,
        "confidence_threshold": 0.8
    }
    
    try:
        response = requests.post(f"{API_URL}/parse", json=payload, timeout=30)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            print("✅ Parse endpoint is working!")
            return True
        else:
            print("❌ Parse endpoint failed")
            return False
            
    except Exception as e:
        print(f"❌ Error testing parse endpoint: {e}")
        return False

def test_health_endpoint():
    """Test the /health endpoint"""
    try:
        response = requests.get(f"{API_URL}/health", timeout=10)
        print(f"Health Status: {response.status_code}")
        print(f"Health Response: {response.text}")
        return response.status_code == 200
    except Exception as e:
        print(f"❌ Error testing health endpoint: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Testing RunPod LLM API Endpoints")
    print("=" * 50)
    
    print("\n1. Testing Health Endpoint...")
    health_ok = test_health_endpoint()
    
    print("\n2. Testing Parse Endpoint...")
    parse_ok = test_parse_endpoint()
    
    print("\n" + "=" * 50)
    if health_ok and parse_ok:
        print("✅ All endpoints working!")
    else:
        print("❌ Some endpoints need fixing")
        if not parse_ok:
            print("   - Parse endpoint needs to be added to RunPod LLM API")


