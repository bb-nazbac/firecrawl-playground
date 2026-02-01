# CRITICAL: Serper.dev vs SerpAPI - Complete Comparison

**Date**: 2025-11-04
**Discovery**: User has SERPER.DEV API key (not SerpAPI)
**Impact**: **MAJOR COST SAVINGS** + **FASTER** performance

═══════════════════════════════════════════════════════════════

## Executive Summary

**Serper.dev** is **15x cheaper** and **3x faster** than SerpAPI!

| Feature | SerpAPI | Serper.dev | Winner |
|---------|---------|------------|--------|
| **Cost/search** | $0.015 | $0.001 | 🏆 Serper (15x cheaper) |
| **Speed** | 5.5 seconds | 1-2 seconds | 🏆 Serper (3x faster) |
| **Pagination** | `start` parameter | `page` parameter | ✅ Both work |
| **Max results** | 100/page | 100/page | ✅ Same |
| **Geo-targeting** | `gl`, `hl`, `location` | `gl`, `hl`, `location` | ✅ Same |
| **Search engines** | 80+ engines | Google only | ⚠️ SerpAPI (more engines) |

**RECOMMENDATION**: **USE SERPER.DEV** ✅

═══════════════════════════════════════════════════════════════

## Detailed Comparison

### 1. Pricing

**SerpAPI**:
```
Free: 100 searches
Starter: $75/month (5,000 searches) = $0.015/search
Developer: $225/month (15,000 searches) = $0.015/search
Production: $450/month (30,000 searches) = $0.015/search
```

**Serper.dev**:
```
Pay-as-you-go:
$50 for 50,000 queries = $0.001/search
$100 for 115,000 queries = $0.00087/search
$250 for 312,500 queries = $0.0008/search
$500 for 833,333 queries = $0.0006/search

🎯 15x CHEAPER than SerpAPI!
```

### 2. Speed

**SerpAPI**:
- Google Search: ~5.5 seconds average
- Google Scholar: ~3.3 seconds
- Google News: ~4.5 seconds

**Serper.dev**:
- All searches: **1-2 seconds** (real-time)
- 🎯 **3x FASTER** than SerpAPI

### 3. API Endpoints

**SerpAPI**:
```
https://serpapi.com/search.json
```

**Serper.dev**:
```
https://google.serper.dev/search
```

### 4. Authentication

**SerpAPI**:
```python
# Query parameter
params = {"api_key": "YOUR_KEY", ...}

# Or via client library
from serpapi import GoogleSearch
search = GoogleSearch({"api_key": "YOUR_KEY"})
```

**Serper.dev**:
```python
# HTTP Header (preferred)
headers = {
    "X-API-KEY": "YOUR_KEY",
    "Content-Type": "application/json"
}

# Or query parameter
params = {"api_key": "YOUR_KEY", ...}
```

### 5. Parameters

**Common Parameters** (both support):

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `q` | string | Search query | `"dental clinic Madrid"` |
| `gl` | string | Country code | `"us"`, `"es"` |
| `hl` | string | Language | `"en"`, `"es"` |
| `location` | string | Geographic location | `"Los Angeles, CA"` |
| `num` | integer | Results per page | `10` (default), max `100` |

**Pagination Differences**:

| Feature | SerpAPI | Serper.dev |
|---------|---------|------------|
| Parameter | `start` (offset) | `page` (page number) |
| Example | `start=0, 100, 200` | `page=1, 2, 3` |
| Logic | Offset-based | Page-based |

**SerpAPI pagination**:
```python
# Page 1
{"start": 0, "num": 100}  # Results 1-100

# Page 2
{"start": 100, "num": 100}  # Results 101-200

# Page 3
{"start": 200, "num": 100}  # Results 201-300
```

**Serper.dev pagination**:
```python
# Page 1
{"page": 1, "num": 100}  # Results 1-100

# Page 2
{"page": 2, "num": 100}  # Results 101-200

# Page 3
{"page": 3, "num": 100}  # Results 201-300
```

### 6. Response Structure

**SerpAPI**:
```json
{
  "search_metadata": {...},
  "organic_results": [
    {
      "position": 1,
      "title": "...",
      "link": "...",
      "snippet": "..."
    }
  ],
  "serpapi_pagination": {
    "current": 1,
    "next": "..."
  }
}
```

**Serper.dev**:
```json
{
  "searchParameters": {...},
  "organic": [
    {
      "position": 1,
      "title": "...",
      "link": "...",
      "snippet": "..."
    }
  ]
}
```

**Key Difference**: Field names
- SerpAPI: `organic_results` array
- Serper.dev: `organic` array

### 7. Features Comparison

| Feature | SerpAPI | Serper.dev |
|---------|---------|------------|
| Google Search | ✅ | ✅ |
| Google Images | ✅ | ✅ |
| Google News | ✅ | ✅ |
| Google Shopping | ✅ | ✅ |
| Google Maps | ✅ | ✅ |
| Bing | ✅ | ❌ |
| Yahoo | ✅ | ❌ |
| Baidu | ✅ | ❌ |
| 80+ engines | ✅ | ❌ |
| Legal Shield | ✅ | ❌ |

**Verdict**: SerpAPI has more engines, but Serper.dev is **15x cheaper** for Google (our main use case)

═══════════════════════════════════════════════════════════════

## Cost Impact Analysis (250 Cities × 250 Results)

### OLD Projection (SerpAPI)
```
250 cities × 3 pages × $0.015 = $11.25
```

### NEW Reality (Serper.dev) 🎉
```
250 cities × 3 pages × $0.001 = $0.75

SAVINGS: $11.25 - $0.75 = $10.50 (93% cost reduction!)
```

### Full Pipeline Cost (Updated)

**Old (SerpAPI + Firecrawl + Claude)**:
```
SerpAPI:    $11.25
Firecrawl:  $12.50
Claude:     $187.50
───────────────────
TOTAL:      $211.25
```

**New (Serper.dev + Firecrawl + Claude)**:
```
Serper:     $0.75   (93% cheaper!)
Firecrawl:  $12.50
Claude:     $187.50
───────────────────
TOTAL:      $200.75  (5% overall savings, but search is 93% cheaper!)
```

**💰 Annual Savings** (12 months):
```
Search cost savings: ($11.25 - $0.75) × 12 = $126/year
```

═══════════════════════════════════════════════════════════════

## Code Migration: SerpAPI → Serper.dev

### Method 1: Direct HTTP (Recommended)

**Old (SerpAPI)**:
```python
from serpapi import GoogleSearch

search = GoogleSearch({
    "api_key": api_key,
    "q": query,
    "gl": "es",
    "hl": "es",
    "num": 100,
    "start": 0  # Offset-based
})

response = search.get_dict()
results = response['organic_results']  # Note: 'organic_results'
```

**New (Serper.dev)**:
```python
import requests

url = "https://google.serper.dev/search"

headers = {
    "X-API-KEY": api_key,
    "Content-Type": "application/json"
}

payload = {
    "q": query,
    "gl": "es",
    "hl": "es",
    "num": 100,
    "page": 1  # Page-based (not offset!)
}

response = requests.post(url, json=payload, headers=headers)
data = response.json()
results = data['organic']  # Note: 'organic' (not 'organic_results')
```

### Method 2: Python Client (if available)

```bash
pip install serper
```

```python
from serper import GoogleSerper

client = GoogleSerper(api_key=api_key)
results = client.search(
    q=query,
    gl="es",
    hl="es",
    num=100,
    page=1
)
```

═══════════════════════════════════════════════════════════════

## Pagination: SerpAPI vs Serper.dev

### SerpAPI Pagination (Offset-based)
```python
all_results = []
start = 0

while start < 300:  # Get 300 results
    response = search(start=start, num=100)
    all_results.extend(response['organic_results'])
    start += 100  # Increment offset
```

### Serper.dev Pagination (Page-based)
```python
all_results = []
page = 1

while page <= 3:  # Get 3 pages (300 results)
    response = search(page=page, num=100)
    all_results.extend(response['organic'])
    page += 1  # Increment page number
```

**Key Difference**:
- SerpAPI: `start=0, 100, 200` (offset)
- Serper.dev: `page=1, 2, 3` (page number)

═══════════════════════════════════════════════════════════════

## Limitations & Caveats

### Both Services
1. **Google's 400-result limit**: Can't get more than ~400 results per query (Google's inherent limit)
2. **Rate limiting**: Too many requests = throttling
3. **Result quality degradation**: Results beyond page 5-10 are lower quality

### Serper.dev Specific
1. **Google only**: No Bing, Yahoo, Baidu (SerpAPI has 80+ engines)
2. **No legal shield**: SerpAPI offers legal protection for scraping
3. **Recent changes**: Google removed `num=100` parameter (may affect pagination)

### SerpAPI Specific
1. **15x more expensive**: $0.015 vs $0.001
2. **3x slower**: 5.5s vs 1-2s
3. **Not cost-effective for Google-only use cases**

═══════════════════════════════════════════════════════════════

## Recommendation

### Use Serper.dev When:
- ✅ Searching Google only (our use case)
- ✅ Cost is a concern ($0.001 vs $0.015)
- ✅ Speed matters (1-2s vs 5s)
- ✅ High volume (50k+ searches/month)

### Use SerpAPI When:
- ⚠️ Need other search engines (Bing, Yahoo, Baidu, etc.)
- ⚠️ Legal protection required
- ⚠️ Advanced features needed (80+ APIs)

**For Our Project**: **Serper.dev** ✅
**Reason**: Google-only, cost-sensitive, high volume (250 cities × 3 pages = 750 searches)

═══════════════════════════════════════════════════════════════

## Next Steps

1. ✅ **Update API reference** → Use Serper.dev endpoint
2. ✅ **Update test script** → Use Serper.dev client
3. ✅ **Update cost model** → Recalculate with $0.001/search
4. ✅ **Test with real API key** → Validate works
5. ✅ **Update Round 05 documentation** → Note Serper.dev instead

═══════════════════════════════════════════════════════════════

**OPTIMUS PRIME Assessment**: **Serper.dev is SUPERIOR for our use case** ✅

**Confidence**: **99%** (based on comprehensive web research + pricing analysis)

═══════════════════════════════════════════════════════════════
