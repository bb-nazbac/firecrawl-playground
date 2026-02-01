# Search System - Domain Discovery

**Status**: Production Ready ✓
**Last Updated**: 2025-01-21

Simple search pipeline that discovers businesses across cities and outputs `domains.csv` for the qualifying pipeline.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ SEARCH SYSTEM                                               │
│ "Find businesses by searching cities"                       │
│                                                             │
│ Input:  Query + Cities (YAML config)                        │
│ Output: domains.csv (unique domains with metadata)          │
│                                                             │
│ L1: Search (Serper.dev) → Extract domains → Dedupe → CSV    │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼ domains.csv
┌─────────────────────────────────────────────────────────────┐
│ QUALIFYING SYSTEM (qualifying_agentic_system_prod)          │
│                                                             │
│ Scrapes, classifies, and qualifies the discovered domains   │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

```bash
# 1. Create a run config
cp configs/runs/TEMPLATE.yaml configs/runs/my_search.yaml
# Edit my_search.yaml with your query and cities

# 2. Run the search
python run_search.py my_search

# 3. Output is ready for qualifying pipeline
# outputs/{client}/{run_id}/domains.csv
```

## Run Config Format

```yaml
# configs/runs/my_search.yaml

client: acme_corp

search:
  query: "food distributors in {city}"
  cities:
    - Little Rock, Arkansas, United States
    - Fort Smith, Arkansas, United States
    - Fayetteville, Arkansas, United States
  results_per_city: 50
  gl: us  # Country code (optional, default: us)

# Optional
test_mode: 3  # Only process first N cities (for testing)
max_cost_usd: 50  # Cost limit warning
```

## Output

```
outputs/{client}/{run_id}/
├── domains.csv             # Main output - unique domains
├── l1_search_results.json  # Raw search results (for debugging)
├── progress.json           # Run progress
├── costs.json              # Cost breakdown
├── diagnostics_l1.json     # Search diagnostics
└── run.log                 # Execution log
```

### domains.csv Columns

| Column | Description |
|--------|-------------|
| domain | Extracted domain (e.g., `example.com`) |
| url | Full URL from search results |
| city | City this result came from |
| title | Page title from search |
| snippet | Search snippet |
| position | Search result position |
| query | Search query used |

## Usage Examples

### Basic Search
```bash
python run_search.py burnt_arkansas_food_distributors
```

### Dry Run (validate config)
```bash
python run_search.py burnt_arkansas_food_distributors --dry-run
```

### Feed to Qualifying Pipeline
```bash
# After search completes:
python ../qualifying_agentic_system_prod/core/pipeline.py \
  outputs/burnt/run_20250121_120000/domains.csv \
  --client burnt \
  --spec food_distributor_qualification
```

## Cost

- **Serper.dev**: ~$0.001 per search query
- **50 results/city × 5 cities**: ~$0.025 total (25 queries)

## Directory Structure

```
search_system_prod/
├── run_search.py           # Main entry point
├── core/
│   ├── layer_search.py     # Serper search implementation
│   ├── config_loader.py    # YAML config loader
│   ├── cost_tracker.py     # Cost tracking
│   ├── diagnostics.py      # Layer diagnostics
│   └── progress_tracker.py # Progress tracking
├── configs/
│   └── runs/               # Run configuration files
│       └── *.yaml
└── outputs/                # Output directory
    └── {client}/
        └── {run_id}/
            └── domains.csv
```

## Environment Variables

Required in `.env` (parent directory):
```bash
SERP_API_KEY=your_serper_api_key
```

## Migration from Old System

The old 5-layer pipeline (Search→Scrape→Classify→Export→Dedupe) has been split:

| Old System | New System |
|------------|------------|
| `run_pipeline.py` with 5 layers | `run_search.py` (search only) |
| Self-contained classification | Separate qualifying pipeline |
| Complex streaming queues | Simple sequential execution |
| All-in-one output | `domains.csv` feeds into qualifying |

The old `run_pipeline.py` is still present for reference but deprecated.
Use `run_search.py` for new searches.
