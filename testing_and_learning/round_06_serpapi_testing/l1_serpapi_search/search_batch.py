#!/usr/bin/env python3
"""
Batch L1 Search Script
Run multiple query-city combinations in sequence
"""

import os
import json
import time
from datetime import datetime
import requests
from dotenv import load_dotenv
import sys

load_dotenv('../../../.env')
SERPER_API_KEY = os.getenv('SERP_API_KEY')

if not SERPER_API_KEY:
    print("❌ ERROR: SERP_API_KEY not found in .env")
    sys.exit(1)


def search_with_pagination(query, country, language, location, target_results=250, client='fuse'):
    """Search with pagination to get up to target_results"""

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
    pages_needed = min((target_results + 9) // 10, 25)

    while page <= pages_needed:
        print(f"🔍 Fetching page {page}/{pages_needed}...", end=" ", flush=True)

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
                print("⚠️  No more results")
                break

            for item in organic:
                all_results.append({
                    'position': item.get('position'),
                    'title': item.get('title'),
                    'link': item.get('link'),
                    'snippet': item.get('snippet'),
                    'date': item.get('date')
                })

            total_cost += credits * 0.001
            print(f"✅ {len(organic)} results in {page_elapsed:.2f}s (total: {len(all_results)})")
            page += 1
            time.sleep(0.3)

        except requests.exceptions.Timeout:
            print("⚠️  Timeout. Retrying...")
            time.sleep(2)
            continue
        except Exception as e:
            print(f"❌ Error: {e}")
            break

    total_elapsed = (datetime.now() - start_time).total_seconds()

    print()
    print("=" * 70)
    print("✅ SEARCH COMPLETE")
    print(f"   Results: {len(all_results)}")
    print(f"   Pages: {page - 1}")
    print(f"   Time: {total_elapsed:.2f}s")
    print(f"   Cost: ${total_cost:.3f}")
    print("=" * 70)
    print()

    output = {
        'query': query,
        'location': location,
        'metadata': {
            'query': query,
            'country': country,
            'language': language,
            'location': location,
            'target_results': target_results,
            'num_returned': len(all_results),
            'pages_fetched': page - 1,
            'timestamp': datetime.now().isoformat(),
            'search_time_seconds': total_elapsed,
            'cost_usd': total_cost
        },
        'results': all_results
    }

    return output


def save_results(output, query_slug, city_slug, client='fuse'):
    """Save results to client folder"""

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'l1_search_{query_slug}_{city_slug}_{timestamp}.json'

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

    return filename


def main():
    print("=" * 70)
    print("ROUND 06: BATCH L1 SEARCH")
    print("Client: Fuse")
    print("API: Serper.dev")
    print("=" * 70)
    print()

    # Define queries and cities
    queries = [
        "Neurology clinic"
    ]

    cities = [
        {"name": "Boston", "location": "Boston, Massachusetts, United States", "slug": "boston"},
        {"name": "Washington DC", "location": "Washington, District of Columbia, United States", "slug": "dc"},
        {"name": "Houston", "location": "Houston, Texas, United States", "slug": "houston"},
        {"name": "Miami", "location": "Miami, Florida, United States", "slug": "miami"},
        {"name": "San Diego", "location": "San Diego, California, United States", "slug": "san_diego"},
        {"name": "San Francisco", "location": "San Francisco, California, United States", "slug": "sf"},
        {"name": "Albuquerque", "location": "Albuquerque, New Mexico, United States", "slug": "albuquerque"},
        {"name": "Philadelphia", "location": "Philadelphia, Pennsylvania, United States", "slug": "philadelphia"},
        {"name": "Austin", "location": "Austin, Texas, United States", "slug": "austin"},
        {"name": "Phoenix", "location": "Phoenix, Arizona, United States", "slug": "phoenix"},
        {"name": "San Jose", "location": "San Jose, California, United States", "slug": "san_jose"},
        {"name": "Denver", "location": "Denver, Colorado, United States", "slug": "denver"}
    ]

    total_runs = len(queries) * len(cities)
    results_summary = []

    print(f"📊 BATCH CONFIGURATION:")
    print(f"   Queries: {len(queries)}")
    print(f"   Cities: {len(cities)}")
    print(f"   Total runs: {total_runs}")
    print(f"   Target per run: 250 results")
    print()

    run_num = 0
    batch_start = datetime.now()

    for query_base in queries:
        for city in cities:
            run_num += 1
            query = f"{query_base} in {city['name']}"

            print()
            print("═" * 70)
            print(f"RUN {run_num}/{total_runs}: {query}")
            print("═" * 70)
            print()

            result = search_with_pagination(
                query=query,
                country="us",
                language="en",
                location=city['location'],
                target_results=250,
                client='fuse'
            )

            if result:
                query_slug = query_base.replace(" ", "_").lower()
                filename = save_results(result, query_slug, city['slug'], client='fuse')

                results_summary.append({
                    'run': run_num,
                    'query': query,
                    'city': city['name'],
                    'results': result['metadata']['num_returned'],
                    'cost': result['metadata']['cost_usd'],
                    'time': result['metadata']['search_time_seconds'],
                    'filename': filename
                })

    batch_elapsed = (datetime.now() - batch_start).total_seconds()

    # Final Summary
    print()
    print("=" * 70)
    print("🎉 BATCH COMPLETE!")
    print("=" * 70)
    print()

    total_results = sum(r['results'] for r in results_summary)
    total_cost = sum(r['cost'] for r in results_summary)

    print(f"📊 BATCH SUMMARY:")
    print(f"   Total runs: {len(results_summary)}")
    print(f"   Total results: {total_results:,} URLs")
    print(f"   Total time: {batch_elapsed:.1f}s ({batch_elapsed/60:.1f} minutes)")
    print(f"   Total cost: ${total_cost:.3f}")
    print()

    print("Per-City Results:")
    for city in cities:
        city_results = [r for r in results_summary if r['city'] == city['name']]
        city_total = sum(r['results'] for r in city_results)
        print(f"   {city['name']}: {city_total} URLs across {len(city_results)} queries")

    print()
    print("Next Step: Run L2 scraping on all result files")
    print("=" * 70)


if __name__ == '__main__':
    main()
