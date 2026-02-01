# L1 Map Layer

## Purpose

Map a company domain to discover all available pages using Firecrawl's `/v2/map` endpoint.

## Usage

```bash
# Single domain
python map_domain.py acme-chemicals.com

# From file (text - one domain per line)
python map_domain.py --input ../inputs/domains.txt

# From file (JSON)
python map_domain.py --input ../inputs/domains.json

# With options
python map_domain.py --limit 1000 --delay 2000 acme-chemicals.com
```

## Input Formats

**Text file** (domains.txt):
```
acme-chemicals.com
bigcorp-wholesale.net
example-distributor.com
```

**JSON file** (domains.json):
```json
[
  {"domain": "acme-chemicals.com", "company_name": "Acme Chemicals"},
  {"domain": "bigcorp-wholesale.net", "company_name": "BigCorp Wholesale"}
]
```

## Output

Each domain produces a JSON file in `../outputs/map_results/`:

```json
{
  "success": true,
  "domain": "acme-chemicals.com",
  "url": "https://acme-chemicals.com",
  "timestamp": "2025-12-14T10:30:00.000Z",
  "duration_ms": 2500,
  "stats": {
    "total_discovered": 1500,
    "after_language_filter": 1200,
    "final_count": 1100,
    "filtered_non_english": 300,
    "filtered_variants": 100
  },
  "links": [
    "https://acme-chemicals.com/",
    "https://acme-chemicals.com/about",
    "https://acme-chemicals.com/products",
    "..."
  ]
}
```

## Language Filtering

The script automatically filters:
1. **Non-English pages**: `/de/`, `/fr/`, `/es/`, `/ja/`, etc.
2. **English variants**: Prefers `/en-us/`, falls back to `/en-gb/`, drops others

## Cost

- 1 Firecrawl credit per domain (regardless of URL count)
