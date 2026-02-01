# Qualifying Agentic System - Production

```
 ██████╗ ██╗   ██╗ █████╗ ██╗     ██╗███████╗██╗   ██╗██╗███╗   ██╗ ██████╗
██╔═══██╗██║   ██║██╔══██╗██║     ██║██╔════╝╚██╗ ██╔╝██║████╗  ██║██╔════╝
██║   ██║██║   ██║███████║██║     ██║█████╗   ╚████╔╝ ██║██╔██╗ ██║██║  ███╗
██║▄▄ ██║██║   ██║██╔══██║██║     ██║██╔══╝    ╚██╔╝  ██║██║╚██╗██║██║   ██║
╚██████╔╝╚██████╔╝██║  ██║███████╗██║██║        ██║   ██║██║ ╚████║╚██████╔╝
 ╚══▀▀═╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝╚═╝╚═╝        ╚═╝   ╚═╝╚═╝  ╚═══╝ ╚═════╝

 █████╗  ██████╗ ███████╗███╗   ██╗████████╗██╗ ██████╗
██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝██║██╔════╝
███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║   ██║██║
██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║   ██║██║
██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║   ██║╚██████╗
╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝   ╚═╝ ╚═════╝
```

## Purpose

Intelligent, iterative company qualification system optimized for scale:
1. **Scrapes homepage first** (1 credit)
2. **Uses Claude to check if sufficient** - if YES, done!
3. **Only maps site if needed** - saves credits and avoids rate limits
4. **Iteratively scrapes additional pages** (max 10 more)
5. **Exports qualification results** to CSV/JSON

## Architecture (Optimized)

```
┌─────────────────────────────────────────────────────────────┐
│  L1: HOMEPAGE SCRAPE + INITIAL CHECK                        │
│  Input: Domain → Firecrawl /v2/scrape (homepage only)       │
│  Claude: Is homepage sufficient?                            │
│  Cost: 1 credit per domain                                  │
│                                                             │
│  ✅ If YES → Skip to L3 (Export) - FAST PATH               │
│  ⚠️  If NO  → Continue to L2                                │
└─────────────────────────────────────────────────────────────┘
                           │
              ┌────────────┴────────────┐
              │ SUFFICIENT              │ INSUFFICIENT
              ▼                         ▼
┌──────────────────────┐  ┌─────────────────────────────────────┐
│  L3: EXPORT          │  │  L2: MAP + ITERATIVE QUALIFICATION  │
│  (Fast path - done!) │  │  Firecrawl /v2/map → site structure │
│  ~1 credit           │  │  Claude selects pages → scrape      │
└──────────────────────┘  │  Iterate until sufficient (max 10)  │
                          │  Cost: 2-12 credits                  │
                          └─────────────────────────────────────┘
                                         │
                                         ▼
                          ┌─────────────────────────────────────┐
                          │  L3: EXPORT                         │
                          │  CSV + JSON output                  │
                          └─────────────────────────────────────┘
```

## Why This Architecture?

| Metric | Old (Map First) | New (Homepage First) |
|--------|-----------------|----------------------|
| /map calls | 100% of domains | Only ~30-50% |
| Rate limit pressure | HIGH | LOW |
| Avg credits/domain | ~6-7 | ~2-4 |
| Speed | Bottlenecked on /map | Much faster |

**Key Insight**: Many companies have enough information on their homepage.
By checking homepage first, we skip the expensive /map call for 50%+ of domains.

## Directory Structure

```
qualifying_agentic_system_prod/
├── core/
│   ├── pipeline.py           # Main orchestrator (NEW)
│   ├── layer_homepage.py     # L1: Homepage scrape + check (NEW)
│   ├── layer_map_iterate.py  # L2: Map + iterate (NEW)
│   ├── batch_runner.py       # Legacy batch runner
│   ├── cost_tracker.py       # API cost tracking
│   ├── progress_tracker.py   # Real-time progress
│   └── diagnostics.py        # Detailed diagnostics
│
├── inputs/                   # Input CSV files
├── outputs/                  # Results by run
├── testing/                  # R&D rounds
│
└── README.md
```

## Quick Start

```bash
# 1. Set environment variables
export FIRECRAWL_API_KEY="fc-xxx"
export ANTHROPIC_API_KEY="sk-ant-xxx"

# 2. Test single domain
python core/pipeline.py example.com

# 3. Batch process CSV
python core/pipeline.py domains.csv --limit 100 --concurrency 30

# 4. Full run with custom output
python core/pipeline.py domains.csv -o outputs/my_run -c 50 --max-pages 11
```

## CLI Options

```
usage: pipeline.py [-h] [--output OUTPUT] [--limit LIMIT]
                   [--concurrency CONCURRENCY] [--max-pages MAX_PAGES]
                   [--model MODEL] input

positional arguments:
  input                 Input CSV file with domains OR single domain

optional arguments:
  --output, -o          Output directory
  --limit, -n           Limit number of domains
  --concurrency, -c     Concurrent workers (default: 30)
  --max-pages           Max pages per domain (default: 11)
  --model               Claude model (default: claude-sonnet-4-20250514)
```

## Cost Model (per company)

| Scenario | Path | Credits | Est. % of Companies |
|----------|------|---------|---------------------|
| Homepage sufficient | L1 only | 1 | ~50-60% |
| Need 1 iteration | L1 + L2 | 3-7 | ~30-40% |
| Need 2 iterations | L1 + L2 | 7-12 | ~10-15% |

**For 100,000 companies (estimated):**
- Best case (60% HP sufficient): ~200k credits
- Average case: ~350k credits
- Worst case: ~600k credits

## Output Format

### JSON
```json
{
  "domain": "example.com",
  "success": true,
  "path": "homepage_only",
  "classification": "QUALIFIED",
  "answers": {
    "sells_products": "yes",
    "product_type": "Industrial equipment",
    "primary_category": "Manufacturing",
    "target_market": "B2B",
    "company_size": "enterprise"
  },
  "confidence": {
    "sells_products": "HIGH",
    "product_type": "HIGH",
    "primary_category": "HIGH",
    "target_market": "MEDIUM",
    "company_size": "MEDIUM"
  },
  "pages_scraped": 1,
  "map_used": false,
  "credits_used": 1,
  "duration_ms": 3500
}
```

### CSV
| domain | success | path | classification | pages_scraped | map_used | credits_used |
|--------|---------|------|----------------|---------------|----------|--------------|
| example.com | true | homepage_only | QUALIFIED | 1 | false | 1 |
| other.com | true | homepage_plus_iterate | QUALIFIED | 6 | true | 7 |

## Testing Status

| Round | Focus | Status |
|-------|-------|--------|
| 01 | Map + Homepage qualification | COMPLETE |
| 02 | MAP rate limit testing | COMPLETE |
| 03 | Optimized pipeline testing | PENDING |

---

*OPTIMUS PRIME Protocol v2.0 - 95% Confidence Required*
