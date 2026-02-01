# Firecrawl Company Scraper

**General-purpose pipeline for extracting company names and domains from ANY website**

---

## Quick Start

### Single URL (Main Pipeline)

```bash
# Run the pipeline
export CLIENT="mycompany"
./run_pipeline.sh "https://www.example.com/directory"

# Check results (centralized location)
cat client_outputs/mycompany/example/*.csv

# Or check original location
cat main_pipeline/l4_dedupe_and_export/outputs/mycompany/example/*.csv
```

### Multiple URLs (Queue System)

```bash
cd queue_system

# Add jobs
./queue_add.sh mycompany "https://site1.com/directory"
./queue_add.sh mycompany "https://site2.com/suppliers"

# Start queue manager
./queue_manager.sh &

# Monitor progress
./queue_status.sh

# Check all results for client (centralized location)
ls -la ../client_outputs/mycompany/
```

---

## Repository Structure

```
firecrawl_playground/
├── run_pipeline.sh          # Main pipeline entry point
├── .env                     # API keys (FIRECRAWL_API_KEY, ANTHROPIC_API_KEY)
│
├── client_outputs/          # 📊 All final CSVs organized by client
│   └── {client}/
│       └── {domain}/
│           └── {domain}_{timestamp}.csv
│
├── docs/                    # 📚 All documentation
│   ├── COMPLETE_PIPELINE_DOCUMENTATION.md  # Complete system reference
│   ├── QUICKSTART.md                       # Getting started guide
│   └── ...
│
├── main_pipeline/           # 🔧 Single-URL pipeline (L1→L2→L3→L4)
│   ├── l1_crawl_with_markdown/
│   ├── l2_merge_and_chunk/
│   ├── l3_llm_classify_extract/
│   ├── l4_dedupe_and_export/
│   └── logs/
│
├── queue_system/            # 🚀 Robust batch processing system
│   ├── queue_add.sh
│   ├── queue_manager.sh
│   ├── queue_status.sh
│   └── ...
│
├── utils/                   # 🛠️ Utility scripts
│   ├── erudus/             # Large page splitting
│   └── analysis/           # Extraction analysis
│
└── archive/                 # 📦 Deprecated systems
    └── queue/              # Old queue system
```

---

## Documentation

**Start here:** [`docs/COMPLETE_PIPELINE_DOCUMENTATION.md`](docs/COMPLETE_PIPELINE_DOCUMENTATION.md)

This comprehensive guide explains:
- All 3 pipeline systems (main, queue, archived)
- 4-stage architecture (L1-L4)
- Configuration options
- Usage examples
- Error handling
- Performance & costs

**Quick guides:**
- [Quick Start](docs/QUICKSTART.md) - Get running in 5 minutes
- [Queue System](docs/QUEUE.md) - Batch processing details
- [For AI Agents](docs/FOR_AI_AGENTS.md) - AI-specific guide
- [Learnings](docs/LEARNINGS.md) - Model testing insights

---

## What It Does

**Input:** Website URL (e.g., `https://example.com/directory`)
**Output:** CSV with company names and domains

**Pipeline Stages:**
1. **L1: Crawl** - Extract markdown from all pages
2. **L2: Chunk** - Split into 1-page chunks
3. **L3: Classify** - LLM extracts companies
4. **L4: Export** - Deduplicate and export CSV

**Fully automated. No manual intervention needed.**

**All final CSVs automatically copied to:** `client_outputs/{client}/{domain}/`

---

## Requirements

- Python 3.9+ (system Python: `/usr/bin/python3`)
- bash shell
- Firecrawl API key
- Anthropic API key

Create `.env` file:
```bash
FIRECRAWL_API_KEY=fc-xxxxxxxxxxxxxxxxxxxxxxxx
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxxxxxx
```

---

## Performance

**Typical 5,000-page website:**
- Time: 1-2 hours
- Cost: ~$70 (Firecrawl $50 + LLM $20)
- Output: 1,000-2,000 companies with 90-95% domain coverage

---

## Two Systems, One Purpose

**Main Pipeline** (`./run_pipeline.sh`)
- Fast single-URL execution
- Quick testing
- Good for prototyping

**Queue System** (`cd queue_system/`)
- Robust batch processing
- Comprehensive retry logic
- Production-ready
- Unattended execution

---

## Success Metrics

✅ Classification success: >95%
✅ Domain extraction: >90%
✅ Deduplication: Aggressive
✅ No manual intervention needed

**Built from Round 8 testing (97.89% success, 93.1% domain capture)**

---

For complete documentation, see [`docs/COMPLETE_PIPELINE_DOCUMENTATION.md`](docs/COMPLETE_PIPELINE_DOCUMENTATION.md)
