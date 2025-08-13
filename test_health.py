#!/usr/bin/env python3
"""
Simple script to test the health endpoint locally
"""
import requests
import sys

def test_health_endpoint(url="http://localhost:8000"):
    try:
        response = requests.get(f"{url}/health")
        if response.status_code == 200:
            data = response.json()
            print("✅ Health check passed!")
            print(f"Status: {data['status']}")
            print(f"OpenAI configured: {data['openai_configured']}")
            print(f"LLM processor ready: {data['llm_processor_ready']}")
            return True
        else:
            print(f"❌ Health check failed with status {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error connecting to health endpoint: {e}")
        return False

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    success = test_health_endpoint(url)
    sys.exit(0 if success else 1)