#!/usr/bin/env python3
"""
Round 06: Test Serper.dev API with real queries
- Test 1: Spanish dental clinics (Madrid)
- Test 2: US neurology clinics (Los Angeles)

API: Serper.dev (NOT SerpAPI!)
Endpoint: https://google.serper.dev/search
Cost: $0.001 per search (15x cheaper than SerpAPI!)
Speed: 1-2 seconds (3x faster than SerpAPI!)
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
    print("Please add: SERP_API_KEY=your_key_here")
    exit(1)

print("✅ API key loaded")
print(f"Key preview: {SERPER_API_KEY[:10]}...")
print()


def test_search(query, country, language, location, num_results=10):
    """
    Test Serper.dev search with geo-targeting

    Args:
        query: Search query
        country: 2-letter country code (e.g., "es", "us")
        language: 2-letter language code (e.g., "es", "en")
        location: City/region for geo-targeting
        num_results: Number of results to fetch
    """

    print("=" * 70)
    print(f"TEST: {query}")
    print("=" * 70)
    print(f"Country: {country}")
    print(f"Language: {language}")
    print(f"Location: {location}")
    print(f"Results requested: {num_results}")
    print()

    # Serper.dev API
    url = "https://google.serper.dev/search"

    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json"
    }

    payload = {
        "q": query,
        "gl": country,           # Country code
        "hl": language,          # Language code
        "location": location,    # City-level targeting
        "num": num_results,      # Results per page
        "page": 1                # Page number (Serper uses page, not start!)
    }

    try:
        print("🔍 Searching with Serper.dev...")
        start_time = datetime.now()

        response = requests.post(url, json=payload, headers=headers, timeout=30)

        elapsed = (datetime.now() - start_time).total_seconds()

        # Check for errors
        if response.status_code != 200:
            print(f"❌ HTTP {response.status_code}: {response.text}")
            return None

        data = response.json()

        # Check for API errors
        if 'error' in data:
            print(f"❌ API Error: {data['error']}")
            return None

        # Extract results (note: 'organic' not 'organic_results')
        organic = data.get('organic', [])
        search_params = data.get('searchParameters', {})

        print(f"✅ Search completed in {elapsed:.2f}s")
        print(f"   Found {len(organic)} results")
        print()

        # Display first 5 results
        print("Top Results:")
        for i, result in enumerate(organic[:5], 1):
            title = result.get('title', 'No title')
            link = result.get('link', 'No link')
            snippet = result.get('snippet', 'No snippet')

            print(f"\n{i}. {title}")
            print(f"   URL: {link}")
            print(f"   Snippet: {snippet[:100]}...")

        print()
        print(f"📊 Speed: {elapsed:.2f}s (Serper.dev is 3x faster than SerpAPI!)")
        print(f"💰 Cost: $0.001 per search (15x cheaper than SerpAPI!)")

        # Prepare output
        output = {
            'metadata': {
                'api': 'serper.dev',
                'query': query,
                'country': country,
                'language': language,
                'location': location,
                'num_requested': num_results,
                'num_returned': len(organic),
                'timestamp': datetime.now().isoformat(),
                'search_time_seconds': elapsed,
                'cost_usd': 0.001  # Serper.dev pricing
            },
            'results': organic,
            'search_parameters': search_params
        }

        return output

    except requests.exceptions.Timeout:
        print(f"❌ Request timeout (>30s)")
        return None
    except Exception as e:
        print(f"❌ Exception: {e}")
        import traceback
        traceback.print_exc()
        return None


def save_results(output, filename, client='fuse'):
    """
    Save results to JSON file in client folder

    Args:
        output: Results dictionary
        filename: Output filename
        client: Client name (default: 'fuse')
    """

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
    print("ROUND 06: Serper.dev Testing")
    print("Client: Fuse")
    print("API: Serper.dev (https://google.serper.dev)")
    print("Cost: $0.001 per search (15x cheaper than SerpAPI!)")
    print("=" * 70)
    print()

    # Test 1: Spanish dental clinics (Madrid)
    result1 = test_search(
        query="clínica dental Madrid",
        country="es",
        language="es",
        location="Madrid, Spain",
        num_results=10
    )

    if result1:
        save_results(result1, 'test1_dental_madrid.json', client='fuse')

    print()

    # Test 2: US neurology clinics (Los Angeles)
    result2 = test_search(
        query="Neurology clinic in Los Angeles",
        country="us",
        language="en",
        location="Los Angeles, California, United States",
        num_results=10
    )

    if result2:
        save_results(result2, 'test2_neurology_la.json', client='fuse')

    print("=" * 70)
    print("✅ TESTS COMPLETE")
    print("=" * 70)
    print()
    print("Results saved to:")
    print("  1. Round outputs: testing_and_learning/round_06_serpapi_testing/outputs/")
    print("  2. Client folder: search_system/client_outputs/fuse/outputs/l1_search/")
    print()
    print("Next steps:")
    print("1. Review outputs")
    print("2. Check result quality")
    print("3. Test pagination (250 results) if tests pass")
    print()
    print("💰 Cost Analysis:")
    print("  - This test: 2 searches × $0.001 = $0.002")
    print("  - Full run (250 cities × 3 pages): 750 × $0.001 = $0.75")
    print("  - vs SerpAPI: $11.25 → SAVINGS: $10.50 (93% cheaper!)")
    print()


if __name__ == '__main__':
    main()
