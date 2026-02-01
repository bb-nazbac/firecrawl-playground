#!/usr/bin/env python3
"""
L1: Batch Discovery Script
OPTIMUS PRIME Round 04 - Production Batch Implementation

Purpose:
- Process multiple cities from a list
- Structured file naming: l1_scraped_pages_{NNN}_{city}_{timestamp}.json
- Checkpoint logging after each city
- Cost tracking per city

Usage:
    python3 discover_batch.py cities.json 100

Args:
    cities.json: JSON file with {"cities": [{"id": 1, "name": "Madrid", "slug": "madrid"}, ...]}
    limit: Results per city (max 100)
"""

import json
import os
import sys
import time
from datetime import datetime
from typing import Dict, List
import requests
from dotenv import load_dotenv

# Load environment
load_dotenv(os.path.join(os.path.dirname(__file__), '../../../.env'))
FIRECRAWL_API_KEY = os.getenv('FIRECRAWL_API_KEY')

if not FIRECRAWL_API_KEY:
    print("❌ ERROR: FIRECRAWL_API_KEY not found")
    sys.exit(1)


def retry_api_call(func, max_retries=10, initial_delay=2):
    """Retry with exponential backoff"""
    retries = 0
    delay = initial_delay

    while retries < max_retries:
        try:
            resp = func()

            if resp.status_code == 429:
                print(f"    ⚠️  Rate limit, retrying in {delay}s... ({retries+1}/{max_retries})")
                time.sleep(delay)
                retries += 1
                delay = min(delay * 2, 60)
                continue

            if resp.status_code == 200:
                return (True, resp.json(), None)

            # Other errors
            print(f"    ⚠️  HTTP {resp.status_code}: {resp.text[:200]}")
            if retries < max_retries - 1:
                print(f"    Retrying in {delay}s... ({retries+1}/{max_retries})")
                time.sleep(delay)
                retries += 1
                delay = min(delay * 2, 60)
                continue

            return (False, None, f"HTTP {resp.status_code}")

        except Exception as e:
            print(f"    ⚠️  Error: {e}")
            if retries < max_retries - 1:
                time.sleep(delay)
                retries += 1
                delay = min(delay * 2, 60)
                continue
            return (False, None, str(e))

    return (False, None, "Max retries exceeded")


def search_city(query: str, limit: int, country: str = "ES") -> Dict:
    """Search for dental clinics in one city"""
    api_url = "https://api.firecrawl.dev/v2/search"

    payload = {
        "query": query,
        "limit": limit,
        "country": country,
        "sources": ["web"],
        "scrapeOptions": {
            "formats": ["markdown", "links"],
            "onlyMainContent": True
        }
    }

    headers = {
        "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
        "Content-Type": "application/json"
    }

    def make_request():
        return requests.post(api_url, json=payload, headers=headers, timeout=120)

    success, data, error = retry_api_call(make_request, max_retries=10)

    if not success:
        return {
            "success": False,
            "error": error,
            "pages": [],
            "credits_used": 0
        }

    # Extract results
    pages = []
    if 'data' in data and 'web' in data['data']:
        for result in data['data']['web']:
            pages.append({
                "search_query": query,
                "search_position": result.get('position', 0),
                "url": result.get('url'),
                "title": result.get('title'),
                "description": result.get('description'),
                "markdown": result.get('markdown', ''),
                "links": result.get('links', [])
            })

    return {
        "success": True,
        "pages": pages,
        "credits_used": data.get('creditsUsed', 0)
    }


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 discover_batch.py cities.json <limit>")
        print("\nExample: python3 discover_batch.py cities_10.json 100")
        sys.exit(1)

    cities_file = sys.argv[1]
    limit = int(sys.argv[2])

    if limit > 100:
        print(f"⚠️  WARNING: limit={limit} exceeds API max (100). Setting limit=100")
        limit = 100

    # Load cities
    with open(cities_file, 'r', encoding='utf-8') as f:
        cities_data = json.load(f)

    cities = cities_data.get('cities', [])

    print("═" * 70)
    print("L1: BATCH DISCOVERY")
    print("═" * 70)
    print(f"Cities to process: {len(cities)}")
    print(f"Results per city: {limit}")
    print(f"Est. total pages: {len(cities) * limit}")
    print(f"Est. credits: {len(cities) * (limit * 0.2):.0f} (~${len(cities) * (limit * 0.002):.2f})")
    print("═" * 70)
    print()

    # Setup output directory
    output_dir = os.path.join(os.path.dirname(__file__), '../outputs')
    os.makedirs(output_dir, exist_ok=True)

    # Setup logging
    log_dir = os.path.join(os.path.dirname(__file__), '../logs/l1_batch')
    os.makedirs(log_dir, exist_ok=True)
    timestamp_start = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = os.path.join(log_dir, f'batch_{timestamp_start}.log')

    def log(msg):
        """Log to both console and file"""
        print(msg)
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(msg + '\n')

    log(f"[{datetime.now().isoformat()}] Batch started")
    log(f"Cities: {len(cities)}, Limit: {limit}")
    log("")

    # Process each city
    start_time = time.time()
    total_credits = 0
    total_pages = 0

    for city in cities:
        city_id = city['id']
        city_name = city['name']
        city_slug = city['slug']

        log(f"\n[{city_id}/{len(cities)}] Processing: {city_name}")

        # Search
        query = f"clínica dental {city_name}"
        result = search_city(query, limit)

        if not result['success']:
            log(f"  ❌ FAILED: {result['error']}")
            log(f"  [CHECKPOINT] City {city_id}/{len(cities)} ({city_name}) FAILED")
            continue

        # Save output with structured naming
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_filename = f"l1_scraped_pages_{city_id:03d}_{city_slug}_{timestamp}.json"
        output_path = os.path.join(output_dir, output_filename)

        output_data = {
            "metadata": {
                "city_id": city_id,
                "city_name": city_name,
                "city_slug": city_slug,
                "query": query,
                "limit": limit,
                "timestamp": datetime.now().isoformat(),
                "credits_used": result['credits_used'],
                "pages_count": len(result['pages'])
            },
            "pages": result['pages']
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        total_credits += result['credits_used']
        total_pages += len(result['pages'])

        log(f"  ✅ SUCCESS: {len(result['pages'])} pages, {result['credits_used']} credits")
        log(f"  📄 Saved: {output_filename}")
        log(f"  [CHECKPOINT] City {city_id}/{len(cities)} ({city_name}) completed")
        log(f"  [COST] City {city_id}: {result['credits_used']} credits")
        log(f"  [COST] Running total: {total_credits} credits (~${total_credits * 0.001:.2f})")

    # Summary
    duration = time.time() - start_time
    log("")
    log("═" * 70)
    log("✅ BATCH COMPLETE")
    log("═" * 70)
    log(f"Cities processed: {len(cities)}")
    log(f"Total pages: {total_pages}")
    log(f"Total credits: {total_credits} (~${total_credits * 0.001:.2f})")
    log(f"Duration: {duration:.1f}s ({duration/60:.1f} minutes)")
    log(f"Output directory: {output_dir}")
    log(f"Log file: {log_file}")
    log("═" * 70)


if __name__ == '__main__':
    main()
