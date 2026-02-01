#!/usr/bin/env python3
"""
Production script: Get 250 results per city using Serper.dev

Reality:
- 10 results per page (confirmed)
- Max ~24 pages = ~240 results (Google limit)
- Cost: ~$0.024 per city
"""

import os
import json
import time
from datetime import datetime
import requests
from dotenv import load_dotenv

load_dotenv('../../../.env')
SERPER_API_KEY = os.getenv('SERP_API_KEY')

if not SERPER_API_KEY:
    print("❌ ERROR: SERP_API_KEY not found in .env")
    exit(1)


def search_with_pagination(query, country, language, location, target_results=250, client='fuse'):
    """
    Search with pagination to get up to target_results

    Args:
        query: Search query
        country: 2-letter country code
        language: 2-letter language code
        location: City/region for geo-targeting
        target_results: Target number of results (default: 250)
        client: Client name for folder structure

    Returns:
        dict: Complete results with metadata
    """

    print("=" * 70)
    print(f"QUERY: {query}")
    print("=" * 70)
    print(f"Target: {target_results} results")
    print(f"Location: {location}")
    print(f"Country: {country} | Language: {language}")
    print(f"Client: {client}")
    print()

    url = "https://google.serper.dev/search"

    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json"
    }

    all_results = []
    page = 1
    total_cost = 0
    start_time = datetime.now()

    # Calculate pages needed (10 results per page)
    # Max ~24 pages due to Google limits
    pages_needed = min((target_results + 9) // 10, 25)

    while page <= pages_needed:
        print(f"🔍 Fetching page {page}/{pages_needed}...", end=" ")

        payload = {
            "q": query,
            "gl": country,
            "hl": language,
            "location": location,
            "num": 10,
            "page": page
        }

        try:
            page_start = datetime.now()
            response = requests.post(url, json=payload, headers=headers, timeout=20)
            page_elapsed = (datetime.now() - page_start).total_seconds()

            if response.status_code == 429:
                print("⚠️  Rate limited. Waiting...")
                time.sleep(5)
                continue

            if response.status_code != 200:
                print(f"❌ HTTP {response.status_code}")
                break

            data = response.json()

            if 'error' in data:
                print(f"❌ API Error: {data['error']}")
                break

            organic = data.get('organic', [])
            credits = data.get('credits', 1)

            if not organic:
                print(f"⚠️  No more results")
                break

            all_results.extend(organic)
            total_cost += 0.001  # Confirmed: 1 credit per page

            print(f"✅ {len(organic)} results in {page_elapsed:.2f}s (total: {len(all_results)})")

            # Stop if we have enough
            if len(all_results) >= target_results:
                print(f"✅ Reached target: {len(all_results)} results")
                break

            page += 1

            # Rate limiting: ~0.3s between requests
            time.sleep(0.3)

        except Exception as e:
            print(f"❌ Exception: {e}")
            break

    total_elapsed = (datetime.now() - start_time).total_seconds()

    # Trim to exact count
    all_results = all_results[:target_results]

    print()
    print("=" * 70)
    print(f"✅ SEARCH COMPLETE")
    print(f"   Results: {len(all_results)}")
    print(f"   Pages: {page}")
    print(f"   Time: {total_elapsed:.2f}s")
    print(f"   Cost: ${total_cost:.3f}")
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
            'num_requested': target_results,
            'num_returned': len(all_results),
            'pages_fetched': page,
            'timestamp': datetime.now().isoformat(),
            'search_time_seconds': total_elapsed,
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
    print("ROUND 06: Production L1 Search - 250 Results")
    print("Client: Fuse")
    print("API: Serper.dev")
    print("=" * 70)
    print()

    # Test query: Neurology clinics in Los Angeles
    result = search_with_pagination(
        query="Neurology clinics in Los Angeles",
        country="us",
        language="en",
        location="Los Angeles, California, United States",
        target_results=250,
        client='fuse'
    )

    if result:
        # Generate filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'l1_search_neurology_la_250_{timestamp}.json'

        save_results(result, filename, client='fuse')

        # Display sample results
        print("Sample Results:")
        print()
        for i, r in enumerate(result['results'][:5], 1):
            print(f"{i}. {r.get('title', 'No title')}")
            print(f"   {r.get('link', 'No link')}")
            print()

        print(f"... and {len(result['results']) - 5} more results")
        print()

        # Summary
        print("=" * 70)
        print("📊 SUMMARY")
        print("=" * 70)
        print(f"Total results: {result['metadata']['num_returned']}")
        print(f"Total pages: {result['metadata']['pages_fetched']}")
        print(f"Search time: {result['metadata']['search_time_seconds']:.2f}s")
        print(f"Cost: ${result['metadata']['cost_usd']:.3f}")
        print()
        print("Next steps:")
        print("1. Review results quality")
        print("2. Feed URLs to Firecrawl L2 scraper")
        print("3. LLM analysis in L3")
        print("=" * 70)


if __name__ == '__main__':
    main()
