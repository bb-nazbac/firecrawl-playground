# Search System - Production Pipeline

**Version**: 1.0 (from Round 06)
**Status**: ✅ Production Ready
**Architecture**: Multi-Tenant, Spec-Driven Classification

---

## Overview

Production-grade multi-tenant lead generation pipeline with geo-targeted search, concurrent scraping, LLM classification, and filtered CSV export.

**Pipeline**: L1 Search (Serper.dev) → L2 Scrape (Firecrawl) → L3 Classify (Claude) → L4 Export (CSV) → L5 Domain Dedup

---

## Quick Start

### Run Full Pipeline for Client

```bash
python3 main.py \
  --client=fuse \
  --spec=spec_v2_hospital_university \
  --skip-l1 \
  --skip-l2
```

### Run Individual Layers

```bash
# L1: Search (Serper.dev)
cd l1_serpapi_search
python3 search_batch.py

# L2: Scrape (Firecrawl)
cd l2_firecrawl_scrape
python3 scrape_batch_logged.py

# L3: Classify (Claude + Spec)
cd l3_llm_classify
python3 classify_with_spec.py \
  --client=fuse \
  --spec=spec_v2_hospital_university \
  --concurrency=30

# L4: Export to CSV
cd l4_csv_export
python3 export_with_client.py \
  --client=fuse \
  --filter=independent

# L5: Domain Deduplication
cd l5_domain_dedup
python3 deduplicate_domains.py \
  --client=fuse \
  --filter=independent
```

---

## Architecture

```
/search_system/  (PRODUCTION)
    main.py                    ← Pipeline orchestrator

    /l1_serpapi_search/        ← L1: Geo-targeted search
        search_batch.py

    /l2_firecrawl_scrape/      ← L2: Concurrent scraping
        scrape_batch_logged.py

    /l3_llm_classify/          ← L3: Spec-driven LLM classification
        classify_with_spec.py
        /specs/
            /fuse/
                spec_v2_hospital_university.json
            /{client_name}/    ← Add new clients here

    /l4_csv_export/            ← L4: Filtered CSV export
        export_with_client.py

    /l5_domain_dedup/          ← L5: Domain normalization & deduplication
        deduplicate_domains.py

    /outputs/                  ← L1/L2 outputs (centralized)
        l1_search_*.json
        l2_scraped_*.json

    /logs/                     ← Execution logs by layer
        /l1_serpapi_search/
        /l2_firecrawl_scrape/
        /l3_llm_classify/
        /l4_csv_export/
        /l5_domain_dedup/
```

**Note**: L3, L4, and L5 outputs are client-specific:
- L3: `/l3_llm_classify/outputs/{client}/`
- L4: `/l4_csv_export/outputs/{client}/`
- L5: `/l5_domain_dedup/outputs/{client}/`

---

## Adding a New Client

### 1. Create Client Spec

```bash
mkdir -p l3_llm_classify/specs/new_client
```

Copy and modify existing spec:
```bash
cp l3_llm_classify/specs/fuse/spec_v2_hospital_university.json \
   l3_llm_classify/specs/new_client/spec_v1_custom.json
```

Edit spec fields:
- `client`: "new_client"
- `classification_task.categories`: Update classification categories
- `extraction_rules`: Define fields to extract
- `additional_questions`: Add custom questions

### 2. Run Pipeline

```bash
python3 main.py \
  --client=new_client \
  --spec=spec_v1_custom \
  --skip-l1 \
  --skip-l2
```

Client folders will be auto-created:
- `/l3_llm_classify/outputs/new_client/`
- `/l4_csv_export/outputs/new_client/`

---

## Data Flow

| Layer | Input | Output | Pattern |
|-------|-------|--------|---------|
| **L1** | External API (Serper.dev) | `/outputs/` | `l1_search_*.json` |
| **L2** | `/outputs/l1_search_*.json` | `/outputs/` | `l2_scraped_*.json` |
| **L3** | `/outputs/l2_scraped_*.json` | `/l3_llm_classify/outputs/{client}/` | `l3_classified_*.json` |
| **L4** | `/l3_llm_classify/outputs/{client}/` | `/l4_csv_export/outputs/{client}/` | `{filter}_clinics_*.csv` |
| **L5** | `/l4_csv_export/outputs/{client}/` | `/l5_domain_dedup/outputs/{client}/` | `{filter}_clinics_deduped_*.csv` |

---

## Production Results (Fuse - 12 Cities)

**Run Date**: 2025-11-07

| Metric | Value |
|--------|-------|
| Cities Searched | 12 (Boston, DC, Houston, Miami, San Diego, SF, Albuquerque, Philadelphia, Austin, Phoenix, San Jose, Denver) |
| L1 URLs Found | 2,993 |
| L2 Pages Scraped | 2,862 (95.6% success) |
| L3 Clinics Classified | 949 (32.2% of scraped) |
| L4 Independent Clinics | 549 (57.9% of clinics) |
| L5 Unique Domains | 222 (56.0% deduplication rate) |
| Total Time | ~3 hours (L1: 7min, L2: 2hr, L3: 30min, L4: <1min, L5: <1min) |
| Total Cost | ~$15 ($0.30 search + $2.86 scrape + ~$12 classify) |

**Classification Breakdown**:
- Individual Clinics: 267 (28.1%)
- Group Practices: 682 (71.9%)
- Directory Pages: 322
- Other: 1,672
- Errors: 3

**Hospital/University Filtering**:
- Independent (neither): 549 ✅ Exported
- Hospital only: 140
- University only: 50
- Both hospital & university: 210

---

## L4 Export Filters

```bash
# Independent clinics (neither hospital nor university)
python3 export_with_client.py --client=fuse --filter=independent

# All clinics
python3 export_with_client.py --client=fuse --filter=all

# Hospital-affiliated only
python3 export_with_client.py --client=fuse --filter=hospital

# University-affiliated only
python3 export_with_client.py --client=fuse --filter=university
```

---

## L5 Domain Deduplication

**Purpose**: Normalize domains and remove duplicates from L4 CSV exports.

**Normalization Rules**:
- Remove protocol (`https://`, `http://`)
- Keep subdomains (`www.mayo.com`, `blog.mayo.com`)
- Remove paths, query params, fragments
- Remove port numbers
- Lowercase all domains

**Example**:
```
https://www.Mayo.com/clinic?x=1  →  www.mayo.com
http://blog.mayo.com/path        →  blog.mayo.com
```

**Usage**:
```bash
cd l5_domain_dedup
python3 deduplicate_domains.py --client=fuse --filter=independent
```

**Output**:
- Adds `domain_normalized` column to CSV
- Keeps first occurrence of each unique domain
- Typical deduplication rate: ~50-60%
- Preserves all original columns

---

## Environment Variables

Required in `../../.env`:

```bash
# Serper.dev (L1 Search)
SERP_API_KEY=your_serper_api_key

# Firecrawl (L2 Scrape)
FIRECRAWL_API_KEY=your_firecrawl_api_key

# Anthropic (L3 Classify)
ANTHROPIC_API_KEY=your_anthropic_api_key
```

---

## Logs

All execution logs stored in `/logs/{layer}/`:
- Timestamped log files
- Console output captured
- Performance metrics
- Error traces

Example: `/logs/l3_llm_classify/classify_fuse_2025-11-07_10-29-34.log`

---

## Spec File Format

See `CLIENT_SPEC_ARCHITECTURE.md` for full documentation.

**Example Spec Structure**:
```json
{
  "client": "fuse",
  "spec_version": "v2",
  "classification_task": {
    "domain": "neurology clinics",
    "categories": [...]
  },
  "extraction_rules": {...},
  "additional_questions": [...],
  "api_settings": {
    "model": "claude-sonnet-4-5-20250929",
    "max_tokens": 1000,
    "temperature": 0
  }
}
```

---

## Testing Reference

This production system was validated in:
- **Testing Location**: `/testing_and_learning/round_06_serpapi_testing/`
- **Confidence**: 95%+ (meets OPTIMUS PRIME standards)
- **Test Results**: See Round 06 learnings.md

---

## Support

- **Architecture Documentation**: `CLIENT_SPEC_ARCHITECTURE.md`
- **Scaling Plan**: `PRODUCTION_SCALING_PLAN.md`
- **Commandments Compliance**: COMMANDMENTS.yml (in docs/)

---

**Deployed**: 2025-11-07
**Source**: Round 06 Testing → Production
**Status**: ✅ Multi-Tenant Production Ready
