# Main Pipeline

**Single-URL company scraper pipeline**

---

## What This Is

This is the **main pipeline** for scraping a single website URL. It executes all 4 stages (L1→L2→L3→L4) in sequence.

**Entry point:** `../run_pipeline.sh` (at repository root)

---

## Directory Structure

```
main_pipeline/
├── l1_crawl_with_markdown/    # Stage 1: Firecrawl API crawling
│   ├── fetch_segments.py      # Fetch all crawl segments
│   └── outputs/               # Crawl data by client/domain
│
├── l2_merge_and_chunk/        # Stage 2: Merge & split into chunks
│   ├── merge_and_split.py     # Main script
│   └── outputs/               # Chunks by client/domain
│
├── l3_llm_classify_extract/   # Stage 3: LLM classification
│   ├── classify_all_with_retry.sh    # Orchestrator with retry
│   ├── scripts/
│   │   └── classify_chunk.sh         # Per-chunk classification
│   └── outputs/               # LLM responses by client/domain
│
├── l4_dedupe_and_export/      # Stage 4: Dedupe & export
│   ├── export_final.py        # Main script
│   └── outputs/               # Final CSV/JSON by client/domain
│
└── logs/                      # Pipeline execution logs
    └── {client}/{domain}/
        └── {domain}_{timestamp}.log
```

---

## Usage

```bash
# From repository root
./run_pipeline.sh "https://example.com/directory"

# With custom client name
export CLIENT="mycompany"
./run_pipeline.sh "https://example.com/directory"

# Check results
cat main_pipeline/l4_dedupe_and_export/outputs/mycompany/example/*.csv
```

---

## How It Works

### L1: Crawl with Markdown
- Submits crawl job to Firecrawl API
- Polls until complete
- Downloads all segments (100 pages per segment)
- Saves to `l1_crawl_with_markdown/outputs/{client}/{domain}/segments/`

### L2: Merge and Chunk
- Reads all segments from L1
- Merges into single dataset
- Splits into 1-page chunks (optimal for LLM accuracy)
- Saves to `l2_merge_and_chunk/outputs/{client}/{domain}/chunks/`

### L3: LLM Classify & Extract
- Reads all chunks from L2
- Sends each to Claude Sonnet 4.5 for classification
- Extracts company names and domains
- Auto-retries rate limits (up to 10 cycles)
- Saves to `l3_llm_classify_extract/outputs/{client}/{domain}/llm_responses/`

### L4: Dedupe and Export
- Reads all LLM responses from L3
- Deduplicates by domain, then by normalized name
- Normalizes domains (removes http, www, paths)
- Exports CSV and JSON
- Saves to `l4_dedupe_and_export/outputs/{client}/{domain}/`

---

## Output Format

**CSV:** `{domain}_{timestamp}.csv`
```csv
name,domain,website_original,classification_type,source_file
Acme Corp,acme.com,https://www.acme.com,company_individual,chunk_0042
Beta Inc,beta.com,www.beta.com/,company_list,chunk_0015
```

**JSON:** `{domain}_{timestamp}.json`
```json
{
  "metadata": {
    "domain": "example",
    "timestamp": "20251027_123456",
    "total_companies": 1234,
    "with_domains": 1150,
    "without_domains": 84
  },
  "companies": [...]
}
```

---

## Configuration

All paths use **relative references** from script locations:
- Python scripts: `Path(__file__).parent` for self, `.parent` for project root
- Bash scripts: `SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"`

This makes the pipeline **portable** - works anywhere you copy it.

---

## Error Handling

**L1:** No retry logic (main pipeline) - fails on API errors
**L2:** No retry logic - fails on malformed JSON
**L3:** ✅ Comprehensive retry (up to 10 cycles, 10s cooldown)
**L4:** No retry logic - continues with partial data

For **robust error handling**, use the Queue System instead (`../queue_system/`)

---

## Monitoring

**Progress:**
```bash
# Count segments downloaded (L1)
ls main_pipeline/l1_crawl_with_markdown/outputs/{client}/{domain}/segments/ | wc -l

# Count chunks created (L2)
ls main_pipeline/l2_merge_and_chunk/outputs/{client}/{domain}/chunks/ | wc -l

# Count LLM responses (L3)
ls main_pipeline/l3_llm_classify_extract/outputs/{client}/{domain}/llm_responses/ | wc -l
```

**Logs:**
```bash
# Pipeline execution log
tail -f main_pipeline/logs/{client}/{domain}/{domain}_{timestamp}.log
```

---

## When to Use This vs Queue System

**Use Main Pipeline when:**
- Testing a single URL quickly
- Prototyping
- One-off scraping jobs
- You want immediate results

**Use Queue System when:**
- Processing multiple URLs
- Production environment
- Need robust error handling on ALL stages
- Unattended execution
- Detailed logging required

---

For complete documentation, see [`../docs/COMPLETE_PIPELINE_DOCUMENTATION.md`](../docs/COMPLETE_PIPELINE_DOCUMENTATION.md)
