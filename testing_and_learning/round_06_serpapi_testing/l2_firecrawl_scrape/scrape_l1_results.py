#!/usr/bin/env python3
"""
L2: Firecrawl Scraper - Scrape URLs from L1 search results

Input: L1 search results JSON (from Serper.dev)
Output: L2 scraped pages JSON (Firecrawl /v2/scrape)

Process:
1. Read L1 search results
2. Extract all URLs
3. Scrape each URL with Firecrawl /v2/scrape
4. Save scraped pages to client folder
"""

import os
import json
import time
import requests
from datetime import datetime
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

# Load environment
load_dotenv('../../../.env')
FIRECRAWL_API_KEY = os.getenv('FIRECRAWL_API_KEY')

if not FIRECRAWL_API_KEY:
    print("❌ ERROR: FIRECRAWL_API_KEY not found in .env")
    exit(1)


def scrape_url(url, max_retries=5):
    """
    Scrape a single URL using Firecrawl /v2/scrape

    Args:
        url: URL to scrape
        max_retries: Maximum retry attempts

    Returns:
        dict: Scraped page data or error info
    """

    firecrawl_url = "https://api.firecrawl.dev/v2/scrape"

    headers = {
        "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "url": url,
        "formats": ["markdown", "links"],
        "onlyMainContent": True,
        "blockAds": True
    }

    for attempt in range(max_retries):
        try:
            response = requests.post(
                firecrawl_url,
                json=payload,
                headers=headers,
                timeout=30
            )

            if response.status_code == 429:
                wait = (2 ** attempt) + 1
                print(f"    ⚠️  Rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue

            if response.status_code == 200:
                data = response.json()

                # Extract key fields
                return {
                    "url": url,
                    "success": True,
                    "markdown": data.get('data', {}).get('markdown', ''),
                    "links": data.get('data', {}).get('links', []),
                    "metadata": data.get('data', {}).get('metadata', {}),
                    "status_code": 200
                }

            # Other errors
            print(f"    ⚠️  HTTP {response.status_code}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue

            return {
                "url": url,
                "success": False,
                "error": f"HTTP {response.status_code}",
                "status_code": response.status_code
            }

        except requests.exceptions.Timeout:
            print(f"    ⚠️  Timeout on attempt {attempt + 1}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            return {
                "url": url,
                "success": False,
                "error": "Timeout after retries"
            }

        except Exception as e:
            print(f"    ❌ Error: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            return {
                "url": url,
                "success": False,
                "error": str(e)
            }

    return {
        "url": url,
        "success": False,
        "error": "Max retries exceeded"
    }


def scrape_l1_results(l1_file, client='fuse', limit=None):
    """
    Scrape all URLs from L1 search results

    Args:
        l1_file: Path to L1 search results JSON
        client: Client name for folder structure
        limit: Optional limit on number of URLs to scrape (for testing)

    Returns:
        dict: Complete L2 output with metadata and scraped pages
    """

    print("=" * 70)
    print("L2: FIRECRAWL SCRAPER")
    print("=" * 70)
    print(f"Input: {l1_file}")
    print(f"Client: {client}")
    print()

    # Read L1 results
    with open(l1_file, 'r', encoding='utf-8') as f:
        l1_data = json.load(f)

    # Extract URLs
    urls = [r['link'] for r in l1_data['results']]
    total_urls = len(urls)

    if limit:
        urls = urls[:limit]
        print(f"⚠️  Limiting to first {limit} URLs (testing mode)")

    print(f"Total URLs to scrape: {len(urls)}")
    print(f"Concurrency: 50 threads")
    print()

    # Scrape with concurrent requests (50 threads)
    scraped_pages = []
    success_count = 0
    error_count = 0
    completed_count = 0
    start_time = datetime.now()

    # Thread-safe counter
    lock = Lock()

    def scrape_with_index(url_tuple):
        """Scrape URL and return with original index"""
        idx, url = url_tuple
        page_data = scrape_url(url)
        return (idx, page_data)

    print("Starting concurrent scraping...")
    print()

    # Use ThreadPoolExecutor with 50 workers
    with ThreadPoolExecutor(max_workers=50) as executor:
        # Submit all tasks
        future_to_url = {
            executor.submit(scrape_with_index, (i, url)): (i, url)
            for i, url in enumerate(urls)
        }

        # Collect results as they complete
        for future in as_completed(future_to_url):
            idx, url = future_to_url[future]

            try:
                result_idx, page_data = future.result()

                with lock:
                    completed_count += 1

                    if page_data.get('success'):
                        success_count += 1
                        markdown_len = len(page_data.get('markdown', ''))
                        links_count = len(page_data.get('links', []))
                        print(f"[{completed_count}/{len(urls)}] ✅ {url[:50]}... ({markdown_len:,} chars, {links_count} links)")
                    else:
                        error_count += 1
                        print(f"[{completed_count}/{len(urls)}] ❌ {url[:50]}... ({page_data.get('error', 'Unknown error')})")

                    scraped_pages.append((result_idx, page_data))

            except Exception as e:
                with lock:
                    completed_count += 1
                    error_count += 1
                    print(f"[{completed_count}/{len(urls)}] ❌ {url[:50]}... (Exception: {e})")
                    scraped_pages.append((idx, {
                        "url": url,
                        "success": False,
                        "error": str(e)
                    }))

    # Sort by original index to maintain order
    scraped_pages.sort(key=lambda x: x[0])
    scraped_pages = [page for idx, page in scraped_pages]

    total_time = (datetime.now() - start_time).total_seconds()

    print()
    print("=" * 70)
    print("✅ SCRAPING COMPLETE")
    print("=" * 70)
    print(f"Total URLs: {len(urls)}")
    print(f"Successful: {success_count}")
    print(f"Failed: {error_count}")
    print(f"Time: {total_time:.1f}s ({total_time/60:.1f} minutes)")
    print(f"Avg: {total_time/len(urls):.2f}s per page")
    print()

    # Calculate cost estimate
    # Firecrawl /v2/scrape: ~1 credit per request
    cost_estimate = len(urls) * 0.001
    print(f"💰 Estimated cost: ${cost_estimate:.3f}")
    print()

    # Prepare output
    output = {
        'metadata': {
            'layer': 'l2_scrape',
            'source_file': os.path.basename(l1_file),
            'source_query': l1_data['metadata'].get('query', ''),
            'source_location': l1_data['metadata'].get('location', ''),
            'total_urls': len(urls),
            'scraped_success': success_count,
            'scraped_failed': error_count,
            'timestamp': datetime.now().isoformat(),
            'scrape_time_seconds': total_time,
            'cost_estimate_usd': cost_estimate
        },
        'pages': scraped_pages
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
    client_dir = f'../../../search_system/client_outputs/{client}/outputs/l2_scrape'
    os.makedirs(client_dir, exist_ok=True)
    client_path = os.path.join(client_dir, filename)

    with open(client_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"💾 Saved to client folder: {client_path}")
    print()


def main():
    import sys

    if len(sys.argv) < 2:
        print("Usage: python3 scrape_l1_results.py <l1_file> [limit]")
        print()
        print("Examples:")
        print("  python3 scrape_l1_results.py ../outputs/l1_search_neurology_la_250_*.json")
        print("  python3 scrape_l1_results.py ../outputs/l1_search_neurology_la_250_*.json 10")
        exit(1)

    l1_file = sys.argv[1]
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else None

    if not os.path.exists(l1_file):
        print(f"❌ ERROR: File not found: {l1_file}")
        exit(1)

    # Scrape all URLs
    output = scrape_l1_results(l1_file, client='fuse', limit=limit)

    # Generate filename
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # Extract city name from L1 filename
    # l1_search_neurology_la_250_20251105_161120.json -> neurology_la
    l1_basename = os.path.basename(l1_file)
    parts = l1_basename.replace('l1_search_', '').replace('.json', '').split('_')
    # Take everything except last 3 parts (250, date, time)
    city_name = '_'.join(parts[:-3]) if len(parts) > 3 else 'unknown'

    filename = f'l2_scraped_{city_name}_{timestamp}.json'

    save_results(output, filename, client='fuse')

    print("=" * 70)
    print("Next step: Run L3 classification")
    print(f"  python3 ../l3_llm_classify/classify.py {filename}")
    print("=" * 70)


if __name__ == '__main__':
    main()
