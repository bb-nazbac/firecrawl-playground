# Round 06 Inputs Manifest

This document tracks all external dependencies and inputs for Round 06.

## External APIs

### Serper.dev (L1 Search)
- **Endpoint:** `https://google.serper.dev/search`
- **Auth:** API key via `X-API-KEY` header
- **ENV Variable:** `SERP_API_KEY`
- **Rate Limit:** 300 QPS (Ultimate tier)
- **Cost:** $0.001 per search (10 results)
- **Docs:** See `SERPER_DEV_API_REFERENCE.md`

### Firecrawl (L2 Scrape)
- **Endpoint:** `https://api.firecrawl.dev/v2/scrape`
- **Auth:** Bearer token via `Authorization` header
- **ENV Variable:** `FIRECRAWL_API_KEY`
- **Rate Limit:** 50 concurrent browsers, 500 requests/min
- **Cost:** $0.001 per scrape (~1 credit)
- **Docs:** https://docs.firecrawl.dev

### Claude API (L3 Classify)
- **Endpoint:** `https://api.anthropic.com/v1/messages`
- **Auth:** API key via `x-api-key` header
- **ENV Variable:** `ANTHROPIC_API_KEY`
- **Model:** `claude-sonnet-4-5-20250929`
- **Rate Limit:** 50 RPM, 30k tokens/min
- **Cost:** $3/MTok input, $15/MTok output
- **Docs:** https://docs.anthropic.com

## Environment File

Location: `/Users/bahaa/Documents/Clients/firecrawl_playground/.env`

Required variables:
```bash
SERP_API_KEY=your_serper_api_key
FIRECRAWL_API_KEY=your_firecrawl_api_key
ANTHROPIC_API_KEY=your_anthropic_api_key
```

## Python Dependencies

From `requirements.txt` (project root):
```
requests>=2.31.0
python-dotenv>=1.0.0
```

Standard library (no install required):
```
concurrent.futures
threading
json
os
time
datetime
```

## Input Files

### L1 → L2 Flow
- **Input:** None (takes query as CLI argument)
- **Output:** `outputs/l1_search_*.json`

### L2 → L3 Flow
- **Input:** `outputs/l1_search_*.json` (from L1)
- **Output:** `outputs/l2_scraped_*.json`

### L3 → Final Flow
- **Input:** `outputs/l2_scraped_*.json` (from L2)
- **Output:** `outputs/l3_classified_*.json`

## Client Folder Structure

Outputs are saved to both:
1. Round outputs: `testing_and_learning/round_06_serpapi_testing/outputs/`
2. Client outputs: `search_system/client_outputs/{client}/outputs/l{n}_*/`

Client structure:
```
search_system/client_outputs/fuse/
├── outputs/
│   ├── l1_search/
│   │   └── l1_search_*.json
│   ├── l2_scrape/
│   │   └── l2_scraped_*.json
│   └── l3_classify/
│       └── l3_classified_*.json
```

## Test Data

**Test Query:** "Neurology clinics in Los Angeles"
- **Location:** Los Angeles, California, United States
- **Country:** us
- **Language:** en
- **Target Results:** 250
- **Actual Results:** 210 (Google limit)

## Dependencies from Other Rounds

None - Round 06 is self-contained.

## Known External Blocks

The following sites block Firecrawl scraping (expected behavior):
- Yelp (HTTP 403)
- Facebook (HTTP 403)
- YouTube (HTTP 500)
- ZocDoc (HTTP 500)

These are not errors - they're anti-bot protections.

## Version Compatibility

**Tested on:**
- Python: 3.9
- OS: macOS 14.3.0 (Darwin)
- urllib3: 2.x (with OpenSSL warning - non-blocking)

**API Versions:**
- Serper.dev: v1 (stable)
- Firecrawl: v2 (latest)
- Claude: 2023-06-01 (stable)

## Security Notes

- **Never commit `.env` file** (contains API keys)
- API keys are loaded from `.env` via `python-dotenv`
- All API keys should be kept secret
- Rotate keys if exposed

## Cost Tracking

Per test run (200 pages):
- L1: $0.021 (210 searches @ $0.001/10)
- L2: $0.210 (210 scrapes @ $0.001 each)
- L3: $4.084 (200 classifications, ~6k tokens avg)
- **Total:** ~$4.30 per 200-page test

## Rate Limits Summary

| Service | Concurrency | RPM | Notes |
|---------|-------------|-----|-------|
| Serper.dev | 300 QPS | - | Can handle high concurrency |
| Firecrawl | 50 browsers | 500 | Use 50 concurrent threads max |
| Claude | 30 safe | 50 RPM | Token limit: 30k/min |

## Dependency Health

✅ All APIs operational as of 2025-11-05
✅ All rate limits tested and confirmed
✅ All costs verified and documented
✅ All auth methods working
