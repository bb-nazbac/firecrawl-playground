# SerpAPI Google Search API - Complete Reference

**For Next Agent**: This document contains everything you need to use SerpAPI for the discovery pipeline.

**Version**: 1.0
**Date**: 2025-11-04
**Agent**: OPTIMUS PRIME OP-2025-1104-SERPAPI-MIGRATION

═══════════════════════════════════════════════════════════════

## Table of Contents

1. [Overview](#overview)
2. [API Endpoint & Authentication](#api-endpoint--authentication)
3. [Request Parameters](#request-parameters)
4. [Response Structure](#response-structure)
5. [Pagination](#pagination)
6. [Cost & Credit System](#cost--credit-system)
7. [Code Examples](#code-examples)
8. [Edge Cases & Caveats](#edge-cases--caveats)

═══════════════════════════════════════════════════════════════

## Overview

**What is SerpAPI?**
- Real-time API to scrape Google (and other engines) search results
- Returns structured JSON data (organic results, ads, knowledge graph, local results)
- Handles proxying, CAPTCHA solving, browser simulation automatically
- Supports pagination via `start` parameter (critical for our use case)

**Why We're Using It**:
- Firecrawl /search has 100-result hard limit with NO pagination
- SerpAPI supports pagination → can get 250+ results per query
- Same cost model (1 credit per search)

**What We Get**:
- `organic_results` array with:
  - `link`: URL to scrape with Firecrawl
  - `title`: Page title
  - `snippet`: Meta description
  - `position`: Result ranking (1-100)

═══════════════════════════════════════════════════════════════

## API Endpoint & Authentication

### Endpoint
```
https://serpapi.com/search.json
```

### Authentication
```python
# Method 1: Query parameter (recommended)
url = "https://serpapi.com/search.json?api_key=YOUR_API_KEY&q=..."

# Method 2: Python client (handles auth automatically)
from serpapi import GoogleSearch

search = GoogleSearch({
    "api_key": "YOUR_API_KEY",
    "q": "your query"
})
```

### Get Your API Key
1. Sign up at https://serpapi.com/
2. Navigate to Dashboard → API Key
3. Store in `.env` file:
   ```bash
   SERPAPI_API_KEY=your_key_here
   ```

═══════════════════════════════════════════════════════════════

## Request Parameters

### Required Parameters

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `q` | string | **Search query** (required) | `"clínica dental Madrid"` |
| `api_key` | string | **Authentication** (required) | Your API key from dashboard |

### Core Parameters (Highly Recommended)

| Parameter | Type | Description | Example | Notes |
|-----------|------|-------------|---------|-------|
| `engine` | string | Search engine to use | `"google"` | Default is `"google"` |
| `gl` | string | Country code (2-letter) | `"es"` | Spain (affects result ranking) |
| `hl` | string | Language code | `"es"` | Spanish UI |
| `num` | integer | Results per page | `100` | Max: 100, Default: 10 |
| `start` | integer | **Pagination offset** | `0`, `100`, `200` | Critical for pagination! |

### Advanced Parameters (Optional)

| Parameter | Type | Description | Example | Use Case |
|-----------|------|-------------|---------|----------|
| `google_domain` | string | Google domain | `"google.es"` | For Spain-specific results |
| `location` | string | Geographic location | `"Madrid, Spain"` | City-level targeting |
| `no_cache` | boolean | Force fresh search | `true` | Bypass cached results |
| `output` | string | Response format | `"json"` | Default: `"json"` |

### Parameter Details

#### 1. `q` - Search Query
```python
# Basic query
q = "clínica dental Madrid"

# Advanced operators (Google syntax)
q = '"Clínica Dental" Madrid site:.es'  # Exact phrase + domain filter
q = 'dentista Madrid -doctoralia'       # Exclude domains
q = 'clínica dental Madrid intitle:contacto'  # In title filter
```

#### 2. `num` - Results Per Page
```python
num = 100  # Recommended: Get max results per call to minimize API calls
num = 50   # Alternative: Faster responses, more granular pagination
num = 10   # Default: Not recommended (too many API calls needed)
```

**Cost Impact**: `num` does NOT affect cost (1 credit regardless of 10 or 100)

#### 3. `start` - Pagination Offset
```python
start = 0    # Page 1: Results 1-100
start = 100  # Page 2: Results 101-200
start = 200  # Page 3: Results 201-300
```

**Critical**: Each `start` value = separate API call = 1 credit

#### 4. `gl` + `hl` - Geographic & Language Targeting
```python
# For Spain (our use case)
gl = "es"  # Country: Spain
hl = "es"  # Language: Spanish

# This affects:
# - Result ranking (Spanish sites prioritized)
# - Ads shown (Spanish advertisers)
# - Knowledge graph (Spanish entities)
```

═══════════════════════════════════════════════════════════════

## Response Structure

### Top-Level Structure
```json
{
  "search_metadata": {
    "id": "67890...",
    "status": "Success",
    "created_at": "2025-11-04 18:10:00 UTC",
    "processed_at": "2025-11-04 18:10:01 UTC",
    "google_url": "https://www.google.com/search?q=...",
    "total_time_taken": 1.23
  },
  "search_parameters": {
    "engine": "google",
    "q": "clínica dental Madrid",
    "gl": "es",
    "hl": "es",
    "num": 100,
    "start": 0
  },
  "organic_results": [
    {
      "position": 1,
      "title": "Clínica Dental en Madrid - Dentistas Orion Dental",
      "link": "https://www.clinicadentalorion.com/",
      "displayed_link": "https://www.clinicadentalorion.com",
      "snippet": "Orión Dental, es una clínica dental en Madrid especializada en implantes dentales y estética dental. Cubrimos todos los servicios odontológicos: ortodoncia, ...",
      "snippet_highlighted_words": ["clínica dental", "Madrid"],
      "sitelinks": {
        "inline": [
          {"title": "Contacto", "link": "https://..."},
          {"title": "Servicios", "link": "https://..."}
        ]
      },
      "rich_snippet": {
        "top": {
          "extensions": ["Rating: 4.8", "200 reviews"]
        }
      }
    },
    ...
  ],
  "serpapi_pagination": {
    "current": 1,
    "next": "https://serpapi.com/search.json?...",
    "next_link": "https://serpapi.com/search.json?...",
    "other_pages": {
      "2": "https://serpapi.com/search.json?...",
      "3": "https://serpapi.com/search.json?...",
      "4": "https://serpapi.com/search.json?..."
    }
  }
}
```

### Key Fields to Extract

#### From `organic_results` Array (Primary Data)
```python
for result in response['organic_results']:
    url = result['link']           # URL to scrape (feed to Firecrawl)
    title = result['title']         # Page title
    snippet = result['snippet']     # Meta description
    position = result['position']   # Ranking (1-100)
```

#### From `serpapi_pagination` (For Pagination Logic)
```python
pagination = response.get('serpapi_pagination', {})
next_url = pagination.get('next')  # URL for next page (if exists)
current_page = pagination.get('current')  # Current page number

if next_url:
    # More results available
    print(f"Page {current_page} complete. Fetching next page...")
else:
    # No more results
    print("Reached end of results")
```

#### From `search_metadata` (For Debugging)
```python
metadata = response['search_metadata']
search_id = metadata['id']          # Unique search ID
status = metadata['status']         # "Success" or error
total_time = metadata['total_time_taken']  # API response time
```

═══════════════════════════════════════════════════════════════

## Pagination

**Critical Feature**: This is why we're using SerpAPI instead of Firecrawl!

### How Pagination Works

1. **First Request** (Page 1):
   ```python
   params = {"q": "clínica dental Madrid", "num": 100, "start": 0}
   ```
   - Returns results 1-100
   - Includes `serpapi_pagination.next` URL

2. **Second Request** (Page 2):
   ```python
   params = {"q": "clínica dental Madrid", "num": 100, "start": 100}
   ```
   - Returns results 101-200
   - Includes `serpapi_pagination.next` URL

3. **Continue** until `serpapi_pagination.next` is absent

### Pagination Loop Pattern

#### Method 1: Using `next` URL (Easiest)
```python
from serpapi import GoogleSearch
import os

api_key = os.getenv('SERPAPI_API_KEY')
all_results = []
start = 0
max_results = 250

while len(all_results) < max_results:
    search = GoogleSearch({
        "api_key": api_key,
        "q": "clínica dental Madrid",
        "gl": "es",
        "hl": "es",
        "num": 100,
        "start": start
    })

    response = search.get_dict()
    organic = response.get('organic_results', [])

    if not organic:
        break  # No more results

    all_results.extend(organic)
    print(f"Fetched {len(organic)} results (total: {len(all_results)})")

    # Check for next page
    pagination = response.get('serpapi_pagination', {})
    if not pagination.get('next'):
        break  # No more pages

    start += 100  # Next page

print(f"Total results: {len(all_results)}")
```

#### Method 2: Manual Increment (More Control)
```python
def search_with_pagination(query, max_results=250, results_per_page=100):
    all_results = []
    page_num = 0

    while len(all_results) < max_results:
        start = page_num * results_per_page

        params = {
            "api_key": api_key,
            "q": query,
            "gl": "es",
            "hl": "es",
            "num": results_per_page,
            "start": start
        }

        response = GoogleSearch(params).get_dict()
        organic = response.get('organic_results', [])

        if not organic:
            print(f"No results on page {page_num + 1}. Stopping.")
            break

        all_results.extend(organic)
        page_num += 1

        print(f"[Page {page_num}] Fetched {len(organic)} results (total: {len(all_results)})")

        # Stop if we got fewer results than requested (last page)
        if len(organic) < results_per_page:
            print("Reached last page of results")
            break

    return all_results[:max_results]  # Trim to max_results
```

### Pagination Best Practices

1. **Use `num=100`**: Minimize API calls (cost-efficient)
2. **Check `organic_results` length**: If < 100, you've hit the last page
3. **Check `serpapi_pagination.next`**: Most reliable indicator
4. **Handle empty results**: Google may return 0 results mid-pagination
5. **Track credits**: Each page = 1 credit

### Pagination Limits

**Google's Hard Limits**:
- Maximum ~1000 results total (varies by query)
- After ~10 pages (1000 results), Google stops returning new results
- Some queries may have fewer results available

**Practical Limits for Our Use Case**:
- Target: 250 results per city → 3 pages (250 = 3×100 - 50)
- Maximum safe: 500 results per city → 5 pages
- Beyond 500: Diminishing returns (duplicates, irrelevant results)

═══════════════════════════════════════════════════════════════

## Cost & Credit System

### Pricing Tiers (as of 2025-11-04)

| Plan | Searches/Month | Price/Month | Cost Per Search |
|------|---------------|-------------|-----------------|
| Free | 100 | $0 | $0 |
| Starter | 5,000 | $75 | $0.015 |
| Developer | 15,000 | $225 | $0.015 |
| Production | 30,000 | $450 | $0.015 |
| Enterprise | Custom | Custom | Negotiable |

**Official Pricing**: https://serpapi.com/pricing

### Cost Calculation Rules

1. **One search = One credit** (regardless of `num` parameter)
   - `num=10` → 1 credit
   - `num=100` → 1 credit (same cost!)
   - **Recommendation**: Always use `num=100`

2. **Each page = One search = One credit**
   - Page 1 (`start=0`) → 1 credit
   - Page 2 (`start=100`) → 1 credit
   - Page 3 (`start=200`) → 1 credit

3. **Cached results** (depends on plan):
   - May not count toward quota
   - Use `no_cache=true` to force fresh search

### Cost Projections for Our Use Case

#### Scenario A: 250 Cities × 100 Results (Conservative)
```
250 cities × 1 page × 1 credit = 250 credits
Cost: 250 × $0.015 = $3.75

Plus Firecrawl scrape:
250 cities × 100 results × 0.2 credits = 5,000 Firecrawl credits = $5.00

Plus Claude classification:
250 cities × 100 results × $0.003 = $75.00

Total: $3.75 + $5.00 + $75.00 = $83.75
```

#### Scenario B: 250 Cities × 250 Results (Target)
```
250 cities × 3 pages × 1 credit = 750 credits
Cost: 750 × $0.015 = $11.25

Plus Firecrawl scrape:
250 cities × 250 results × 0.2 credits = 12,500 Firecrawl credits = $12.50

Plus Claude classification:
250 cities × 250 results × $0.003 = $187.50

Total: $11.25 + $12.50 + $187.50 = $211.25
```

#### Scenario C: 250 Cities × 500 Results (Maximum)
```
250 cities × 5 pages × 1 credit = 1,250 credits
Cost: 1,250 × $0.015 = $18.75

Plus Firecrawl scrape:
250 cities × 500 results × 0.2 credits = 25,000 Firecrawl credits = $25.00

Plus Claude classification:
250 cities × 500 results × $0.003 = $375.00

Total: $18.75 + $25.00 + $375.00 = $418.75
```

### Cost Optimization Strategies

1. **Use `num=100`** (not 10 or 50) → Minimize API calls
2. **Enable caching** (leave `no_cache=false` default) → Rerun queries are cheaper
3. **Filter before scraping** → Only scrape relevant domains (L2 filter)
4. **Deduplicate early** → Don't scrape duplicate domains
5. **Set max_pages limit** → Prevent runaway costs

═══════════════════════════════════════════════════════════════

## Code Examples

### Example 1: Simple Search (Single Query)
```python
#!/usr/bin/env python3
"""Simple SerpAPI search example"""

import os
from serpapi import GoogleSearch
from dotenv import load_dotenv

load_dotenv()

def simple_search(query, num_results=10):
    """Fetch single page of results"""

    search = GoogleSearch({
        "api_key": os.getenv('SERPAPI_API_KEY'),
        "q": query,
        "gl": "es",
        "hl": "es",
        "num": num_results
    })

    results = search.get_dict()

    # Extract URLs
    urls = [result['link'] for result in results.get('organic_results', [])]

    print(f"Query: {query}")
    print(f"Found {len(urls)} results")
    for i, url in enumerate(urls, 1):
        print(f"  {i}. {url}")

    return urls

if __name__ == '__main__':
    simple_search("clínica dental Madrid", num_results=10)
```

### Example 2: Pagination (Multiple Pages)
```python
#!/usr/bin/env python3
"""SerpAPI with pagination example"""

import os
import json
from serpapi import GoogleSearch
from dotenv import load_dotenv

load_dotenv()

def search_with_pagination(query, max_results=250):
    """
    Search with pagination to get multiple pages of results

    Args:
        query: Search query string
        max_results: Maximum total results to fetch

    Returns:
        List of result objects with link, title, snippet, position
    """

    api_key = os.getenv('SERPAPI_API_KEY')
    all_results = []
    start = 0
    page = 1

    print(f"Query: {query}")
    print(f"Target: {max_results} results")
    print(f"{'=' * 70}")

    while len(all_results) < max_results:
        print(f"\n[Page {page}] Fetching results {start+1}-{start+100}...")

        search = GoogleSearch({
            "api_key": api_key,
            "q": query,
            "gl": "es",
            "hl": "es",
            "num": 100,
            "start": start
        })

        response = search.get_dict()
        organic = response.get('organic_results', [])

        if not organic:
            print(f"  No results returned. Stopping.")
            break

        # Extract key fields
        for result in organic:
            all_results.append({
                'position': result.get('position'),
                'title': result.get('title'),
                'link': result.get('link'),
                'snippet': result.get('snippet'),
                'page': page
            })

        print(f"  ✅ Fetched {len(organic)} results (total: {len(all_results)})")

        # Check for next page
        pagination = response.get('serpapi_pagination', {})
        if not pagination.get('next'):
            print(f"  No more pages available")
            break

        # Check if we got fewer results than requested (last page)
        if len(organic) < 100:
            print(f"  Last page reached ({len(organic)} results)")
            break

        start += 100
        page += 1

    print(f"\n{'=' * 70}")
    print(f"✅ Total results fetched: {len(all_results)}")
    print(f"📄 Pages fetched: {page}")
    print(f"💰 Credits used: {page}")

    return all_results[:max_results]

def save_results(results, filename):
    """Save results to JSON file"""
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump({
            'metadata': {
                'total_results': len(results),
                'pages': max(r['page'] for r in results) if results else 0
            },
            'results': results
        }, f, ensure_ascii=False, indent=2)
    print(f"\n💾 Saved to: {filename}")

if __name__ == '__main__':
    results = search_with_pagination("clínica dental Madrid", max_results=250)
    save_results(results, '../outputs/test_serpapi_madrid.json')
```

### Example 3: cURL (Command Line)
```bash
#!/bin/bash
# Simple SerpAPI test with cURL

API_KEY="your_api_key_here"
QUERY="clínica dental Madrid"

curl -s "https://serpapi.com/search.json?engine=google&q=${QUERY}&gl=es&hl=es&num=10&api_key=${API_KEY}" | jq '.organic_results[] | {position, title, link}'
```

### Example 4: Batch Search (Multiple Cities)
```python
#!/usr/bin/env python3
"""Batch search multiple cities with SerpAPI"""

import os
import json
import time
from serpapi import GoogleSearch
from dotenv import load_dotenv

load_dotenv()

def search_city(city_name, results_per_city=100):
    """Search for dental clinics in one city"""

    query = f"clínica dental {city_name}"
    api_key = os.getenv('SERPAPI_API_KEY')

    search = GoogleSearch({
        "api_key": api_key,
        "q": query,
        "gl": "es",
        "hl": "es",
        "num": results_per_city
    })

    response = search.get_dict()
    organic = response.get('organic_results', [])

    return {
        'city': city_name,
        'query': query,
        'results_count': len(organic),
        'results': organic
    }

def batch_search(cities, results_per_city=100):
    """Search multiple cities"""

    all_city_results = []

    for i, city in enumerate(cities, 1):
        print(f"[{i}/{len(cities)}] Searching: {city}")

        city_data = search_city(city, results_per_city)
        all_city_results.append(city_data)

        print(f"  ✅ Found {city_data['results_count']} results")

        # Rate limiting (be respectful)
        if i < len(cities):
            time.sleep(1)

    return all_city_results

if __name__ == '__main__':
    cities = ["Madrid", "Barcelona", "Valencia"]
    results = batch_search(cities, results_per_city=10)

    # Save
    with open('../outputs/batch_test.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Batch complete: {len(cities)} cities")
```

═══════════════════════════════════════════════════════════════

## Edge Cases & Caveats

### 1. Google Result Limits
**Issue**: Google doesn't provide infinite results
**Limit**: ~1000 results max per query (varies)
**Mitigation**:
- Don't rely on results beyond page 10 (1000 results)
- Use multiple queries with variations if needed
- Accept 500-1000 results as practical maximum

### 2. Result Quality Degradation
**Issue**: Results after page 5-10 become less relevant
**Observation**: Top 100-200 results are highest quality
**Recommendation**:
- Target 250-300 results per city (pages 1-3)
- Beyond 500 results → diminishing returns

### 3. Caching Behavior
**Issue**: Repeated queries may return cached results
**Impact**: Cached results may not count toward quota (plan-dependent)
**Control**:
```python
# Force fresh results
params = {"no_cache": True, ...}
```

### 4. Rate Limiting
**Issue**: Too many requests too fast may trigger rate limits
**Mitigation**:
```python
import time
time.sleep(1)  # 1 second between requests
```

### 5. Empty Results Mid-Pagination
**Issue**: Sometimes Google returns 0 results on a page
**Example**: Page 1 has 100 results, Page 2 has 0, Page 3 has 50
**Handling**:
```python
if not organic_results:
    # Could be temporary - try next page or stop
    if retries < 3:
        continue  # Try next page
    else:
        break  # Give up
```

### 6. Domain Duplicates
**Issue**: Same domain appears multiple times (different pages)
**Example**:
- `example.com/` (position 5)
- `example.com/about` (position 23)
- `example.com/contact` (position 67)

**Mitigation**:
```python
from urllib.parse import urlparse

seen_domains = set()
unique_results = []

for result in all_results:
    domain = urlparse(result['link']).netloc
    if domain not in seen_domains:
        unique_results.append(result)
        seen_domains.add(domain)
```

### 7. Missing Fields
**Issue**: Not all results have all fields
**Example**: Some results may lack `snippet` or have empty `title`
**Handling**:
```python
url = result.get('link', '')
title = result.get('title', 'No Title')
snippet = result.get('snippet', '')

if not url:
    continue  # Skip results without URL
```

### 8. Special Result Types
**Issue**: Response may include non-organic results
**Types**:
- `ads` - Paid advertisements
- `local_results` - Google Maps results
- `knowledge_graph` - Info boxes
- `inline_videos` - Video carousels

**Handling**:
```python
# Focus only on organic results
organic = response.get('organic_results', [])
# Ignore: ads, local_results, knowledge_graph, etc.
```

### 9. Query Encoding
**Issue**: Special characters in queries need proper encoding
**Example**:
```python
# ✅ Good
q = "clínica dental Madrid"  # SerpAPI client handles encoding

# ❌ Bad (if using raw requests)
q = "clínica dental Madrid"  # May break without URL encoding
```

### 10. API Key Security
**Issue**: API keys in code = security risk
**Best Practice**:
```python
# ✅ Good - Use environment variables
api_key = os.getenv('SERPAPI_API_KEY')

# ❌ Bad - Hardcoded
api_key = "1234567890abcdef"  # NEVER DO THIS
```

═══════════════════════════════════════════════════════════════

## Quick Reference Card

### Minimal Working Example
```python
from serpapi import GoogleSearch
import os

search = GoogleSearch({
    "api_key": os.getenv('SERPAPI_API_KEY'),
    "q": "clínica dental Madrid",
    "gl": "es",
    "hl": "es",
    "num": 100
})

results = search.get_dict()
urls = [r['link'] for r in results['organic_results']]
```

### Required Parameters
```python
{
    "api_key": "YOUR_KEY",  # Required
    "q": "your query"        # Required
}
```

### Recommended Parameters
```python
{
    "api_key": "YOUR_KEY",
    "q": "clínica dental Madrid",
    "gl": "es",    # Country
    "hl": "es",    # Language
    "num": 100,    # Max results per page
    "start": 0     # Pagination offset
}
```

### Pagination Pattern
```python
start = 0
while True:
    results = search(start=start)
    if not results or not has_next_page(results):
        break
    start += 100
```

### Cost Formula
```
Total Credits = Number of Cities × Pages per City
Total Cost = Total Credits × $0.015
```

═══════════════════════════════════════════════════════════════

**Next Agent**: You now have everything needed to implement SerpAPI search!

See `MIGRATION_GUIDE.md` for step-by-step migration from Firecrawl.
