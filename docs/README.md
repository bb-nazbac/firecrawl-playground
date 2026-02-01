# Firecrawl Company Scraper - Production

**General-purpose pipeline for extracting company names and domains from ANY website**

---

## What It Does

Input: Website URL (e.g., `https://example.com/directory`)  
Output: CSV with company names and domains

**Fully automated. No manual intervention needed.**

---

## Quick Start

### Single URL (Direct Execution)

```bash
# Run the pipeline directly
./run_pipeline.sh "https://www.example.com/directory"

# Get results
cat l4_dedupe_and_export/outputs/{client}/{domain}/*.csv
```

### Multiple URLs (Queue System)

```bash
# Add jobs to queue
./queue_add.sh mycompany "https://site1.com/directory"
./queue_add.sh mycompany "https://site2.com/suppliers"

# Start queue manager (runs in background)
./queue_manager.sh &

# Monitor progress
./queue_status.sh
```

**See [QUEUE.md](QUEUE.md) for full queue system documentation.**

---

## Pipeline Layers

```
L1: Crawl with Markdown
  ├─ Crawls entire target domain
  ├─ Extracts markdown (onlyMainContent)
  └─ Output: All pages with content

L2: Merge and Chunk
  ├─ Merges crawl segments
  ├─ Splits into 1-page chunks
  └─ Output: Ready for LLM

L3: LLM Classify & Extract
  ├─ Claude classifies each page
  ├─ Extracts company names + domains
  ├─ Progressive retry (handles rate limits)
  └─ Output: All classifications

L4: Dedupe and Export
  ├─ Deduplicates by domain then name
  ├─ Normalizes domains
  ├─ Exports clean CSV
  └─ Output: final_companies.csv
```

---

## Requirements

- Firecrawl API key (in `.env`)
- Anthropic API key (in `.env`)
- Python 3.9+ (system Python: `/usr/bin/python3`)
- bash shell

---

## Configuration

**File:** `config/pipeline_config.json`

```json
{
  "crawl": {
    "limit": 10000,
    "concurrency": 50,
    "depth": 5
  },
  "llm": {
    "model": "claude-3-5-sonnet-20241022",
    "concurrency": 75,
    "max_retry_cycles": 10
  }
}
```

---

## Cost Estimate

**For ~5,000 page website:**
- Crawl: ~$50
- LLM: ~$20
- **Total: ~$70**

**Output:** 1,000-2,000 companies with domains

---

## Success Metrics

- Classification success: >95%
- Domain extraction: >90%
- Deduplication: Aggressive
- No manual intervention needed

---

**Built from Round 8 testing (97.89% success, 93.1% domain capture)**

