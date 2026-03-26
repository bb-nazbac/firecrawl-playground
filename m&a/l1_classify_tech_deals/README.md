# L1: Classify Tech Deals

**Layer**: L1 (Independent — no dependencies on other script outputs)
**Input**: `full_data.csv` (411,768 M&A deals from SDC/Refinitiv)
**Output**: `outputs/all_deals_classified.csv`, `outputs/tech_deals_only.csv`

## Purpose

Classify all 411K M&A deals as technology-related or not using LLM batch classification.
This is a WIDE NET filter — catches all tech companies (software, hardware, biotech,
fintech, cybersecurity, etc.) so that downstream research can determine more specific
categories like AI/ML.

## How It Works

```
┌─────────────────────────────────────────────────────────┐
│  full_data.csv (411K rows x 62 cols)                    │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│  Extract 4 classify columns per row:                    │
│  - Target Full Name                                     │
│  - Target Primary SIC                                   │
│  - Target Mid Industry                                  │
│  - Target Macro Industry                                │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│  Batch 10 rows per API call -> gpt-5-mini               │
│  "Is this a TECHNOLOGY company?"                        │
│  Returns: is_tech, tech_category, confidence            │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│  Checkpoint (JSONL) -> Merge with full CSV              │
│  Output: all_deals_classified.csv + tech_deals_only.csv │
└─────────────────────────────────────────────────────────┘
```

## Usage

```bash
# Test on first 10K rows
python classify_deals.py --test 10000

# Resume interrupted run
python classify_deals.py --test 10000 --resume

# Full run (all 411K)
python classify_deals.py

# Just merge existing checkpoint (skip API calls)
python classify_deals.py --merge-only

# Custom concurrency / model
python classify_deals.py --concurrency 20 --model gpt-5-mini
```

## Cost Estimates

| Scope | Batches | Est. Cost |
|-------|---------|-----------|
| 10K test | 1,000 | ~$0.50 |
| Full 411K | 41,100 | ~$20 |

## Output Schema

Added columns to input CSV:
- `is_tech`: "true" / "false" / "error"
- `tech_category`: Technology sub-field (e.g., "Software", "Semiconductors", "Fintech", "Biotech")
- `tech_confidence`: "high" / "medium" / "low"
