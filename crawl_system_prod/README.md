# Production Crawl & Extraction Pipeline

**Status**: Design Phase - Awaiting Requirements
**Last Updated**: 2025-11-14

## Overview

Production-grade crawling and extraction system with:
- Decoupled crawling and extraction (configs vs specs)
- 6-layer pipeline with comprehensive tracking
- Real-time progress, cost tracking, and diagnostics
- Retry logic, error handling, and re-run capabilities
- Multi-tenant architecture (client-isolated outputs)

## Quick Start (After Implementation)

```bash
# Dry-run to validate config
python run_pipeline.py <config_name> --dry-run

# Run pipeline
python run_pipeline.py <config_name>

# Run with options
python run_pipeline.py <config_name> --start-from classify --max-cost 500
```

## Directory Structure

```
crawl_system_prod/
├── run_pipeline.py          # Main orchestrator
├── PRODUCTION_DESIGN.md     # Complete design documentation
│
├── core/                    # Infrastructure
│   ├── config_loader.py     # YAML config validation
│   ├── spec_loader.py       # JSON spec validation
│   ├── progress_tracker.py  # Real-time progress
│   ├── cost_tracker.py      # Cost tracking
│   ├── diagnostics.py       # Diagnostics & failures
│   ├── domain_cache.py      # Deduplication cache
│   ├── layer_crawl.py       # L1: Firecrawl Crawl
│   ├── layer_merge.py       # L2: Merge Segments
│   ├── layer_chunk.py       # L3: Create Chunks
│   ├── layer_classify.py    # L4: LLM Extract
│   ├── layer_export.py      # L5: Export CSV
│   └── layer_dedupe.py      # L6: Deduplicate
│
├── configs/
│   ├── runs/                # Run configs (YAML)
│   │   ├── TEMPLATE.yaml
│   │   └── <client>_<name>.yaml
│   └── specs/
│       └── extraction/      # Extraction specs (JSON)
│           ├── TEMPLATE.json
│           └── <spec_name>.json
│
└── outputs/
    └── <client>/
        └── run_<timestamp>/
            ├── final_results.csv
            ├── progress.json
            ├── costs.json
            ├── diagnostics_l*.json
            ├── failures_l*.json
            └── run.log
```

## 6-Layer Pipeline

1. **L1 Crawl** (Firecrawl) - Crawl target URL for pages
2. **L2 Merge** - Merge segments into single dataset
3. **L3 Chunk** - Split into chunks (1 page per chunk)
4. **L4 Classify** (Claude) - Extract company data per spec
5. **L5 Export** (CSV) - Export with reasoning/evidence
6. **L6 Dedupe** - Remove domain duplicates

## Configuration

### Run Config (`configs/runs/*.yaml`)
```yaml
client: doppel
crawl:
  target_url: "https://paginasamarillas.es/search/clinics"
  limit: 20000
  max_concurrency: 50
  max_depth: 5
extraction_spec: spanish_clinic_extraction
test_mode: 10  # Optional: limit pages for testing
```

### Extraction Spec (`configs/specs/extraction/*.json`)
```json
{
  "spec_name": "spanish_clinic_extraction",
  "extraction_fields": {
    "company_name": {"type": "string", "required": true},
    "domain": {"type": "string", "required": false},
    "phone": {"type": "string", "required": false}
  },
  "questions": [
    {
      "field": "has_website",
      "question": "Does this listing include a website URL?",
      "answer_type": "boolean",
      "reasoning_required": true
    }
  ],
  "llm": {
    "model": "claude-3-5-haiku-20241022",
    "max_tokens": 1500,
    "temperature": 0
  }
}
```

## Output Files

Each run creates a timestamped folder with:
- **final_results.csv** - Your deliverable with all fields
- **progress.json** - Real-time progress tracking
- **costs.json** - Complete cost breakdown
- **diagnostics_l{1-6}_{layer}.json** - Per-layer stats
- **failures_l{1,4}_{layer}.json** - Failed items for re-runs
- **run.log** - Exhaustive execution log

## Environment Variables

Required in `.env` (parent directory):
```
FIRECRAWL_API_KEY=<your_firecrawl_key>
ANTHROPIC_API_KEY=<your_anthropic_key>
```

## Cost Estimates

**Per Run** (approximate):
- Firecrawl: $0.025 per page
- Claude Haiku: $0.003 per page
- Claude Sonnet: $0.045 per page

**Example Costs:**
- 1,000 pages: ~$28 (Haiku)
- 10,000 pages: ~$280 (Haiku)
- 20,000 pages: ~$560 (Haiku)

## Re-running Failures

```bash
# Re-run only failed items from previous run
python run_pipeline.py <config> --rerun-failures --from-run run_20251114_103000
```

## Key Improvements Over Legacy crawl_system

1. ✅ **Decoupled architecture** - Crawl ≠ Extraction (mix-and-match)
2. ✅ **Object-oriented Python** - Clean separation vs bash scripts
3. ✅ **Production error handling** - Continue on failure, retry logic
4. ✅ **Cost management** - Real-time tracking, budget enforcement
5. ✅ **Comprehensive diagnostics** - Per-layer stats, failure tracking
6. ✅ **Output transparency** - Reasoning + evidence columns
7. ✅ **Modern codebase** - Type-safe, modular, testable
8. ✅ **Developer experience** - Dry-run, real-time progress
9. ✅ **Multi-tenant ready** - Client isolation, concurrent runs
10. ✅ **Domain deduplication** - Avoid duplicate processing

## Documentation

See `PRODUCTION_DESIGN.md` for complete system design including:
- Architecture philosophy
- Configuration formats
- Data flow diagrams
- Error handling strategies
- Retry logic
- Cost breakdown models
- Implementation checklist
