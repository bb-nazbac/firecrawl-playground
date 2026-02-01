# Round 05: SerpAPI Integration

**Date**: 2025-11-04
**Status**: 🚧 In Progress
**Lead**: OPTIMUS PRIME Unit OP-2025-1104-SERPAPI-MIGRATION

═══════════════════════════════════════════════════════════════

## Overview

**Mission**: Migrate discovery pipeline from Firecrawl /search (100-result hard limit, no pagination) to SerpAPI (unlimited pagination, deep search capability).

**Problem Statement**:
- Round 02 discovered Firecrawl v2 /search API has hard limit of 100 results per query
- Round 02 confirmed NO pagination support (offset, page, skip all rejected with HTTP 400)
- User requires 250+ results per city for comprehensive coverage
- 250 cities × 100 results = 25,000 pages (insufficient for business needs)

**Solution**:
Replace Firecrawl /search (L1) with SerpAPI, while maintaining:
- ✅ Firecrawl /scrape (L2) - Unchanged
- ✅ LLM classification (L3) - Unchanged

**Business Outcome**:
Enable retrieval of 250+ dental clinic results per Spanish city via pagination, achieving comprehensive national coverage (~60,000+ pages vs. previous 25,000 limit).

═══════════════════════════════════════════════════════════════

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  NEW PIPELINE: SerpAPI → Firecrawl Scrape → LLM Analysis   │
└─────────────────────────────────────────────────────────────┘
             │
             ├─→ L1: SerpAPI Search (NEW - replaces Firecrawl search)
             │   ├─ Input: City name + query template
             │   ├─ Process: Paginate Google results via start parameter
             │   ├─ Output: JSON with URLs, titles, snippets
             │   └─ Cost: 1 SerpAPI credit per page (100 results)
             │
             ├─→ L2: Firecrawl Homepage Scrape (UNCHANGED)
             │   ├─ Input: URLs from L1
             │   ├─ Process: Scrape each URL for full content
             │   ├─ Output: JSON with markdown, links, metadata
             │   └─ Cost: ~1 Firecrawl credit per page
             │
             └─→ L3: LLM Classification (UNCHANGED)
                 ├─ Input: Scraped content from L2
                 ├─ Process: Claude classifies (clinic vs directory)
                 ├─ Output: Classified pages with extracted data
                 └─ Cost: ~$0.003 per page
```

**Key Change**: L1 only (search layer)

═══════════════════════════════════════════════════════════════

## Why SerpAPI?

**Critical Advantages Over Firecrawl /search**:
1. ✅ **Pagination Support**: Unlimited via `start` parameter (0, 100, 200, 300...)
2. ✅ **Deep Search**: Access 500+ results per query (Google limit ~1000)
3. ✅ **Cost Efficient**: 1 credit per search (regardless of num=10 or num=100)
4. ✅ **Proven Reliability**: Handles CAPTCHA, proxying, browser simulation
5. ✅ **Same Output Format**: JSON with links, titles, descriptions

**Comparison**:

| Feature | Firecrawl /search | SerpAPI |
|---------|-------------------|---------|
| Max results per call | 100 | 100 |
| Pagination | ❌ NO | ✅ YES (via start) |
| Max total results | 100 | ~1000 (Google limit) |
| Cost per call | 1 credit | 1 credit |
| Returns scraped content | ✅ YES (scrapeOptions) | ❌ NO (must scrape separately) |

**Trade-off**: SerpAPI requires separate scraping step (via Firecrawl /scrape), but enables 10x more results.

═══════════════════════════════════════════════════════════════

## Round Structure

```
/round_05_serpapi_integration
    /inputs
        INPUTS_MANIFEST.md          # No dependencies (L1 layer)
    /outputs
        test_serpapi_madrid.json    # Test outputs
    /logs
        /l1_serpapi_search
            test_search_*.log       # Execution logs
    /l1_serpapi_search
        test_serpapi.py             # Test script
        search_with_pagination.py   # Pagination demo
        README.md                   # L1 documentation
    learnings.md                    # 4-section experimental findings
    API_REFERENCE.md                # Complete SerpAPI documentation
    MIGRATION_GUIDE.md              # How to migrate from Firecrawl
    COST_MODEL.md                   # Detailed cost analysis
    README.md                       # This file
```

═══════════════════════════════════════════════════════════════

## Documentation Files

1. **API_REFERENCE.md** - Complete SerpAPI documentation
   - All parameters (q, num, start, gl, hl, etc.)
   - Pagination mechanism (serpapi_pagination.next)
   - Response structure (organic_results)
   - Authentication (api_key)
   - Examples (Python, cURL, Node.js)

2. **MIGRATION_GUIDE.md** - How to migrate existing scripts
   - Side-by-side comparison (old vs new)
   - Step-by-step migration process
   - Testing checklist
   - Rollback strategy

3. **COST_MODEL.md** - Cost analysis and budgeting
   - SerpAPI pricing tiers
   - Cost per city at different depths
   - Full 250-city cost projections
   - Cost optimization strategies

═══════════════════════════════════════════════════════════════

## Quick Start

### Test SerpAPI Search (Single Query)
```bash
cd l1_serpapi_search
python3 test_serpapi.py "clínica dental Madrid" 10
```

### Test Pagination (Multiple Pages)
```bash
python3 search_with_pagination.py "clínica dental Madrid" 250
```

### Expected Output
```json
{
  "metadata": {
    "query": "clínica dental Madrid",
    "total_results": 250,
    "pages_fetched": 3,
    "credits_used": 3
  },
  "results": [
    {
      "position": 1,
      "title": "Clínica Dental en Madrid - Dentistas Orion Dental",
      "link": "https://www.clinicadentalorion.com/",
      "snippet": "Orión Dental, es una clínica dental en Madrid...",
      "page": 1
    },
    ...
  ]
}
```

═══════════════════════════════════════════════════════════════

## Success Metrics

- [ ] Complete API documentation created
- [ ] Working test scripts with pagination
- [ ] Cost model documented and validated
- [ ] Migration guide tested with sample city
- [ ] Ready for production batch implementation (Round 06)

═══════════════════════════════════════════════════════════════

## Next Steps (Round 06)

After this round completes:
1. Implement production batch script (250 cities × 250 results)
2. Integrate with existing L2 (Firecrawl scrape) and L3 (LLM classify)
3. Run 10-city pilot test
4. Execute full 250-city production run

═══════════════════════════════════════════════════════════════
