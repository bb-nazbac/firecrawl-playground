#!/usr/bin/env python3
"""
L1 Map Layer - Firecrawl /v2/map Integration

Maps a domain to discover all available pages on the site.
This is the first step in the Qualifying Agentic System.

Usage:
    python map_domain.py example.com
    python map_domain.py --input domains.txt
    python map_domain.py --input domains.json
"""

import os
import sys
import json
import re
import time
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional
import requests

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════

SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent
OUTPUT_DIR = ROOT_DIR / "outputs" / "map_results"
LOG_DIR = ROOT_DIR / "logs" / "l1_map"

# Ensure directories exist
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ═══════════════════════════════════════════════════════════════
# ENVIRONMENT
# ═══════════════════════════════════════════════════════════════

def load_env():
    """Load environment variables from .env file"""
    env_path = SCRIPT_DIR.parents[3] / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip())

load_env()

FIRECRAWL_API_KEY = os.environ.get('FIRECRAWL_API_KEY')
if not FIRECRAWL_API_KEY:
    print("❌ FIRECRAWL_API_KEY not found in environment variables")
    sys.exit(1)

# ═══════════════════════════════════════════════════════════════
# LANGUAGE FILTERING
# ═══════════════════════════════════════════════════════════════

NON_ENGLISH_PATTERNS = [
    '/de/', '/de-', '/-de/',  # German
    '/fr/', '/fr-', '/-fr/',  # French
    '/es/', '/es-', '/-es/',  # Spanish
    '/it/', '/it-', '/-it/',  # Italian
    '/ja/', '/jp/', '/ja-jp/',  # Japanese
    '/zh/', '/cn/',  # Chinese
    '/ko/', '/kr/',  # Korean
    '/ru/',  # Russian
    '/pt/', '/br/',  # Portuguese
    '/nl/',  # Dutch
    '/pl/',  # Polish
    '/tr/',  # Turkish
    '/ar/',  # Arabic
    '/hi/',  # Hindi
    '/vi/',  # Vietnamese
    '/th/',  # Thai
    '/id/',  # Indonesian
]

def is_likely_non_english(url: str) -> bool:
    """Check if URL is likely a non-English page"""
    lower_url = url.lower()
    return any(pattern in lower_url for pattern in NON_ENGLISH_PATTERNS)

def filter_english_variants(links: list) -> tuple[list, int]:
    """
    Filter English language variants, preferring en-us over en-gb.
    Drops other variants like en-jp, en-kr, etc.
    """
    en_pattern = re.compile(r'/en-([a-z]{2})(/|$)', re.IGNORECASE)

    # Pass 1: Detect available variants
    has_en_us = False
    has_en_gb = False

    for link in links:
        url = link if isinstance(link, str) else link.get('url', '')
        match = en_pattern.search(url)
        if match:
            variant = match.group(1).lower()
            if variant == 'us':
                has_en_us = True
            elif variant == 'gb':
                has_en_gb = True

    # Decision: Prefer US over GB
    keep_en_us = has_en_us
    keep_en_gb = not has_en_us and has_en_gb

    print(f"   English Variants: US={has_en_us}, GB={has_en_gb}")
    print(f"   Policy: Keep US={keep_en_us}, Keep GB={keep_en_gb}")

    # Pass 2: Filter
    filtered = []
    dropped_count = 0

    for link in links:
        url = link if isinstance(link, str) else link.get('url', '')
        match = en_pattern.search(url)

        if match:
            variant = match.group(1).lower()
            if variant == 'us' and keep_en_us:
                filtered.append(link)
            elif variant == 'gb' and keep_en_gb:
                filtered.append(link)
            else:
                dropped_count += 1
        else:
            # No /en-XX/ pattern - keep it (generic or root)
            filtered.append(link)

    return filtered, dropped_count

# ═══════════════════════════════════════════════════════════════
# MAP FUNCTION
# ═══════════════════════════════════════════════════════════════

def map_domain(domain: str, limit: int = 5000) -> dict:
    """
    Map a domain using Firecrawl /v2/map endpoint.

    Args:
        domain: Domain to map (e.g., 'example.com')
        limit: Maximum number of URLs to return (default 5000)

    Returns:
        dict with mapping results
    """
    print(f"\n🗺️  Mapping {domain}...")
    start_time = time.time()

    # Ensure domain has protocol
    if not domain.startswith('http'):
        url = f"https://{domain}"
    else:
        url = domain
        domain = domain.replace('https://', '').replace('http://', '').split('/')[0]

    try:
        response = requests.post(
            'https://api.firecrawl.dev/v2/map',
            headers={
                'Authorization': f'Bearer {FIRECRAWL_API_KEY}',
                'Content-Type': 'application/json'
            },
            json={
                'url': url,
                'limit': limit
            },
            timeout=60
        )

        data = response.json()
        duration_ms = int((time.time() - start_time) * 1000)

        if data.get('success'):
            # Get links - handle both array of strings and array of objects
            raw_links = data.get('links', [])
            total_links = len(raw_links)

            # Normalize to list of URL strings for filtering
            if raw_links and isinstance(raw_links[0], dict):
                urls = [link.get('url', '') for link in raw_links]
            else:
                urls = raw_links

            # Step 1: Basic non-English filter
            english_urls = [url for url in urls if not is_likely_non_english(url)]
            basic_filtered_count = total_links - len(english_urls)

            # Step 2: English variant filter
            final_urls, variant_dropped_count = filter_english_variants(english_urls)

            print(f"✅ Success ({duration_ms}ms)")
            print(f"   Found {total_links} links")
            print(f"   Filtered {basic_filtered_count} non-English links")
            print(f"   Filtered {variant_dropped_count} unwanted English variants")
            print(f"   Remaining {len(final_urls)} links")

            # Save result
            safe_domain = domain.replace('.', '_').replace('/', '_')
            output_path = OUTPUT_DIR / f"{safe_domain}_map.json"

            result_data = {
                'success': True,
                'domain': domain,
                'url': url,
                'timestamp': datetime.now().isoformat(),
                'duration_ms': duration_ms,
                'stats': {
                    'total_discovered': total_links,
                    'after_language_filter': len(english_urls),
                    'final_count': len(final_urls),
                    'filtered_non_english': basic_filtered_count,
                    'filtered_variants': variant_dropped_count
                },
                'links': final_urls
            }

            with open(output_path, 'w') as f:
                json.dump(result_data, f, indent=2)

            print(f"   Saved to {output_path}")

            return {
                'domain': domain,
                'success': True,
                'links_count': len(final_urls),
                'original_count': total_links,
                'filtered_count': basic_filtered_count + variant_dropped_count,
                'duration_ms': duration_ms,
                'output_path': str(output_path),
                'error': None
            }
        else:
            error_msg = data.get('error', 'Unknown error')
            print(f"❌ Failed ({duration_ms}ms): {error_msg}")
            return {
                'domain': domain,
                'success': False,
                'links_count': 0,
                'duration_ms': duration_ms,
                'error': error_msg
            }

    except requests.exceptions.Timeout:
        duration_ms = int((time.time() - start_time) * 1000)
        print(f"❌ Timeout ({duration_ms}ms)")
        return {
            'domain': domain,
            'success': False,
            'links_count': 0,
            'duration_ms': duration_ms,
            'error': 'Request timeout'
        }

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        print(f"❌ Exception ({duration_ms}ms): {str(e)}")
        return {
            'domain': domain,
            'success': False,
            'links_count': 0,
            'duration_ms': duration_ms,
            'error': str(e)
        }

# ═══════════════════════════════════════════════════════════════
# BATCH PROCESSING
# ═══════════════════════════════════════════════════════════════

def load_domains_from_file(file_path: str) -> list[str]:
    """Load domains from a file (JSON or text)"""
    path = Path(file_path)

    if path.suffix == '.json':
        with open(path) as f:
            data = json.load(f)
        # Handle both list of strings and list of objects
        if isinstance(data, list):
            if data and isinstance(data[0], dict):
                return [item.get('domain', item.get('url', '')) for item in data]
            return data
        return []
    else:
        # Text file - one domain per line
        with open(path) as f:
            return [line.strip() for line in f if line.strip() and not line.startswith('#')]

def map_domains_batch(domains: list[str], delay_ms: int = 1000) -> list[dict]:
    """Map multiple domains with rate limiting"""
    print(f"🚀 Mapping {len(domains)} domains")
    print("=" * 50)

    results = []

    for i, domain in enumerate(domains, 1):
        print(f"\n[{i}/{len(domains)}]")
        result = map_domain(domain)
        results.append(result)

        # Rate limit delay (except for last domain)
        if i < len(domains) and delay_ms > 0:
            time.sleep(delay_ms / 1000)

    # Save summary
    summary_path = OUTPUT_DIR / "batch_summary.json"
    summary = {
        'timestamp': datetime.now().isoformat(),
        'total_domains': len(domains),
        'successful': sum(1 for r in results if r['success']),
        'failed': sum(1 for r in results if not r['success']),
        'total_links': sum(r.get('links_count', 0) for r in results),
        'results': results
    }

    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2)

    print("\n" + "=" * 50)
    print("🏁 Batch Complete")
    print(f"   Successful: {summary['successful']}/{summary['total_domains']}")
    print(f"   Total links: {summary['total_links']}")
    print(f"   Summary saved to {summary_path}")

    return results

# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description='Map domains using Firecrawl /v2/map')
    parser.add_argument('domain', nargs='?', help='Single domain to map')
    parser.add_argument('--input', '-i', help='Input file (JSON or text) with domains')
    parser.add_argument('--limit', type=int, default=5000, help='Max URLs per domain (default 5000)')
    parser.add_argument('--delay', type=int, default=1000, help='Delay between requests in ms (default 1000)')

    args = parser.parse_args()

    if args.input:
        domains = load_domains_from_file(args.input)
        if not domains:
            print("❌ No domains found in input file")
            sys.exit(1)
        map_domains_batch(domains, delay_ms=args.delay)
    elif args.domain:
        map_domain(args.domain, limit=args.limit)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == '__main__':
    main()
