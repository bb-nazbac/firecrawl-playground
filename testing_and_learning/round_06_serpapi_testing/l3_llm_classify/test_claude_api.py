#!/usr/bin/env python3
"""
Quick test to verify Claude API connectivity
"""
import os
import json
import requests
from dotenv import load_dotenv

load_dotenv('../../../.env')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')

print(f"API Key loaded: {ANTHROPIC_API_KEY[:20]}..." if ANTHROPIC_API_KEY else "❌ No API key")
print()

url = "https://api.anthropic.com/v1/messages"
headers = {
    "x-api-key": ANTHROPIC_API_KEY,
    "anthropic-version": "2023-06-01",
    "content-type": "application/json"
}

payload = {
    "model": "claude-3-5-sonnet-20241022",
    "max_tokens": 100,
    "temperature": 0,
    "messages": [
        {
            "role": "user",
            "content": "Say hello in JSON format: {\"greeting\": \"...\"}"
        }
    ]
}

print("Testing Claude API...")
print(f"URL: {url}")
print(f"Model: {payload['model']}")
print()

try:
    response = requests.post(url, json=payload, headers=headers, timeout=30)

    print(f"Status Code: {response.status_code}")
    print(f"Response Headers: {dict(response.headers)}")
    print()
    print(f"Response Body:")
    print(response.text)
    print()

    if response.status_code == 200:
        data = response.json()
        print("✅ SUCCESS!")
        print(f"Content: {data.get('content', [{}])[0].get('text', 'N/A')}")
    else:
        print(f"❌ HTTP {response.status_code}")

except Exception as e:
    print(f"❌ Exception: {e}")
