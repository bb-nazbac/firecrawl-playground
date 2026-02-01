#!/usr/bin/env python3
"""
Round 06: Test SerpAPI with real queries
- Test 1: Spanish dental clinics (Madrid)
- Test 2: US neurology clinics (Los Angeles)
"""

import os
import json
from datetime import datetime
from serpapi.google_search import GoogleSearch
from dotenv import load_dotenv

# Load API key
load_dotenv('../../../.env')
SERPAPI_API_KEY = os.getenv('SERP_API_KEY') or os.getenv('SERPAPI_API_KEY')

if not SERPAPI_API_KEY:
    print("❌ ERROR: SERP_API_KEY not found in .env")
    print("Please add: SERP_API_KEY=your_key_here")
    exit(1)

print("✅ API key loaded")
print(f"Key preview: {SERPAPI_API_KEY[:10]}...")
print()


def test_search(query, country, language, location, num_results=10):
    """
    Test SerpAPI search with geo-targeting

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

    # SerpAPI search
    search = GoogleSearch({
        "api_key": SERPAPI_API_KEY,
        "q": query,
        "gl": country,           # Country code
        "hl": language,          # Language code
        "location": location,    # City-level targeting
        "num": num_results
    })

    try:
        print("🔍 Searching...")
        response = search.get_dict()

        # Check for errors
        if 'error' in response:
            print(f"❌ API Error: {response['error']}")
            return None

        # Extract results
        organic = response.get('organic_results', [])
        metadata = response.get('search_metadata', {})
        pagination = response.get('serpapi_pagination', {})

        print(f"✅ Search completed in {metadata.get('total_time_taken', 0):.2f}s")
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
        print(f"📊 Pagination available: {'Yes' if pagination.get('next') else 'No'}")
        if pagination.get('next'):
            print(f"   Next page available (for more results)")

        # Prepare output
        output = {
            'metadata': {
                'query': query,
                'country': country,
                'language': language,
                'location': location,
                'num_requested': num_results,
                'num_returned': len(organic),
                'timestamp': datetime.now().isoformat(),
                'search_time': metadata.get('total_time_taken', 0),
                'search_id': metadata.get('id', ''),
                'has_next_page': bool(pagination.get('next'))
            },
            'results': organic,
            'pagination': pagination
        }

        return output

    except Exception as e:
        print(f"❌ Exception: {e}")
        return None


def save_results(output, filename):
    """Save results to JSON file"""
    output_dir = '../outputs'
    os.makedirs(output_dir, exist_ok=True)

    filepath = os.path.join(output_dir, filename)

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"💾 Saved to: {filepath}")
    print()


def main():
    print("=" * 70)
    print("ROUND 06: SerpAPI Testing")
    print("Client: Fuse")
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
        save_results(result1, 'test1_dental_madrid.json')

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
        save_results(result2, 'test2_neurology_la.json')

    print("=" * 70)
    print("✅ TESTS COMPLETE")
    print("=" * 70)
    print()
    print("Next steps:")
    print("1. Review outputs in ../outputs/")
    print("2. Check result quality")
    print("3. Test pagination (250 results) if tests pass")
    print()


if __name__ == '__main__':
    main()
