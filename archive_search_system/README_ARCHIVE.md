# Search System Archive

**Status**: ARCHIVED - Reference Only
**Archived**: 2025-11-13
**Replaced By**: `../search_system_prod/`

## What is this?

This directory contains the original/legacy search system that was used during development and testing phases. It has been **replaced by the production system** in `search_system_prod/`.

## Why was it archived?

The production system (`search_system_prod/`) is a complete rewrite with:
- ✓ Unified orchestrator with proper layer management
- ✓ Comprehensive tracking (progress, costs, diagnostics, failures)
- ✓ Config/spec validation system
- ✓ Retry logic and error handling
- ✓ Re-run capabilities
- ✓ Domain deduplication cache
- ✓ Per-client output isolation

The legacy system had:
- ✗ Separate scripts per layer (manual execution)
- ✗ Hardcoded configurations
- ✗ Limited error tracking
- ✗ Manual cost calculation
- ✗ No unified orchestration

## Contents

```
archive_search_system/
├── l1_serpapi_search/       # Original search scripts
├── l2_firecrawl_scrape/     # Original scrape scripts
├── l3_llm_classify/         # Original classification scripts
├── l4_csv_export/           # Original export scripts
├── l5_domain_dedup/         # Original dedup scripts
├── outputs/                 # Historical outputs (massive - 507MB+)
├── logs/                    # Historical logs
└── ...                      # Other legacy files
```

## Can I delete this?

**Yes**, once you've:
1. Verified all production runs work correctly
2. Migrated any important historical outputs
3. No longer need reference to old implementation

## Migration Path

If you need to reference old outputs or configurations:
1. Check `outputs/` for historical run data
2. Check `logs/` for execution logs
3. Check `l3_llm_classify/specs/` for old spec formats

## Production System

Use this instead:
```bash
cd /Users/bahaa/Documents/Clients/firecrawl_playground/search_system_prod
python run_pipeline.py <config_name>
```

See `../search_system_prod/README.md` for complete documentation.
