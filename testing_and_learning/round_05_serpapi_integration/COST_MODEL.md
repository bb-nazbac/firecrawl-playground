# Cost Model: SerpAPI + Firecrawl + Claude Pipeline

**Date**: 2025-11-04
**Version**: 1.0
**Purpose**: Complete cost analysis for 250-city Spain dental clinic discovery

═══════════════════════════════════════════════════════════════

## Executive Summary

**NEW Pipeline Cost** (SerpAPI + Firecrawl scrape):
- 250 cities × 250 results = 62,500 pages
- **Total Cost**: **~$211** (vs. $78 for 100 results w/ Firecrawl only)
- **Benefit**: 2.5x more results for 2.7x cost → **Cost-effective scaling**

**Breakdown**:
- SerpAPI search: **$11.25** (750 searches)
- Firecrawl scrape: **$12.50** (62,500 pages)
- Claude classify: **$187.50** (62,500 pages)

═══════════════════════════════════════════════════════════════

## API Pricing Reference

### SerpAPI Pricing (Google Search)

| Plan | Searches/Month | Price/Month | Cost Per Search |
|------|---------------|-------------|-----------------|
| Free | 100 | $0 | $0 |
| Starter | 5,000 | $75 | $0.015 |
| Developer | 15,000 | $225 | $0.015 |
| Production | 30,000 | $450 | $0.015 |

**Source**: https://serpapi.com/pricing
**Our Cost**: **$0.015 per search** (regardless of `num` parameter)

**Key Rule**: Each page = 1 search = 1 credit
- Page 1 (`start=0`) → 1 credit
- Page 2 (`start=100`) → 1 credit
- Page 3 (`start=200`) → 1 credit

### Firecrawl Pricing (Scrape Only)

**Scrape Endpoint** (`/v2/scrape`):
- **Cost**: ~1 credit per page scraped
- **1 credit** = **$0.001** ($1 per 1,000 credits)

**Source**: Firecrawl docs + our testing
**Our Cost**: **$0.0002 per page** (0.2 credits per page from Round 02 testing)

### Claude Pricing (Sonnet 3.5)

**Model**: Claude 3.5 Sonnet (2024-10-22)
- **Input**: $3.00 per million tokens
- **Output**: $15.00 per million tokens

**Our Usage** (from crawl_system testing):
- Average: ~2K input tokens per page (markdown content)
- Average: ~200 output tokens per page (classification + extraction)
- **Cost per page**: ~$0.003

═══════════════════════════════════════════════════════════════

## Cost Calculation Formulas

### Formula 1: SerpAPI Search Cost
```
SerpAPI Cost = Cities × (Results per City / 100) × $0.015

Example:
250 cities × (250 results / 100 pages) × $0.015 = 250 × 2.5 × $0.015 = $9.375

Note: Rounds up to 3 pages (250 results requires pages 1, 2, and part of 3)
Actual: 250 cities × 3 pages × $0.015 = $11.25
```

### Formula 2: Firecrawl Scrape Cost
```
Firecrawl Cost = Total Pages × $0.0002

Example:
62,500 pages × $0.0002 = $12.50
```

### Formula 3: Claude Classification Cost
```
Claude Cost = Total Pages × $0.003

Example:
62,500 pages × $0.003 = $187.50
```

### Formula 4: Total Pipeline Cost
```
Total = SerpAPI + Firecrawl + Claude

Example:
$11.25 + $12.50 + $187.50 = $211.25
```

═══════════════════════════════════════════════════════════════

## Scenario Analysis

### Scenario A: Conservative (100 results/city)
**Goal**: Match Firecrawl's 100-result limit

```
Cities: 250
Results per city: 100
Total pages: 25,000

SerpAPI:    250 cities × 1 page × $0.015        = $3.75
Firecrawl:  25,000 pages × $0.0002              = $5.00
Claude:     25,000 pages × $0.003               = $75.00
───────────────────────────────────────────────────────────
TOTAL:                                            $83.75

Time: ~2.5 hours
Coverage: Top 100 results per city (good)
```

### Scenario B: Target (250 results/city) ⭐ RECOMMENDED
**Goal**: User's original target (250 results)

```
Cities: 250
Results per city: 250
Total pages: 62,500

SerpAPI:    250 cities × 3 pages × $0.015       = $11.25
Firecrawl:  62,500 pages × $0.0002              = $12.50
Claude:     62,500 pages × $0.003               = $187.50
───────────────────────────────────────────────────────────
TOTAL:                                            $211.25

Time: ~6 hours
Coverage: Top 250 results per city (excellent)
ROI: 2.5x more results for 2.5x cost
```

### Scenario C: Maximum (500 results/city)
**Goal**: Maximum practical coverage

```
Cities: 250
Results per city: 500
Total pages: 125,000

SerpAPI:    250 cities × 5 pages × $0.015       = $18.75
Firecrawl:  125,000 pages × $0.0002             = $25.00
Claude:     125,000 pages × $0.003              = $375.00
───────────────────────────────────────────────────────────
TOTAL:                                            $418.75

Time: ~12 hours
Coverage: Top 500 results per city (comprehensive)
Diminishing returns: Results 250-500 are lower quality
```

### Scenario D: Aggressive (1000 results/city)
**Goal**: Maximum possible (Google limit)

```
Cities: 250
Results per city: 1000
Total pages: 250,000

SerpAPI:    250 cities × 10 pages × $0.015      = $37.50
Firecrawl:  250,000 pages × $0.0002             = $50.00
Claude:     250,000 pages × $0.003              = $750.00
───────────────────────────────────────────────────────────
TOTAL:                                            $837.50

Time: ~24 hours
Coverage: Maximum Google allows (near-complete)
⚠️ Warning: Results 500+ are very low quality
```

═══════════════════════════════════════════════════════════════

## Cost Optimization Strategies

### Strategy 1: Filter Before Scraping (Highest Impact)
**Idea**: Don't scrape every URL from SerpAPI

```python
# Current: Scrape all 250 results
search_results = serpapi_search(query, 250)  # 250 URLs
scraped = firecrawl_scrape(search_results)   # Scrape all 250

# Optimized: Filter first, scrape only relevant
search_results = serpapi_search(query, 250)  # 250 URLs

# Filter by domain (exclude aggregators)
filtered = [r for r in search_results if not is_aggregator(r['domain'])]
# Filtered: ~200 URLs (removed Doctoralia, TopDoctors, etc.)

# Filter by position (top results are higher quality)
top_results = filtered[:150]  # Top 150 only

scraped = firecrawl_scrape(top_results)  # Scrape only 150

# Savings
Old cost: 250 × $0.0002 = $0.05 per city
New cost: 150 × $0.0002 = $0.03 per city
Savings: $0.02 per city × 250 cities = $5.00 total
```

**Impact**: **Save $5-10** on Firecrawl + **$37-75** on Claude = **$42-85 total**

### Strategy 2: Deduplicate Domains Early
**Idea**: Same domain may appear multiple times

```python
# Current: Scrape duplicate domains
search_results = [
    {'link': 'example.com/', 'position': 5},
    {'link': 'example.com/about', 'position': 23},
    {'link': 'example.com/contact', 'position': 67}
]
# Scrapes: 3 pages → 3 × $0.0002 = $0.0006

# Optimized: Keep only first occurrence per domain
from urllib.parse import urlparse

seen_domains = set()
unique_results = []

for result in search_results:
    domain = urlparse(result['link']).netloc
    if domain not in seen_domains:
        unique_results.append(result)
        seen_domains.add(domain)

# Scrapes: 1 page → 1 × $0.0002 = $0.0002
# Savings: 66% reduction
```

**Impact**: **Save ~30-40%** on Firecrawl + Claude = **$60-90 total**

### Strategy 3: Use Caching
**Idea**: SerpAPI caches results (may not count toward quota)

```python
# First run: Full cost
search1 = serpapi_search("clínica dental Madrid", no_cache=False)
# Cost: 1 credit

# Rerun same query (cached):
search2 = serpapi_search("clínica dental Madrid", no_cache=False)
# Cost: 0 credits (cached)

# Force fresh (if needed):
search3 = serpapi_search("clínica dental Madrid", no_cache=True)
# Cost: 1 credit
```

**Impact**: **Free reruns** (useful for testing/debugging)

### Strategy 4: Batch Scraping (Reduce Overhead)
**Idea**: Batch multiple URLs in one Firecrawl call (if API supports)

```python
# Check if Firecrawl supports batch scraping
# If yes: Scrape 10 URLs at once → reduce latency & potential bulk discount

# Current: 1 URL per call
for url in urls:
    scrape(url)  # 250 API calls

# Optimized: 10 URLs per call (if supported)
for batch in chunks(urls, 10):
    scrape_batch(batch)  # 25 API calls
```

**Impact**: **Faster execution** (may not reduce cost, but improves speed)

### Strategy 5: Progressive Depth
**Idea**: Start shallow, go deeper only if needed

```python
# Phase 1: Search 100 results per city (fast, cheap)
results = search_with_serpapi(query, 100)
# Cost: 1 page × $0.015 = $0.015 per city

# Analyze coverage
if coverage_sufficient(results):
    return results  # Done
else:
    # Phase 2: Fetch next 150 results (250 total)
    results += search_with_serpapi(query, 150, start=100)
    # Additional cost: 2 pages × $0.015 = $0.03
```

**Impact**: **Adaptive spending** (only go deep when needed)

═══════════════════════════════════════════════════════════════

## Cost Comparison: Old vs New

### OLD System (Firecrawl /search only)
```
Pipeline: Firecrawl /search → Claude classify

250 cities × 100 results = 25,000 pages

Firecrawl:  25,000 searches × $0.0002*        = $5.00
Claude:     25,000 pages × $0.003             = $75.00
───────────────────────────────────────────────────────────
TOTAL:                                          $80.00

* Estimate based on scrape cost (search cost may differ)

Limitation: MAX 100 results (no pagination)
```

### NEW System (SerpAPI search + Firecrawl scrape)
```
Pipeline: SerpAPI /search → Firecrawl /scrape → Claude classify

250 cities × 250 results = 62,500 pages

SerpAPI:    750 searches × $0.015             = $11.25
Firecrawl:  62,500 scrapes × $0.0002          = $12.50
Claude:     62,500 pages × $0.003             = $187.50
───────────────────────────────────────────────────────────
TOTAL:                                          $211.25

Benefit: 2.5x more results (25k → 62.5k)
Cost increase: 2.6x ($80 → $211)
ROI: Excellent (more coverage, nearly linear cost)
```

### Winner: NEW System ✅
- **2.5x more data for 2.6x cost** = Cost-effective scaling
- **Pagination support** = No hard limits
- **Future-proof** = Can scale to 500+ results if needed

═══════════════════════════════════════════════════════════════

## Monthly Budget Planning

### For Production Use (Ongoing)

**Assumptions**:
- Run once per month (refresh data)
- 250 cities × 250 results
- Full pipeline (search → scrape → classify)

**Monthly Cost**: **$211.25**

**Annual Cost**: **$2,535** (12 months)

### SerpAPI Plan Selection

**For 250-city run**:
- Credits needed: 750 per run
- Monthly: 750 credits
- **Plan**: Free (100) + one-time purchase, OR Starter ($75/month for 5,000)

**Recommendation**: **Starter Plan** ($75/month)
- Covers 6-7 runs per month (5,000 / 750 = 6.6)
- Plenty of headroom for testing/retries
- No per-search charges

### Cost Allocation

| Component | Monthly | Annual | % of Total |
|-----------|---------|--------|------------|
| SerpAPI | $11.25 | $135 | 5% |
| Firecrawl | $12.50 | $150 | 6% |
| Claude | $187.50 | $2,250 | 89% |
| **Total** | **$211.25** | **$2,535** | **100%** |

**Insight**: Claude is 89% of cost → optimize LLM classification for biggest savings

═══════════════════════════════════════════════════════════════

## Cost Sensitivity Analysis

### Variable 1: Number of Cities

| Cities | Pages | SerpAPI | Firecrawl | Claude | Total |
|--------|-------|---------|-----------|--------|-------|
| 10 | 2,500 | $0.45 | $0.50 | $7.50 | $8.45 |
| 50 | 12,500 | $2.25 | $2.50 | $37.50 | $42.25 |
| 100 | 25,000 | $4.50 | $5.00 | $75.00 | $84.50 |
| 250 | 62,500 | $11.25 | $12.50 | $187.50 | $211.25 |
| 500 | 125,000 | $22.50 | $25.00 | $375.00 | $422.50 |

**Takeaway**: **Linear scaling** (double cities = double cost)

### Variable 2: Results per City

| Results | Pages/City | SerpAPI | Firecrawl | Claude | Total |
|---------|-----------|---------|-----------|--------|-------|
| 50 | 50 | $0.015 | $0.01 | $0.15 | $0.175 |
| 100 | 100 | $0.015 | $0.02 | $0.30 | $0.335 |
| 250 | 250 | $0.045 | $0.05 | $0.75 | $0.845 |
| 500 | 500 | $0.075 | $0.10 | $1.50 | $1.675 |
| 1000 | 1000 | $0.150 | $0.20 | $3.00 | $3.350 |

**Per city cost** at 250 results: **$0.845**
**Total** (250 cities): **$0.845 × 250 = $211.25** ✓

### Variable 3: Filtering Strategy

| Strategy | Pages Scraped | Scrape Cost | Claude Cost | Total | Savings |
|----------|---------------|-------------|-------------|-------|---------|
| No filter | 62,500 | $12.50 | $187.50 | $211.25 | - |
| Domain filter | 50,000 | $10.00 | $150.00 | $171.25 | $40 |
| Top 150 only | 37,500 | $7.50 | $112.50 | $131.25 | $80 |
| Top 100 only | 25,000 | $5.00 | $75.00 | $91.25 | $120 |

**Takeaway**: **Filtering = Major savings** ($40-120 per run)

═══════════════════════════════════════════════════════════════

## Recommendations

### For Testing Phase (10-city pilot)
```
Cities: 10
Results: 100 per city
Total pages: 1,000

Cost: ~$8.50
Time: ~30 minutes
Purpose: Validate pipeline works end-to-end
```

### For Production Phase (250 cities)
```
Cities: 250
Results: 250 per city (with filtering → 150 scraped)
Total pages: 37,500

Cost: ~$131 (with optimization)
Time: ~4-5 hours
Purpose: Full Spain coverage
```

### Optimization Priorities
1. **Filter aggregator domains** before scraping (-$40)
2. **Deduplicate domains** before scraping (-$30)
3. **Keep top 150 results per city** only (-$50)
4. **Total savings**: **~$120** ($211 → $91)

═══════════════════════════════════════════════════════════════

## Cost Tracking Template

```python
# Track costs in logs
cost_log = {
    'run_id': 'batch_20251104_180000',
    'timestamp': '2025-11-04T18:00:00Z',
    'cities_processed': 250,
    'total_pages': 62500,
    'costs': {
        'serpapi': {
            'searches': 750,
            'cost': 11.25
        },
        'firecrawl': {
            'scrapes': 62500,
            'credits': 12500,
            'cost': 12.50
        },
        'claude': {
            'pages': 62500,
            'tokens_in': 125000000,  # 2K per page
            'tokens_out': 12500000,  # 200 per page
            'cost': 187.50
        }
    },
    'total_cost': 211.25,
    'cost_per_city': 0.845,
    'cost_per_page': 0.00338
}
```

═══════════════════════════════════════════════════════════════

**Summary**: SerpAPI migration enables **2.5x more results** for **2.6x cost** = **Excellent ROI**

**Recommended**: **Scenario B (250 results/city) with filtering** → **~$131 total**

═══════════════════════════════════════════════════════════════
