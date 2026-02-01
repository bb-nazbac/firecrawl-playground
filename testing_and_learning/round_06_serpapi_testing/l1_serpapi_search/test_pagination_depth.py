#!/usr/bin/env python3
"""
Test Serper.dev pagination depth
Check how many pages we can actually fetch
"""

import os
import time
import requests
from dotenv import load_dotenv

load_dotenv('../../../.env')
SERPER_API_KEY = os.getenv('SERP_API_KEY')

url = "https://google.serper.dev/search"

headers = {
    "X-API-KEY": SERPER_API_KEY,
    "Content-Type": "application/json"
}

print("Testing pagination depth...")
print("Query: Neurology clinics in Los Angeles")
print()

# Test pages 1-25
test_pages = [1, 2, 3, 4, 5, 10, 15, 20, 25]

for page in test_pages:
    payload = {
        "q": "Neurology clinics in Los Angeles",
        "gl": "us",
        "hl": "en",
        "location": "Los Angeles, California, United States",
        "num": 10,
        "page": page
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=20)
        data = response.json()

        organic = data.get('organic', [])
        credits = data.get('credits', 'N/A')

        print(f"Page {page:2d}: {len(organic):2d} results, {credits} credit(s)")

        if not organic:
            print(f"⚠️  No results after page {page-1}")
            break

        time.sleep(0.3)  # Rate limiting

    except Exception as e:
        print(f"❌ Error on page {page}: {e}")
        break

print()
print("✅ Pagination depth test complete")
