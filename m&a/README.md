# M&A Technology Deal Classification Pipeline

Identifies technology-related M&A transactions from a dataset of 411,768 deals (SDC/Refinitiv).
Tech classification is the first wide-net filter; downstream research determines specific
sub-categories (AI/ML, fintech, cybersecurity, etc.).

## Problem

SIC/NAIC codes are too coarse to reliably categorize modern technology companies.
Many tech companies are classified by application domain rather than technology:
- Healthcare AI → "Healthcare Equipment" SIC
- Self-driving cars → "Automobiles" SIC
- Fintech → "Financial Services" SIC

LLM classification provides the most reliable wide-net filter for technology deals.

## Pipeline Architecture

```
┌─────────────────────────────────────────────────────────┐
│  m&a/                                                   │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  full_data.csv ─────→ L1: classify_deals.py             │
│  (411K deals)         (gpt-5-mini, batch 10/call)       │
│                              │                          │
│                              ▼                          │
│                       outputs/                          │
│                       ├── all_deals_classified.csv      │
│                       ├── tech_deals_only.csv           │
│                       └── classify_stats.json           │
│                                                         │
│  inputs/              logs/                             │
│  └── INPUTS_MANIFEST  └── l1_classify_tech_deals/       │
│                                                         │
│  L2+ (planned): research pipeline on tech deals         │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

## Quick Start

```bash
# Set API key
export OPENAI_API_KEY="sk-..."

# Test on 10K rows first
python l1_classify_tech_deals/classify_deals.py --test 10000

# Full run (all 411K, ~$20, ~2-3 hours)
python l1_classify_tech_deals/classify_deals.py
```

## Directory Structure

```
m&a/
├── full_data.csv                    # Source: 411K deals (768MB)
├── full data download.xlsx          # Original XLSX (159MB)
├── inputs/
│   └── INPUTS_MANIFEST.md          # Dependency documentation
├── l1_classify_tech_deals/
│   ├── classify_deals.py            # Main classification script
│   └── README.md                    # Layer documentation
├── outputs/                         # Classification results
│   └── .checkpoints/               # Resume state (JSONL)
├── logs/
│   └── l1_classify_tech_deals/      # Timestamped execution logs
├── learnings.md                     # Experimental findings
├── CHANGELOG.md                     # Version history
└── README.md                        # This file
```
