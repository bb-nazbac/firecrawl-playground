#!/usr/bin/env python3
"""
L1: Fetch All Segments from Firecrawl Crawl Job
"""
import os
import sys
import json
import time
import requests
from pathlib import Path

if len(sys.argv) < 2:
    print("Usage: fetch_segments.py <crawl_id>")
    sys.exit(1)

CRAWL_ID = sys.argv[1]
FIRECRAWL_KEY = os.getenv("FIRECRAWL_API_KEY")
CLIENT = os.getenv("CLIENT", "default")
DOMAIN = os.getenv("DOMAIN", "default")

# Use relative path from script location with client/domain-specific folder
SCRIPT_DIR = Path(__file__).parent.parent.parent  # Go up to queue_system/
SEGMENTS_DIR = SCRIPT_DIR / "outputs" / CLIENT / DOMAIN / "segments"
SEGMENTS_DIR.mkdir(parents=True, exist_ok=True)

print(f"Fetching segments for crawl: {CRAWL_ID}")

# Poll until complete
retries = 0
max_retries = 10
while True:
    try:
        resp = requests.get(
            f"https://api.firecrawl.dev/v2/crawl/{CRAWL_ID}",
            headers={"Authorization": f"Bearer {FIRECRAWL_KEY}"},
            timeout=30
        )

        if resp.status_code != 200:
            print(f"  API Error: HTTP {resp.status_code} - {resp.text[:200]}", flush=True)
            retries += 1
            if retries > max_retries:
                print(f"  ❌ Max retries exceeded, giving up")
                sys.exit(1)
            time.sleep(10 * retries)  # Exponential backoff
            continue

        data = resp.json()
        status = data.get('status')
        completed = data.get('completed', 0)
        total = data.get('total', 0)

        print(f"  Status: {status} - {completed}/{total}", flush=True)
        retries = 0  # Reset on success

        if status == 'completed':
            break

        time.sleep(5)

    except (requests.exceptions.JSONDecodeError, requests.exceptions.RequestException) as e:
        print(f"  Error polling status: {e}", flush=True)
        retries += 1
        if retries > max_retries:
            print(f"  ❌ Max retries exceeded, giving up")
            sys.exit(1)
        time.sleep(10 * retries)  # Exponential backoff

# Fetch all segments
print("Fetching all segments...")
segment_num = 0
skip = 0

while True:
    segment_num += 1
    
    if segment_num == 1:
        url = f"https://api.firecrawl.dev/v2/crawl/{CRAWL_ID}"
    else:
        url = f"https://api.firecrawl.dev/v2/crawl/{CRAWL_ID}?skip={skip}"
    
    resp = requests.get(url, headers={"Authorization": f"Bearer {FIRECRAWL_KEY}"})
    data = resp.json()
    
    # Save segment
    segment_file = SEGMENTS_DIR / f"segment_{segment_num:03d}.json"
    with open(segment_file, 'w') as f:
        json.dump(data, f)
    
    data_count = len(data.get('data', []))
    print(f"  Segment {segment_num}: {data_count} pages")
    
    skip += data_count
    
    if not data.get('next'):
        break

print(f"✅ Fetched {segment_num} segments")
print(f"   Saved to: {SEGMENTS_DIR}")

