#!/usr/bin/env python3
"""
Round 06: Test Serper.dev pagination to get 250 results

Query: "Neurology clinics in Los Angeles"
Goal: 250 results (3 pages × ~83 results per page)
Cost: 3 × $0.001 = $0.003
"""

import os
import json
from datetime import datetime
import requests
from dotenv import load_dotenv

# Load API key
load_dotenv('../../../.env')
SERPER_API_KEY = os.getenv('SERP_API_KEY') or os.getenv('SERPER_API_KEY')

if not SERPER_API_KEY:
    print("❌ ERROR: SERP_API_KEY not found in .env")
    exit(1)

print("✅ API key loaded")
print(f"Key preview: {SERPER_API_KEY[:10]}...")
print()


def search_with_pagination(query, country, language, location, total_results=250):
    """
    Search with pagination to get total_results

    Serper.dev returns ~100 results per page max
    For 250 results: need 3 pages
    """

    print("=" * 70)
    print(f"PAGINATION TEST: {query}")
    print("=" * 70)
    print(f"Target results: {total_results}")
    print(f"Country: {country}")
    print(f"Language: {language}")
    print(f"Location: {location}")
    print()

    url = "https://google.serper.dev/search"

    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json"
    }

    all_results = []
    page = 1
    total_cost = 0

    while len(all_results) < total_results:
        print(f"🔍 Fetching page {page}...")

        # Request 100 results per page (Serper max)
        payload = {
            "q": query,
            "gl": country,
            "hl": language,
            "location": location,
            "num": 100,  # Max per page
            "page": page
        }

        try:
            start_time = datetime.now()
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            elapsed = (datetime.now() - start_time).total_seconds()

            if response.status_code != 200:
                print(f"❌ HTTP {response.status_code}: {response.text}")
                break

            data = response.json()

            if 'error' in data:
                print(f"❌ API Error: {data['error']}")
                break

            organic = data.get('organic', [])

            if not organic:
                print(f"⚠️  No more results on page {page}")
                break

            all_results.extend(organic)
            total_cost += 0.001

            print(f"✅ Page {page}: {len(organic)} results in {elapsed:.2f}s")
            print(f"   Total so far: {len(all_results)} results")
            print()

            # Stop if we have enough
            if len(all_results) >= total_results:
                break

            page += 1

        except Exception as e:
            print(f"❌ Exception on page {page}: {e}")
            break

    # Trim to exact count
    all_results = all_results[:total_results]

    print("=" * 70)
    print(f"✅ PAGINATION COMPLETE")
    print(f"   Total results: {len(all_results)}")
    print(f"   Total pages: {page}")
    print(f"   Total cost: ${total_cost:.3f}")
    print("=" * 70)
    print()

    # Prepare output
    output = {
        'metadata': {
            'api': 'serper.dev',
            'query': query,
            'country': country,
            'language': language,
            'location': location,
            'num_requested': total_results,
            'num_returned': len(all_results),
            'pages_fetched': page,
            'timestamp': datetime.now().isoformat(),
            'cost_usd': total_cost
        },
        'results': all_results
    }

    return output


def save_results(output, filename, client='fuse'):
    """Save results to client folder"""

    # Save to round outputs
    output_dir = '../outputs'
    os.makedirs(output_dir, exist_ok=True)
    round_path = os.path.join(output_dir, filename)

    with open(round_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"💾 Saved to: {round_path}")

    # Also save to client folder
    client_dir = f'../../../search_system/client_outputs/{client}/outputs/l1_search'
    os.makedirs(client_dir, exist_ok=True)
    client_path = os.path.join(client_dir, filename)

    with open(client_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"💾 Saved to client folder: {client_path}")
    print()


def main():
    print("=" * 70)
    print("ROUND 06: Pagination Test - 250 Results")
    print("Client: Fuse")
    print("=" * 70)
    print()

    # Test: Neurology clinics in Los Angeles (250 results)
    result = search_with_pagination(
        query="Neurology clinics in Los Angeles",
        country="us",
        language="en",
        location="Los Angeles, California, United States",
        total_results=250
    )

    if result:
        save_results(result, 'test_pagination_250_neurology_la.json', client='fuse')

        # Display sample results
        print("Sample Results:")
        for i, r in enumerate(result['results'][:5], 1):
            print(f"\n{i}. {r.get('title', 'No title')}")
            print(f"   {r.get('link', 'No link')}")

        print(f"\n... and {len(result['results']) - 5} more results")
        print()

    print("=" * 70)
    print("✅ TEST COMPLETE")
    print("=" * 70)
    print()


if __name__ == '__main__':
    main()
