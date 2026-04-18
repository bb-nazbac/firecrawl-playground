#!/usr/bin/env python3
"""Scrape sample domains to analyze markdown patterns."""

import os
import json
import requests
from pathlib import Path

# Load API key
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent.parent / '.env')

FIRECRAWL_API_KEY = os.getenv('FIRECRAWL_API_KEY')
OUTPUT_DIR = Path(__file__).parent / 'samples'
OUTPUT_DIR.mkdir(exist_ok=True)

DOMAINS = [
    'heritage-plastics.com',   # Qualified, small (2941 tokens)
    'fukokusc.com',            # Qualified, larger (8477 tokens)
    'trachte.com',             # Disqualified, high tokens (20152)
    'bbpschools.org',          # Filtered early (3023 tokens)
]

def scrape_domain(domain: str) -> dict:
    """Scrape a single domain."""
    url = f"https://{domain}"

    payload = {
        "url": url,
        "formats": ["markdown"],
        "onlyMainContent": False,  # Get EVERYTHING to see what we can strip
        "timeout": 30000,
    }

    headers = {
        "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
        "Content-Type": "application/json"
    }

    print(f"Scraping {domain}...")

    resp = requests.post(
        "https://api.firecrawl.dev/v1/scrape",
        json=payload,
        headers=headers,
        timeout=60
    )
    result = resp.json()

    if result.get('success'):
        markdown = result.get('data', {}).get('markdown', '')

        # Save raw markdown
        output_file = OUTPUT_DIR / f"{domain.replace('.', '_')}_raw.md"
        output_file.write_text(markdown)

        # Save metadata
        meta_file = OUTPUT_DIR / f"{domain.replace('.', '_')}_meta.json"
        meta = {
            'domain': domain,
            'char_count': len(markdown),
            'line_count': len(markdown.split('\n')),
            'word_count': len(markdown.split()),
        }
        meta_file.write_text(json.dumps(meta, indent=2))

        print(f"  ✓ {domain}: {len(markdown):,} chars, {len(markdown.split()):,} words")
        return {'domain': domain, 'success': True, 'chars': len(markdown)}
    else:
        print(f"  ✗ {domain}: {result.get('error', 'Unknown error')}")
        return {'domain': domain, 'success': False, 'error': result.get('error')}

def main():
    results = [scrape_domain(d) for d in DOMAINS]

    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    for r in results:
        if r['success']:
            print(f"  {r['domain']}: {r['chars']:,} chars")
        else:
            print(f"  {r['domain']}: FAILED - {r.get('error')}")

if __name__ == '__main__':
    main()
