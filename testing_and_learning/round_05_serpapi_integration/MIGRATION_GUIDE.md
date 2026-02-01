# Migration Guide: Firecrawl Search → SerpAPI

**For Next Agent**: Step-by-step guide to migrate from Firecrawl /search to SerpAPI

**Date**: 2025-11-04
**Version**: 1.0

═══════════════════════════════════════════════════════════════

## Why Migrate?

**Problem**:
- Firecrawl /search: 100-result hard limit, NO pagination
- Our need: 250+ results per city × 250 cities = 62,500+ pages

**Solution**:
- SerpAPI: Unlimited pagination via `start` parameter
- Can retrieve 250-1000 results per query

═══════════════════════════════════════════════════════════════

## What Changes

### L1: Search Layer (REPLACE)
```
❌ OLD: Firecrawl /v2/search
✅ NEW: SerpAPI /search.json
```

### L2: Scrape Layer (UNCHANGED)
```
✅ KEEP: Firecrawl /v2/scrape
```

### L3: Classification Layer (UNCHANGED)
```
✅ KEEP: Claude LLM classification
```

═══════════════════════════════════════════════════════════════

## Side-by-Side Comparison

### OLD: Firecrawl Search
```python
import requests
import os

def firecrawl_search(query, limit=100):
    api_url = "https://api.firecrawl.dev/v2/search"

    payload = {
        "query": query,
        "limit": limit,  # MAX: 100 (hard limit)
        "country": "ES",
        "sources": ["web"],
        "scrapeOptions": {
            "formats": ["markdown", "links"],
            "onlyMainContent": True
        }
    }

    headers = {
        "Authorization": f"Bearer {os.getenv('FIRECRAWL_API_KEY')}",
        "Content-Type": "application/json"
    }

    resp = requests.post(api_url, json=payload, headers=headers)
    data = resp.json()

    # Returns results WITH content already scraped
    results = data['data']['web']

    return results  # Max 100 results, NO pagination
```

**Limitations**:
- ❌ Max 100 results (hard limit)
- ❌ NO pagination (offset, page, skip all fail)
- ✅ Returns scraped content (nice, but not needed if we scrape separately)

### NEW: SerpAPI Search
```python
from serpapi import GoogleSearch
import os

def serpapi_search(query, max_results=250):
    api_key = os.getenv('SERPAPI_API_KEY')
    all_results = []
    start = 0

    while len(all_results) < max_results:
        search = GoogleSearch({
            "api_key": api_key,
            "q": query,
            "gl": "es",
            "hl": "es",
            "num": 100,
            "start": start  # Pagination offset
        })

        response = search.get_dict()
        organic = response.get('organic_results', [])

        if not organic:
            break  # No more results

        all_results.extend(organic)
        start += 100  # Next page

        # Check if more pages exist
        pagination = response.get('serpapi_pagination', {})
        if not pagination.get('next'):
            break

    return all_results[:max_results]  # Can get 250+ results!
```

**Advantages**:
- ✅ Pagination support (250, 500, 1000+ results)
- ✅ Same cost model (1 credit per search)
- ❌ Returns URLs only (must scrape separately with Firecrawl /scrape)

═══════════════════════════════════════════════════════════════

## Migration Steps

### Step 1: Install SerpAPI Client
```bash
pip install google-search-results
# OR
pip install serpapi
```

### Step 2: Add API Key to .env
```bash
# Add to .env file
SERPAPI_API_KEY=your_serpapi_key_here
```

Get your key: https://serpapi.com/dashboard

### Step 3: Replace Search Function

**OLD CODE** (`discover.py`):
```python
def search(self, query: str, limit: int = 10) -> List[Dict]:
    """Search using Firecrawl /v2/search"""
    api_url = f"{self.base_url}/search"

    payload = {
        "query": query,
        "limit": limit,
        "country": "ES",
        "sources": ["web"],
        "scrapeOptions": {...}
    }

    resp = requests.post(api_url, json=payload, headers=headers, timeout=30)
    data = resp.json()

    results = []
    for result in data['data']['web']:
        results.append({
            'url': result.get('url'),
            'title': result.get('title'),
            'description': result.get('description'),
            'markdown': result.get('markdown', ''),  # Already scraped
            'links': result.get('links', [])
        })

    return results[:limit]
```

**NEW CODE** (SerpAPI):
```python
from serpapi import GoogleSearch

def search(self, query: str, max_results: int = 250) -> List[Dict]:
    """Search using SerpAPI with pagination"""

    api_key = os.getenv('SERPAPI_API_KEY')
    all_results = []
    start = 0

    while len(all_results) < max_results:
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
            break

        # Extract URLs (NO markdown yet - must scrape separately)
        for result in organic:
            all_results.append({
                'url': result.get('link'),
                'title': result.get('title'),
                'description': result.get('snippet'),
                'position': result.get('position'),
                'page': (start // 100) + 1
            })

        # Check for next page
        pagination = response.get('serpapi_pagination', {})
        if not pagination.get('next'):
            break

        start += 100

    return all_results[:max_results]
```

### Step 4: Update Scrape Logic

**IMPORTANT**: SerpAPI returns URLs only (no content). You MUST scrape each URL separately.

**Add separate scraping step**:
```python
def scrape_urls(urls: List[str]) -> List[Dict]:
    """Scrape URLs using Firecrawl /v2/scrape"""

    api_key = os.getenv('FIRECRAWL_API_KEY')
    scraped_pages = []

    for url in urls:
        api_url = "https://api.firecrawl.dev/v2/scrape"

        payload = {
            "url": url,
            "formats": ["markdown", "links"],
            "onlyMainContent": True
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        try:
            resp = requests.post(api_url, json=payload, headers=headers, timeout=30)
            data = resp.json()

            scraped_data = data.get('data', {})
            scraped_pages.append({
                'url': url,
                'markdown': scraped_data.get('markdown', ''),
                'links': scraped_data.get('links', []),
                'title': scraped_data.get('metadata', {}).get('title', ''),
                'status_code': scraped_data.get('metadata', {}).get('statusCode', 0)
            })

        except Exception as e:
            print(f"  ⚠️  Failed to scrape {url}: {e}")
            continue

    return scraped_pages
```

### Step 5: Update Main Pipeline

**OLD FLOW**:
```
Search (Firecrawl) → Returns content → Classify (LLM)
```

**NEW FLOW**:
```
Search (SerpAPI) → Scrape (Firecrawl) → Classify (LLM)
       ↓                    ↓                  ↓
   URLs only         Full content        Categories
```

**Updated `process_query` function**:
```python
def process_query(self, query: str, max_results: int):
    """
    Process one search query with pagination

    Returns list of classified pages
    """

    # Step 1: Search with SerpAPI (get URLs)
    print(f"🔍 Searching: {query}")
    search_results = self.search(query, max_results)
    print(f"  Found {len(search_results)} results")

    # Step 2: Scrape URLs with Firecrawl
    print(f"📄 Scraping {len(search_results)} pages...")
    urls = [r['url'] for r in search_results]
    scraped_pages = self.scrape_urls(urls)
    print(f"  Scraped {len(scraped_pages)} pages")

    # Step 3: Classify with LLM (existing code unchanged)
    print(f"🤖 Classifying pages...")
    classified_pages = self.classify(scraped_pages)  # Your existing L3 code

    return classified_pages
```

═══════════════════════════════════════════════════════════════

## File Structure Changes

### OLD Structure (Firecrawl only)
```
search_system/
    l1_search_and_scrape/
        discover.py        # Firecrawl search + scrape in one
        config.json
```

### NEW Structure (SerpAPI + Firecrawl)
```
search_system/
    l1_search/            # SerpAPI search layer
        discover_serpapi.py
        config.json
    l2_scrape/            # Firecrawl scrape layer
        scrape_urls.py
        config.json
    l3_classify/          # LLM classification (unchanged)
        classify.py
```

**OR** (simpler - keep in one layer):
```
search_system/
    l1_search_and_scrape/
        discover_serpapi.py      # Uses SerpAPI for search
        scraper.py               # Uses Firecrawl for scrape
        config.json
```

═══════════════════════════════════════════════════════════════

## Testing the Migration

### Test 1: Simple Search (10 Results)
```bash
python3 discover_serpapi.py "clínica dental Madrid" 10
```

**Expected Output**:
```
Query: clínica dental Madrid
Target: 10 results
======================================================================
🔍 Searching...
  Found 10 results
📄 Scraping 10 pages...
  Scraped 10 pages
======================================================================
✅ Complete: 10 pages
Output: outputs/test_serpapi_madrid.json
```

### Test 2: Pagination Test (250 Results)
```bash
python3 discover_serpapi.py "clínica dental Barcelona" 250
```

**Expected Output**:
```
Query: clínica dental Barcelona
Target: 250 results
======================================================================
🔍 Searching...
[Page 1] Fetched 100 results (total: 100)
[Page 2] Fetched 100 results (total: 200)
[Page 3] Fetched 50 results (total: 250)
  Found 250 results
📄 Scraping 250 pages...
  ...
======================================================================
✅ Complete: 250 pages
Credits used:
  - SerpAPI: 3 credits
  - Firecrawl: 250 credits
Output: outputs/test_serpapi_barcelona.json
```

### Test 3: Compare Results
```bash
# Old (Firecrawl search)
python3 discover_firecrawl.py "clínica dental Madrid" 100

# New (SerpAPI search)
python3 discover_serpapi.py "clínica dental Madrid" 100

# Compare
diff outputs/firecrawl_madrid.json outputs/serpapi_madrid.json
```

═══════════════════════════════════════════════════════════════

## Common Migration Issues

### Issue 1: Missing `markdown` Field
**Problem**: SerpAPI doesn't return content, only URLs
**Solution**: Must scrape separately with Firecrawl /scrape

### Issue 2: Different Field Names
**Firecrawl**: `description`, `url`
**SerpAPI**: `snippet`, `link`

**Fix**: Map fields consistently
```python
# Firecrawl format
result = {
    'url': serpapi_result['link'],  # link → url
    'description': serpapi_result['snippet']  # snippet → description
}
```

### Issue 3: Rate Limiting
**Problem**: Scraping 250+ pages quickly may hit rate limits
**Solution**: Add delay between scrapes
```python
import time
for url in urls:
    scrape(url)
    time.sleep(0.5)  # 500ms delay
```

### Issue 4: API Key Not Found
**Problem**: `SERPAPI_API_KEY` not in environment
**Solution**: Check `.env` file
```bash
# Verify
echo $SERPAPI_API_KEY

# If empty, add to .env
echo "SERPAPI_API_KEY=your_key" >> .env
source .env
```

### Issue 5: Empty Results
**Problem**: `organic_results` is empty
**Causes**:
- Query too specific (no results)
- Pagination past last page
- API error

**Solution**: Check response status
```python
if 'error' in response:
    print(f"API Error: {response['error']}")
    return []

organic = response.get('organic_results', [])
if not organic:
    print("No results found (end of pagination or no matches)")
    return all_results  # Return what we have
```

═══════════════════════════════════════════════════════════════

## Rollback Plan

If SerpAPI migration fails, revert to Firecrawl:

### Step 1: Keep Old Code
```bash
# Don't delete old code - rename it
mv discover.py discover_firecrawl_backup.py
mv discover_serpapi.py discover.py
```

### Step 2: Test Rollback
```bash
# Revert
mv discover.py discover_serpapi.py
mv discover_firecrawl_backup.py discover.py

# Test
python3 discover.py "clínica dental Madrid" 100
```

### Step 3: Switch Environment Variable
```bash
# In code, support both
USE_SERPAPI = os.getenv('USE_SERPAPI', 'false').lower() == 'true'

if USE_SERPAPI:
    results = search_with_serpapi(query)
else:
    results = search_with_firecrawl(query)
```

═══════════════════════════════════════════════════════════════

## Success Checklist

- [ ] SerpAPI client installed (`pip install serpapi`)
- [ ] API key added to `.env` file
- [ ] Test search returns results (10 results test)
- [ ] Pagination works (250 results test)
- [ ] Firecrawl scraping works (L2 unchanged)
- [ ] LLM classification works (L3 unchanged)
- [ ] Cost tracking implemented
- [ ] Error handling tested
- [ ] Performance acceptable (time and cost)
- [ ] Documentation updated

═══════════════════════════════════════════════════════════════

## Next Steps

After successful migration:

1. **Test with 3 cities** (Madrid, Barcelona, Sevilla)
2. **Validate results quality** (compare with Firecrawl baseline)
3. **Run 10-city pilot** (confirm cost and performance)
4. **Scale to 250 cities** (production run)

═══════════════════════════════════════════════════════════════

**Migration complete!** 🎉

See `API_REFERENCE.md` for complete SerpAPI documentation.
See `COST_MODEL.md` for detailed cost projections.
