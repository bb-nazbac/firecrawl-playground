# Complete Pipeline Documentation

**Last Updated:** 2025-10-28
**For:** AI Agents and Future Developers
**Purpose:** Comprehensive reference for all pipeline systems in this repository

---

## Table of Contents

1. [Overview](#overview)
2. [Pipeline Systems](#pipeline-systems)
3. [Core Pipeline Stages (L1-L4)](#core-pipeline-stages-l1-l4)
4. [Architecture Comparison](#architecture-comparison)
5. [File Structure](#file-structure)
6. [Configuration](#configuration)
7. [Usage Examples](#usage-examples)
8. [Specialized Scripts](#specialized-scripts)
9. [Error Handling & Retry Logic](#error-handling--retry-logic)
10. [Performance & Costs](#performance--costs)
11. [Known Issues & Solutions](#known-issues--solutions)
12. [Development History](#development-history)

---

## Overview

### What This Repository Does

**Input:** Any website URL with company listings
**Output:** CSV/JSON with company names and domains
**Approach:** Crawl → Chunk → LLM Classification → Extraction → Deduplication

This repository contains **general-purpose**, **production-ready** pipelines for extracting company information from any website directory or listing.

### Key Design Principles

1. **Generalized** - No website-specific logic, no hardcoded patterns
2. **Resilient** - Auto-retries rate limits, handles errors gracefully
3. **Portable** - All paths relative, works anywhere
4. **Self-contained** - All code, prompts, documentation included
5. **Scalable** - Queue system for batch processing

---

## Pipeline Systems

This repository contains **three distinct pipeline systems**:

### 1. Main Pipeline (Original)

**Location:** Root directory (`l1_crawl_with_markdown/`, `l2_merge_and_chunk/`, `l3_llm_classify_extract/`, `l4_dedupe_and_export/`)
**Entry Point:** `./run_pipeline.sh <url>`
**Status:** Production-ready, validated
**Use Case:** Single URL execution, quick testing

**Characteristics:**
- ✅ Simple, straightforward execution
- ✅ Fast setup
- ❌ Fails on error (`set -e`)
- ⚠️ Only L3 has retry logic
- ⚠️ No pre-flight checks

**When to Use:**
- Quick testing on a single URL
- When you need immediate results
- When you're confident the target website is well-formed

### 2. Queue System (Robust, Isolated)

**Location:** `queue_system/` directory
**Entry Point:**
- Add jobs: `./queue_system/queue_add.sh <client> <url>`
- Start manager: `./queue_system/queue_manager.sh &`
- Check status: `./queue_system/queue_status.sh`

**Status:** Production-ready, battle-tested
**Use Case:** Multiple URLs, batch processing, unattended execution

**Characteristics:**
- ✅ Comprehensive retry logic on ALL stages (L1-L4)
- ✅ Pre-flight checks (disk space, API keys, network)
- ✅ Graceful error handling (no `set -e`)
- ✅ Isolated outputs (won't interfere with main pipeline)
- ✅ Detailed logging at all levels
- ✅ Queue management (FIFO, serial execution)
- ✅ Handles partial failures (exports what's available)

**When to Use:**
- Processing multiple websites
- Running unattended batch jobs
- Production environment with reliability requirements
- When you need detailed logs and monitoring

### 3. Old Queue System (Deprecated)

**Location:** `queue/` directory at root
**Status:** Superseded by `queue_system/`, keep for reference only

---

## Core Pipeline Stages (L1-L4)

All pipeline systems share the same 4-stage architecture:

### L1: Crawl with Markdown

**Purpose:** Crawl target website and extract markdown content

**Process:**
1. Submit crawl job to Firecrawl API v2 (`/v2/crawl`)
2. Receive crawl ID
3. Poll API until crawl completes
4. Fetch all segments (paginated, 100 pages per segment)
5. Save segments as JSON files

**Configuration:**
```json
{
  "url": "<target_url>",
  "limit": 20000,              // Max pages to crawl
  "maxConcurrency": 50,        // Parallel crawlers
  "maxDiscoveryDepth": 5,      // Link depth
  "allowExternalLinks": false,
  "scrapeOptions": {
    "formats": ["markdown"],
    "onlyMainContent": true,   // Strip navigation/ads
    "blockAds": true
  }
}
```

**Files:**
- Main: `l1_crawl_with_markdown/fetch_segments.py`
- Robust: `queue_system/scripts/l1_crawl_with_markdown/fetch_segments_robust.py`

**Outputs:**
- Main: `l1_crawl_with_markdown/outputs/{client}/{domain}/segments/segment_XXX.json`
- Queue: `queue_system/outputs/{client}/{domain}/segments/segment_XXX.json`

**Segment Format:**
```json
{
  "data": [
    {
      "url": "https://example.com/page1",
      "markdown": "# Page content...",
      "metadata": {...}
    }
  ],
  "next": "skip=100"  // For pagination
}
```

**Retry Logic (Robust Only):**
- 10-attempt retry with exponential backoff
- Handles rate limits automatically
- Validates JSON responses
- Continues even if some segments fail

---

### L2: Merge and Chunk

**Purpose:** Merge all segments and split into 1-page chunks for LLM processing

**Process:**
1. Read all segment files from L1 output directory
2. Merge all pages into single dataset
3. Split into 1-page chunks (optimal for extraction accuracy)
4. Save each chunk as separate JSON file

**Why 1-page chunks?**
- Better extraction accuracy per page
- Easier to retry individual pages
- Prevents LLM from stopping early on dense pages
- Allows parallel processing in L3

**Files:**
- Main: `l2_merge_and_chunk/merge_and_split.py`
- Robust: `queue_system/scripts/l2_merge_and_chunk/merge_and_split_robust.py`

**Outputs:**
- Main: `l2_merge_and_chunk/outputs/{client}/{domain}/chunks/chunk_XXXX.json`
- Queue: `queue_system/outputs/{client}/{domain}/chunks/chunk_XXXX.json`

**Chunk Format:**
```json
{
  "chunk_id": 1,
  "page_count": 1,
  "pages": [
    {
      "id": 1,
      "url": "https://example.com/page1",
      "title": "Page Title",
      "markdown": "# Page content...",
      "markdown_length": 5432
    }
  ]
}
```

**Validation (Robust Only):**
- Checks segment files exist before reading
- Handles malformed JSON gracefully
- Skips empty pages
- Validates disk space before writing

---

### L3: LLM Classify & Extract

**Purpose:** Use Claude/GPT to classify pages and extract company data

**Process:**
1. Read all chunk files from L2 output directory
2. For each chunk, send markdown to LLM with classification prompt
3. LLM classifies page type and extracts companies
4. Save LLM response as JSON file
5. Retry failed chunks with progressive backoff

**Classification Types:**
- `company_individual` - Single company profile page
- `company_list` - List of multiple companies
- `navigation` - Navigation/category page with no company data
- `other` - Unrelated content

**LLM Models Used:**
- Primary: Claude 3.5 Sonnet (`claude-3-5-sonnet-20241022`)
- Alternative: OpenAI GPT-4o (for dense list pages - see LEARNINGS.md)

**Prompt Strategy:**
- Exhaustive extraction (extract EVERY company found)
- Company's OWN website domain (not directory URL)
- Looks for "Website:", http links in markdown
- Returns empty string if no domain found

**Files:**
- Main:
  - Orchestrator: `l3_llm_classify_extract/classify_all_with_retry.sh`
  - Per-chunk: `l3_llm_classify_extract/scripts/classify_chunk.sh`
- Robust:
  - Orchestrator: `queue_system/scripts/l3_llm_classify_extract/classify_all_robust.sh`
  - Per-chunk: `queue_system/scripts/l3_llm_classify_extract/scripts/classify_chunk_robust.sh`

**Outputs:**
- Main: `l3_llm_classify_extract/outputs/{client}/{domain}/llm_responses/response_chunk_XXXX.json`
- Queue: `queue_system/outputs/{client}/{domain}/llm_responses/response_chunk_XXXX.json`

**Response Format:**
```json
{
  "classification": "company_list",
  "confidence": "high",
  "reasoning": "Page contains multiple company listings...",
  "companies_extracted": [
    {
      "name": "Acme Corp",
      "website": "acme.com"
    },
    {
      "name": "Beta Inc",
      "website": "beta.com"
    }
  ]
}
```

**Retry Logic:**
- Main: Up to 10 cycles, 10-second cooldown between cycles
- Robust: 10-attempt retry per chunk with exponential backoff + jitter
- Handles rate limits automatically
- Succeeds if ≥50% of chunks complete (robust only)

**Concurrency:**
- Main: 75 parallel requests (safe for 400k token/min limit)
- Robust: 75 parallel requests with backoff

**Cost Per Chunk:**
- ~$0.002-0.01 depending on chunk size
- Dense pages: up to $0.57 (OpenAI) or $0.30 (Claude)

---

### L4: Dedupe and Export

**Purpose:** Deduplicate companies and export clean CSV/JSON

**Process:**
1. Read all LLM response files from L3 output directory
2. Extract all companies with classifications
3. Deduplicate by domain first (exact match)
4. Deduplicate by normalized name (for entries without domains)
5. Normalize domains (remove http, www, paths)
6. Normalize names (handle "Inc." vs "Inc", "Corp." vs "Corp")
7. Export to CSV and JSON with metadata

**Deduplication Strategy:**
```
Priority 1: Domain-based deduplication
  - Exact domain match
  - Keep first occurrence

Priority 2: Name-based deduplication (for entries without domains)
  - Normalize: lowercase, remove punctuation
  - Handle common variations (Inc/Inc., Corp/Corp., Ltd/Ltd.)
  - Keep entry with domain over entry without
```

**Domain Normalization:**
```
Input:  "https://www.example.com/path?query=1"
Output: "example.com"

Steps:
1. Remove protocol (http://, https://)
2. Remove www.
3. Remove path and query
4. Remove port
5. Lowercase
```

**Name Normalization:**
```
Input:  "Acme Corp., Inc."
Output: "acme corp inc"

Steps:
1. Lowercase
2. Remove punctuation (commas, periods)
3. Normalize spacing
```

**Files:**
- Main: `l4_dedupe_and_export/export_final.py`
- Robust: `queue_system/scripts/l4_dedupe_and_export/export_final_robust.py`

**Outputs:**
- Main:
  - `l4_dedupe_and_export/outputs/{client}/{domain}/{domain}_{timestamp}.csv`
  - `l4_dedupe_and_export/outputs/{client}/{domain}/{domain}_{timestamp}.json`
- Queue:
  - `queue_system/outputs/{client}/{domain}/{domain}_{timestamp}.csv`
  - `queue_system/outputs/{client}/{domain}/{domain}_{timestamp}.json`

**CSV Format:**
```csv
name,domain,website_original,classification_type,source_file
Acme Corp,acme.com,https://www.acme.com,company_individual,chunk_0042
Beta Inc,beta.com,www.beta.com/,company_list,chunk_0015
```

**JSON Format:**
```json
{
  "metadata": {
    "client": "test",
    "domain": "example",
    "timestamp": "20251027_123456",
    "total_companies": 1234,
    "with_domains": 1150,
    "without_domains": 84,
    "total_chunks_processed": 500
  },
  "companies": [
    {
      "name": "Acme Corp",
      "domain": "acme.com",
      "website_original": "https://www.acme.com",
      "classification_type": "company_individual",
      "source_file": "chunk_0042"
    }
  ]
}
```

**Validation (Robust Only):**
- Checks L3 response files exist
- Handles malformed JSON responses gracefully
- Continues even if some responses fail
- Validates disk space before writing
- Exports whatever data is available (partial success)

---

## Architecture Comparison

### Main Pipeline vs Queue System

| Feature | Main Pipeline | Queue System |
|---------|--------------|--------------|
| **Entry Point** | `./run_pipeline.sh <url>` | `./queue_add.sh` + `./queue_manager.sh` |
| **Error Handling** | Fails on error (`set -e`) | Graceful failures |
| **Retry Logic** | L3 only (10 cycles) | All stages (L1-L4) |
| **Pre-flight Checks** | None | API keys, disk space, network |
| **Partial Results** | Fails if any stage fails | Exports partial data |
| **Outputs** | Mixed in root directories | Isolated in `queue_system/outputs/` |
| **Logging** | Basic, per-pipeline | Comprehensive, multi-level |
| **Batch Processing** | Manual | Automatic queue management |
| **Monitoring** | Manual log inspection | `queue_status.sh` command |
| **Concurrency** | Single job only | Serial queue execution |
| **Job Management** | None | Add, status, manager daemon |
| **Use Case** | Single URL testing | Production batch processing |

### Pre-flight Checks (Queue System Only)

Before starting any pipeline, the queue system checks:
- ✅ API keys configured (`FIRECRAWL_API_KEY`, `ANTHROPIC_API_KEY`)
- ✅ Disk space available (500MB minimum)
- ✅ Network connectivity to Firecrawl API
- ✅ Python environment working
- ✅ Required tools installed (jq, curl, bash)

### Retry Logic Comparison

**Main Pipeline (L3 Only):**
```bash
# classify_all_with_retry.sh
for cycle in 1..10; do
  # Try all failed chunks
  sleep 10  # Cooldown
done
```

**Queue System (All Stages):**
```bash
# L1: fetch_segments_robust.py
for attempt in 1..10; do
  try_fetch_segment()
  if success: break
  sleep (2^attempt + jitter)  # Exponential backoff
done

# L2: merge_and_split_robust.py
- Validate inputs exist
- Handle malformed JSON
- Check disk space

# L3: classify_all_robust.sh
for chunk in chunks; do
  for attempt in 1..10; do
    classify_chunk_robust()
    if success: break
    sleep (2^attempt + jitter)
  done
done

# L4: export_final_robust.py
- Validate L3 outputs exist
- Handle partial results
- Export available data
```

---

## File Structure

```
firecrawl_playground/
│
├── ============================================================
├──  MAIN PIPELINE (Original)
├── ============================================================
│
├── run_pipeline.sh              # Main entry point for single URL
│
├── l1_crawl_with_markdown/
│   ├── fetch_segments.py        # Fetch crawl segments from Firecrawl
│   ├── crawl_job.json           # Crawl job details (generated)
│   └── outputs/                 # Crawl outputs
│       └── {client}/{domain}/
│           └── segments/
│               ├── segment_001.json
│               ├── segment_002.json
│               └── ...
│
├── l2_merge_and_chunk/
│   ├── merge_and_split.py       # Merge segments + create chunks
│   ├── merge_segments.py        # Legacy: only merge
│   ├── split_into_chunks.py     # Legacy: only split
│   └── outputs/                 # Chunk outputs
│       └── {client}/{domain}/
│           └── chunks/
│               ├── chunk_0001.json
│               ├── chunk_0002.json
│               └── ...
│
├── l3_llm_classify_extract/
│   ├── classify_all_with_retry.sh     # Main orchestrator with retry
│   ├── scripts/
│   │   └── classify_chunk.sh          # Classify single chunk
│   ├── outputs/                       # LLM response outputs
│   │   └── {client}/{domain}/
│   │       └── llm_responses/
│   │           ├── response_chunk_0001.json
│   │           ├── response_chunk_0002.json
│   │           └── ...
│   └── logs/                          # Classification logs
│
├── l4_dedupe_and_export/
│   ├── export_final.py          # Dedupe + export CSV/JSON
│   └── outputs/                 # Final outputs
│       └── {client}/{domain}/
│           ├── {domain}_{timestamp}.csv
│           └── {domain}_{timestamp}.json
│
├── ============================================================
├──  QUEUE SYSTEM (Robust, Isolated)
├── ============================================================
│
├── queue_system/
│   │
│   ├── queue_add.sh             # Add job to queue
│   ├── queue_manager.sh         # Queue daemon (background)
│   ├── queue_status.sh          # Check queue status
│   ├── README.md                # Queue system docs
│   │
│   ├── scripts/                 # Robust versions of all stages
│   │   ├── run_pipeline_robust.sh
│   │   ├── l1_crawl_with_markdown/
│   │   │   └── fetch_segments_robust.py
│   │   ├── l2_merge_and_chunk/
│   │   │   └── merge_and_split_robust.py
│   │   ├── l3_llm_classify_extract/
│   │   │   ├── classify_all_robust.sh
│   │   │   └── scripts/
│   │   │       └── classify_chunk_robust.sh
│   │   └── l4_dedupe_and_export/
│   │       └── export_final_robust.py
│   │
│   ├── queue/                   # Queue state management
│   │   ├── queue.txt            # Pending jobs (FIFO)
│   │   ├── active.json          # Currently running job
│   │   ├── completed.txt        # Successfully completed jobs
│   │   ├── failed.txt           # Failed jobs
│   │   ├── manager.log          # Queue manager activity log
│   │   └── logs/                # Per-job pipeline logs
│   │       └── {client}_{domain}.log
│   │
│   ├── outputs/                 # Isolated outputs
│   │   └── {client}/{domain}/
│   │       ├── segments/
│   │       ├── chunks/
│   │       ├── llm_responses/
│   │       ├── {domain}_{timestamp}.csv
│   │       └── {domain}_{timestamp}.json
│   │
│   └── logs/                    # Detailed stage logs
│       └── {client}/{domain}/
│
├── ============================================================
├──  SPECIALIZED SCRIPTS & UTILITIES
├── ============================================================
│
├── split_erudus_simple.py       # Split large single-page lists
├── split_erudus.py              # Advanced Erudus splitting
├── split_erudus.sh              # Erudus split wrapper
├── export_erudus_simple.py      # Simple Erudus export
│
├── analyze_empty_websites_by_type.py    # Analyze extraction failures
├── check_extraction_failure.py          # Check why extraction failed
├── find_directory_page_failures.py      # Find pages with bad URLs
├── find_empty_websites.py               # Find companies without websites
│
├── ============================================================
├──  DOCUMENTATION
├── ============================================================
│
├── README.md                    # Quick overview
├── QUICKSTART.md                # Getting started guide
├── QUEUE.md                     # Queue system detailed docs
├── FOR_AI_AGENTS.md             # Guide for AI agents
├── LEARNINGS.md                 # Testing insights (OpenAI vs Claude)
├── PRODUCTION_READY.md          # Production validation results
├── CONFIG.md                    # Configuration guide
├── PROMPT.md                    # LLM prompt documentation
├── COMMANDMENTS.yml             # Development rules
├── COMPLETE_PIPELINE_DOCUMENTATION.md  # This file!
│
├── ============================================================
├──  CONFIGURATION & ENVIRONMENT
├── ============================================================
│
├── .env                         # API keys (gitignored)
│   # FIRECRAWL_API_KEY=fc-xxx
│   # ANTHROPIC_API_KEY=sk-ant-xxx
│   # OPENAI_API_KEY=sk-xxx
│
├── ============================================================
├──  LEGACY / DEPRECATED
├── ============================================================
│
├── queue/                       # Old queue system (deprecated)
│   ├── queue.txt
│   ├── active.json
│   ├── completed.txt
│   ├── failed.txt
│   └── logs/
│
├── queue_add.sh                 # Old queue add (use queue_system/)
├── queue_manager.sh             # Old queue manager (use queue_system/)
└── queue_status.sh              # Old queue status (use queue_system/)
```

---

## Configuration

### Environment Variables

All pipelines require API keys in `.env` file:

```bash
# .env file (place in project root)
FIRECRAWL_API_KEY=fc-xxxxxxxxxxxxxxxxxxxxxxxx
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxxxxxx
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx  # Optional, for OpenAI model
```

**Location:**
- Main pipeline: Checks root directory and parent
- Queue system: Checks `queue_system/` directory and parent

### Crawl Configuration

**File:** `run_pipeline.sh` (lines 82-96) or `queue_system/scripts/run_pipeline_robust.sh`

```bash
curl -X POST https://api.firecrawl.dev/v2/crawl \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"url\": \"$TARGET_URL\",
    \"limit\": 20000,              # Max pages (default: 10000, queue: 20000)
    \"maxConcurrency\": 50,        # Parallel crawlers
    \"maxDiscoveryDepth\": 5,      # Link following depth
    \"allowExternalLinks\": false, # Stay on domain
    \"scrapeOptions\": {
      \"formats\": [\"markdown\"],
      \"onlyMainContent\": true,
      \"blockAds\": true
    }
  }"
```

**Adjustable Parameters:**
- `limit`: Maximum pages to crawl (10000-20000 recommended)
- `maxConcurrency`: Crawl speed (50 = fast, 10 = slow but polite)
- `maxDiscoveryDepth`: How deep to follow links (5 = good default)

### LLM Configuration

**File:** `l3_llm_classify_extract/scripts/classify_chunk.sh` (line ~102)

**Model Selection:**
```bash
# Current default
MODEL="claude-3-5-sonnet-20241022"

# Alternatives:
# MODEL="claude-3-5-haiku-20241022"     # Cheaper, less accurate
# MODEL="gpt-4o-2024-08-06"             # For dense list pages (see LEARNINGS.md)
```

**Concurrency:**
```bash
# File: classify_all_with_retry.sh or classify_all_robust.sh
MAX_CONCURRENT=75  # Safe for 400k token/min limit
```

**Retry Cycles:**
```bash
# Main pipeline: classify_all_with_retry.sh
MAX_CYCLES=10
COOLDOWN=10  # seconds between cycles

# Queue system: classify_all_robust.sh
MAX_ATTEMPTS=10
BACKOFF="exponential with jitter"
```

### Client and Domain Naming

**For Main Pipeline:**
```bash
# Set CLIENT environment variable before running
export CLIENT="mycompany"
export DOMAIN="specificdomain"  # Optional, auto-extracted if not set
./run_pipeline.sh "https://example.com/directory"
```

**For Queue System:**
```bash
# Client is first parameter to queue_add.sh
./queue_system/queue_add.sh "mycompany" "https://example.com/directory"

# Domain auto-extracted from URL
# example.com/directory -> domain = "example"
```

---

## Usage Examples

### Example 1: Quick Single URL Test (Main Pipeline)

```bash
cd /Users/bahaa/Documents/Clients/firecrawl_playground

# Set client (optional, defaults to "default")
export CLIENT="test"

# Run pipeline
./run_pipeline.sh "https://www.example.com/directory"

# Check results
cat l4_dedupe_and_export/outputs/test/example/*.csv
```

**Expected Output:**
```
[L1] CRAWL WITH MARKDOWN
Starting crawl (limit: 10000, concurrency: 50)...
Crawl started: abc123-crawl-id
Fetching all segments...
[L1] COMPLETE

[L2] MERGE AND CHUNK
Merging 10 segments into single dataset...
Creating 247 chunks...
[L2] COMPLETE

[L3] LLM CLASSIFY & EXTRACT
Processing 247 chunks (concurrency: 75)...
Cycle 1: 245 successful, 2 failed
Cycle 2: 2 successful, 0 failed
[L3] COMPLETE

[L4] DEDUPE AND EXPORT
Found 1,234 raw companies
After deduplication: 567 unique companies
[L4] COMPLETE

PIPELINE COMPLETE!
Final output: l4_dedupe_and_export/outputs/test/example/example_20251027_123456.csv

SUMMARY:
  Companies extracted: 567
  With domains: 523 (92%)
```

---

### Example 2: Batch Processing Multiple URLs (Queue System)

```bash
cd /Users/bahaa/Documents/Clients/firecrawl_playground/queue_system

# Add multiple jobs
./queue_add.sh "foodco" "https://www.totalfood.com/directory"
./queue_add.sh "foodco" "https://www.specialtyfood.com/members"
./queue_add.sh "foodco" "https://www.fooddirectory.com/companies"

# Start queue manager in background
./queue_manager.sh &

# Monitor status
./queue_status.sh

# Watch progress in real-time
watch -n 5 ./queue_status.sh

# Check logs
tail -f queue/manager.log
tail -f queue/logs/foodco_totalfood.log

# Get results
ls outputs/foodco/*/*.csv
cat outputs/foodco/totalfood/*.csv
```

**Queue Status Output:**
```
╔════════════════════════════════════════════════════════════════╗
║         ROBUST QUEUE SYSTEM STATUS                            ║
╚════════════════════════════════════════════════════════════════╝

⚙️  ACTIVE JOBS:
   foodco/totalfood → PID: 12345 (started: 2025-10-27 12:00:00)

📋 PENDING QUEUE:
   Total jobs: 2

   1. foodco/specialtyfood
      https://www.specialtyfood.com/members
   2. foodco/fooddirectory
      https://www.fooddirectory.com/companies

📊 STATISTICS:
   ✅ Completed: 0
   ❌ Failed:    0
```

---

### Example 3: Handling Large Single-Page Lists (Erudus)

Some directories have ALL companies on a single page (e.g., 1,500+ companies). These need special handling:

```bash
cd /Users/bahaa/Documents/Clients/firecrawl_playground

# First, run normal pipeline
export CLIENT="openinfo"
export DOMAIN="erudus"
./run_pipeline.sh "https://erudus.com/approved-suppliers"

# L2 will create 1 massive chunk
# Split it into smaller chunks for better LLM processing
./split_erudus_simple.py

# This creates 10 chunks:
# - Chunk 1: Header + Wholesalers (194 companies)
# - Chunks 2-10: Manufacturers split into 9 parts (~165 each)

# Continue with L3 and L4
./l3_llm_classify_extract/classify_all_with_retry.sh
/usr/bin/python3 ./l4_dedupe_and_export/export_final.py
```

---

### Example 4: Re-running Failed Stages

**Main Pipeline:**
```bash
# Pipeline failed at L3 due to rate limits
# Resume from L3 (L1 and L2 outputs still exist)
export CLIENT="test"
export DOMAIN="example"
export TIMESTAMP="20251027_123456"

./l3_llm_classify_extract/classify_all_with_retry.sh
/usr/bin/python3 ./l4_dedupe_and_export/export_final.py
```

**Queue System:**
```bash
# Job failed, check why
cat queue_system/queue/failed.txt

# Output: foodco/example|https://example.com|Fri Oct 27 12:00:00 2025

# Fix issue (e.g., add API key), then re-add job
./queue_system/queue_add.sh "foodco" "https://example.com"
```

---

### Example 5: Monitoring Long-Running Jobs

**Main Pipeline:**
```bash
# Count processed chunks
ls l3_llm_classify_extract/outputs/test/example/llm_responses/ | wc -l

# Check for errors
grep -r "ERROR\|rate limit" logs/test/example/

# Watch final output size
watch ls -lh l4_dedupe_and_export/outputs/test/example/
```

**Queue System:**
```bash
# Check queue status
./queue_system/queue_status.sh

# Monitor manager
tail -f queue_system/queue/manager.log

# Monitor specific job
tail -f queue_system/queue/logs/foodco_example.log

# Count segments downloaded (L1)
ls queue_system/outputs/foodco/example/segments/ | wc -l

# Count chunks created (L2)
ls queue_system/outputs/foodco/example/chunks/ | wc -l

# Count LLM responses (L3)
ls queue_system/outputs/foodco/example/llm_responses/ | wc -l
```

---

## Specialized Scripts

### Erudus Splitting Scripts

**Purpose:** Handle large single-page directories with 1,000+ companies

**Files:**
- `split_erudus_simple.py` - Simple line-based splitting
- `split_erudus.py` - Advanced splitting with section detection
- `split_erudus.sh` - Wrapper script

**Use Case:**
```bash
# Erudus has 1,684 companies on ONE page
# Normal chunking creates 1 massive chunk -> LLM stops early
# Solution: Split into 10 smaller chunks

./split_erudus_simple.py
# Creates:
# - chunk_0001.json: Wholesalers (194 companies)
# - chunk_0002.json: Manufacturers part 1 (~165 companies)
# - chunk_0003.json: Manufacturers part 2 (~165 companies)
# ...
# - chunk_0010.json: Manufacturers part 9 (~165 companies)
```

### Analysis Scripts

**Purpose:** Debug extraction failures and data quality issues

#### `analyze_empty_websites_by_type.py`

Analyzes why some companies have no website extracted:

```bash
/usr/bin/python3 analyze_empty_websites_by_type.py

# Output:
# Companies by classification type:
#   company_individual: 123 companies, 45 without websites (37%)
#   company_list: 456 companies, 12 without websites (3%)
#
# Possible reasons:
#   - Website not displayed on individual pages
#   - Website in non-markdown format (e.g., JavaScript)
#   - Website field empty in source data
```

#### `check_extraction_failure.py`

Checks specific chunks that failed extraction:

```bash
/usr/bin/python3 check_extraction_failure.py

# Output:
# Failed chunks: 5
#   - chunk_0042: No company data found (classification: navigation)
#   - chunk_0098: Rate limit error, retried successfully
#   - chunk_0123: Malformed JSON response
```

#### `find_directory_page_failures.py`

Finds pages where directory URL was extracted instead of company website:

```bash
/usr/bin/python3 find_directory_page_failures.py

# Output:
# Found 12 companies with directory URLs:
#   - Acme Corp: example.com/directory/acme (should be: acme.com)
#   - Beta Inc: example.com/companies/beta (should be: beta.com)
```

#### `find_empty_websites.py`

Simple script to count companies without websites:

```bash
/usr/bin/python3 find_empty_websites.py

# Output:
# Total companies: 567
# With websites: 523 (92%)
# Without websites: 44 (8%)
```

---

## Error Handling & Retry Logic

### Common Errors and Solutions

#### Error: "Rate limit exceeded" (L3)

**Symptom:**
```
ERROR: {"type":"error","error":{"type":"rate_limit_error",...}}
```

**Cause:** Anthropic API rate limit (400k tokens/min)

**Solution:**
- Main pipeline: Automatic retry with 10-second cooldown (up to 10 cycles)
- Queue system: Automatic retry with exponential backoff
- Both: Usually resolves in 1-3 cycles

**Manual intervention:**
```bash
# Not needed - automatic retry handles this
# Just wait for completion
```

---

#### Error: "Firecrawl API timeout" (L1)

**Symptom:**
```
ERROR: Request to Firecrawl API timed out after 120 seconds
```

**Cause:** Firecrawl API slow or overloaded

**Solution:**
- Main pipeline: Fails, must restart
- Queue system: Automatic retry with exponential backoff (up to 10 attempts)

**Manual intervention (main pipeline only):**
```bash
# Delete crawl_job.json to restart crawl
rm l1_crawl_with_markdown/crawl_job.json

# Restart pipeline
./run_pipeline.sh "https://example.com"
```

---

#### Error: "No space left on device" (L2)

**Symptom:**
```
OSError: [Errno 28] No space left on device
```

**Cause:** Disk full

**Solution:**
- Queue system: Pre-flight check catches this before running
- Main pipeline: No pre-flight check, fails at L2

**Manual intervention:**
```bash
# Free up space
rm -rf old_outputs/
rm logs/*.log

# Check available space
df -h .

# Restart from L2
export CLIENT="test"
export DOMAIN="example"
export TIMESTAMP="20251027_123456"
/usr/bin/python3 l2_merge_and_chunk/merge_and_split.py
```

---

#### Error: "Invalid API key" (L1 or L3)

**Symptom:**
```
ERROR: {"type":"error","error":{"type":"authentication_error","message":"Invalid API key"}}
```

**Cause:** Missing or incorrect API key in `.env`

**Solution:**
- Queue system: Pre-flight check catches this before running
- Main pipeline: Fails immediately at L1 or L3

**Manual intervention:**
```bash
# Check .env file exists
cat .env

# Verify API keys
echo $FIRECRAWL_API_KEY
echo $ANTHROPIC_API_KEY

# If missing, create .env
cat > .env <<EOF
FIRECRAWL_API_KEY=fc-xxxxxxxxxxxxxxxxxxxxxxxx
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxxxxxx
EOF

# Restart pipeline
./run_pipeline.sh "https://example.com"
```

---

#### Error: "Malformed JSON response" (L3)

**Symptom:**
```
ERROR: Invalid JSON in response_chunk_0042.json
```

**Cause:** LLM returned invalid JSON (rare)

**Solution:**
- Main pipeline: Retries the chunk in next cycle
- Queue system: Retries with exponential backoff

**Manual intervention (if all retries fail):**
```bash
# Check the malformed response
cat l3_llm_classify_extract/outputs/test/example/llm_responses/response_chunk_0042.json

# Manually fix JSON or delete file to retry
rm l3_llm_classify_extract/outputs/test/example/llm_responses/response_chunk_0042.json

# Restart L3
./l3_llm_classify_extract/classify_all_with_retry.sh
```

---

### Retry Logic Deep Dive

#### Main Pipeline L3 Retry

**File:** `l3_llm_classify_extract/classify_all_with_retry.sh`

**Algorithm:**
```bash
MAX_CYCLES=10
COOLDOWN=10  # seconds

for cycle in 1..$MAX_CYCLES; do
  echo "=== Cycle $cycle ==="

  # Find all chunks without responses
  chunks_to_process = chunks_without_responses()

  if chunks_to_process is empty:
    echo "All chunks processed!"
    exit 0
  fi

  # Process failed chunks in parallel (75 concurrent)
  parallel_process(chunks_to_process, MAX_CONCURRENT=75)

  # Cooldown before next cycle
  sleep $COOLDOWN
done

# After all cycles, check if we have enough data
success_rate = count_successful_chunks() / total_chunks
if success_rate >= 0.95:
  echo "Acceptable success rate: $success_rate"
  exit 0
else:
  echo "WARNING: Low success rate: $success_rate"
  exit 0  # Continue anyway, L4 will work with what we have
fi
```

**Key Features:**
- Retries only failed chunks (efficient)
- Parallel processing (75 concurrent)
- Fixed cooldown (10 seconds)
- Logs all retry attempts

---

#### Queue System All-Stage Retry

**L1 Retry (Firecrawl API):**
```python
# File: queue_system/scripts/l1_crawl_with_markdown/fetch_segments_robust.py

MAX_ATTEMPTS = 10
BASE_BACKOFF = 2  # seconds

for attempt in range(1, MAX_ATTEMPTS + 1):
    try:
        response = requests.get(url, headers=headers, timeout=30)

        if response.status_code == 200:
            return response.json()
        elif response.status_code == 429:  # Rate limit
            backoff = BASE_BACKOFF ** attempt + random.uniform(0, 1)
            print(f"Rate limit, retry in {backoff}s")
            time.sleep(backoff)
        else:
            print(f"Error {response.status_code}, retry {attempt}/{MAX_ATTEMPTS}")
            time.sleep(BASE_BACKOFF ** attempt)
    except requests.exceptions.Timeout:
        backoff = BASE_BACKOFF ** attempt + random.uniform(0, 1)
        print(f"Timeout, retry in {backoff}s")
        time.sleep(backoff)
    except Exception as e:
        print(f"Error: {e}, retry {attempt}/{MAX_ATTEMPTS}")
        time.sleep(BASE_BACKOFF ** attempt)

print("All retry attempts failed")
return None  # Graceful failure
```

**L3 Retry (LLM Classification):**
```bash
# File: queue_system/scripts/l3_llm_classify_extract/scripts/classify_chunk_robust.sh

MAX_ATTEMPTS=10
BASE_BACKOFF=2

for attempt in $(seq 1 $MAX_ATTEMPTS); do
  # Try classification
  response=$(curl -s ... Anthropic API)

  if [ $? -eq 0 ]; then
    # Success
    echo "$response" > response_file.json
    exit 0
  else
    # Failed, calculate backoff
    backoff=$(echo "2^$attempt + ($RANDOM % 1000) / 1000" | bc)
    echo "Attempt $attempt failed, retry in ${backoff}s"
    sleep $backoff
  fi
done

echo "All retry attempts failed for chunk"
exit 1  # Mark chunk as failed
```

**Key Features:**
- Exponential backoff (2^attempt seconds)
- Jitter (random 0-1 second) prevents thundering herd
- Timeout handling
- Graceful degradation (continues with partial results)

---

## Performance & Costs

### Typical Performance Metrics

**Test Case:** 5,000-page website

| Stage | Time | Cost | Notes |
|-------|------|------|-------|
| **L1: Crawl** | 30-60 min | ~$50 | Depends on page size, concurrency |
| **L2: Merge/Chunk** | 1-2 min | $0 | CPU only |
| **L3: LLM Classify** | 20-40 min | ~$20 | Depends on retry cycles |
| **L4: Dedupe/Export** | 1-2 min | $0 | CPU only |
| **TOTAL** | **1-2 hours** | **~$70** | End-to-end |

**Output:** 1,000-2,000 companies with 90-95% domain coverage

### Cost Breakdown

**Firecrawl (L1):**
- $0.01 per page crawled
- 5,000 pages = $50
- 20,000 page limit = $200 max

**Anthropic Claude (L3):**
- ~$0.002-0.01 per chunk (average)
- 5,000 pages = 5,000 chunks = $10-$50
- Dense pages cost more (more tokens)

**Total per website:**
- Small (500 pages): ~$10
- Medium (5,000 pages): ~$70
- Large (20,000 pages): ~$250

### Performance Tuning

**Faster Crawling:**
```bash
# Increase concurrency (in run_pipeline.sh)
"maxConcurrency": 100  # Default: 50
# Warning: May hit rate limits or get blocked
```

**Faster LLM Processing:**
```bash
# Increase concurrency (in classify_all_with_retry.sh)
MAX_CONCURRENT=150  # Default: 75
# Warning: May hit rate limits (400k tokens/min)
```

**Lower Cost:**
```bash
# Use cheaper model (in classify_chunk.sh)
MODEL="claude-3-5-haiku-20241022"  # ~70% cheaper, ~10% less accurate
```

**Lower Cost (Crawl):**
```bash
# Reduce page limit (in run_pipeline.sh)
"limit": 5000  # Default: 10000 (main), 20000 (queue)
```

---

## Known Issues & Solutions

### Issue: Claude Stops Early on Dense Pages

**Description:**
When a page has 100+ companies, Claude may extract only 44-87% due to token limits.

**Solution:**
Use OpenAI GPT-4o for dense list pages (see LEARNINGS.md):
```bash
# In classify_chunk.sh, change model:
MODEL="gpt-4o-2024-08-06"
# and use JSON Schema for validation
```

**Alternative:**
Split large pages using Erudus splitting approach (10 sub-chunks per page).

---

### Issue: Individual Pages Have No Company Website

**Description:**
Individual company profile pages often don't display the company's own website.

**Root Cause:**
- Website not in crawled markdown
- Website rendered by JavaScript
- Website on separate "Contact" page

**Solution:**
1. Accept lower domain extraction rate (~50-70% for individual pages)
2. Use contact page scraping (if Firecrawl supports deeper crawling)
3. Supplement with external data (Google search, LinkedIn)

---

### Issue: Directory URLs Extracted Instead of Company URLs

**Description:**
LLM extracts "example.com/directory/company-name" instead of "company.com"

**Root Cause:**
- Page doesn't have company's own website
- LLM forced to extract something (JSON Schema strict mode)

**Solution:**
- Use Claude (more conservative, leaves website empty if not found)
- Don't use OpenAI with JSON Schema strict mode on individual pages

---

### Issue: Python File I/O Not Working

**Description:**
Python scripts can't read/write files.

**Root Cause:**
Using Homebrew Python (`/opt/homebrew/bin/python3`) which has sandbox restrictions.

**Solution:**
Use system Python:
```bash
# All scripts already use:
/usr/bin/python3

# If you modified scripts, change to:
#!/usr/bin/env python3  # WRONG
#!/usr/bin/python3      # CORRECT
```

---

### Issue: Queue Manager Not Processing Jobs

**Description:**
Queue has jobs but manager isn't starting them.

**Root Cause:**
- Manager not running
- Manager crashed
- active.json corrupted

**Solution:**
```bash
# Check if manager running
ps aux | grep queue_manager

# If not running, restart
./queue_system/queue_manager.sh &

# If active.json corrupted, reset it
echo "{}" > queue_system/queue/active.json
```

---

### Issue: High Failure Rate in Queue

**Description:**
Many jobs failing (50%+ in failed.txt).

**Root Cause:**
- Invalid API keys
- Rate limits
- Bad URLs (404, auth required)

**Solution:**
```bash
# Check common failure pattern
cat queue_system/queue/failed.txt

# Check logs for specific errors
cat queue_system/queue/logs/*.log | grep "ERROR"

# If API key issue, fix .env
cat > .env <<EOF
FIRECRAWL_API_KEY=fc-xxxxxxxx
ANTHROPIC_API_KEY=sk-ant-xxxxxxxx
EOF

# Re-add failed jobs
cat queue_system/queue/failed.txt | while IFS='|' read job url timestamp; do
    IFS='/' read client domain <<< "$job"
    ./queue_system/queue_add.sh "$client" "$url"
done
```

---

## Development History

### Timeline

**2025-10-22:** Production system ready
- Validated on ACHR directory (4,472 pages)
- 97.89% classification success
- 93.1% domain extraction
- Cost: ~$65

**2025-10-23:** Model comparison testing
- Tested OpenAI GPT-4o vs Claude Sonnet
- Identified strengths/weaknesses of each model
- Documented in LEARNINGS.md
- Conclusion: Hybrid approach best (OpenAI for lists, Claude for individual pages)

**2025-10-24:** Erudus large page handling
- Implemented split_erudus scripts
- Successfully processed 1,684 companies on single page

**2025-10-26:** Queue system development
- Built robust queue system with retry logic
- Added pre-flight checks
- Isolated outputs from main pipeline
- Comprehensive logging

**2025-10-27:** Batch processing validation
- Tested queue system on multiple websites (fooddirectory, totalfood, specialtyfood)
- Successfully processed 9 websites with 3,316 total companies
- Created master combined CSV

**2025-10-28:** Complete documentation
- Created COMPLETE_PIPELINE_DOCUMENTATION.md
- Documented all pipeline types and components
- Prepared for next agent handoff

### Key Learnings

See LEARNINGS.md for detailed testing insights, including:
- OpenAI GPT-4o vs Claude Sonnet comparison
- Exhaustive extraction prompt testing
- Website structure impact on extraction
- Model-specific strengths and weaknesses

### Future Enhancements

- [ ] Hybrid model routing (OpenAI for lists, Claude for individual)
- [ ] Web UI for queue management
- [ ] Email notifications on completion/failure
- [ ] Parallel job execution with configurable concurrency
- [ ] Contact page deep-crawling for missing websites
- [ ] External data enrichment (Google, LinkedIn APIs)

---

## Quick Reference

### Most Common Commands

```bash
# ========================================
# MAIN PIPELINE (Single URL)
# ========================================

# Run pipeline
./run_pipeline.sh "https://example.com/directory"

# Check results
cat l4_dedupe_and_export/outputs/default/example/*.csv

# Monitor L3 progress
ls l3_llm_classify_extract/outputs/default/example/llm_responses/ | wc -l

# ========================================
# QUEUE SYSTEM (Batch Processing)
# ========================================

# Add jobs
./queue_system/queue_add.sh "client" "https://example.com"

# Start manager
./queue_system/queue_manager.sh &

# Check status
./queue_system/queue_status.sh

# Monitor logs
tail -f queue_system/queue/manager.log
tail -f queue_system/queue/logs/client_domain.log

# Check results
ls queue_system/outputs/client/domain/*.csv

# Re-add failed jobs
cat queue_system/queue/failed.txt | while IFS='|' read job url ts; do
    IFS='/' read client domain <<< "$job"
    ./queue_system/queue_add.sh "$client" "$url"
done

# ========================================
# TROUBLESHOOTING
# ========================================

# Check API keys
cat .env

# Check disk space
df -h .

# Check running processes
ps aux | grep queue_manager
ps aux | grep python3

# Count segments/chunks/responses
find . -name "segment_*.json" | wc -l
find . -name "chunk_*.json" | wc -l
find . -name "response_chunk_*.json" | wc -l

# Check for errors
grep -r "ERROR" logs/
grep -r "rate limit" logs/
```

---

**END OF DOCUMENTATION**

For questions or issues, refer to:
- README.md - Overview
- QUICKSTART.md - Getting started
- QUEUE.md - Queue system details
- LEARNINGS.md - Model testing insights
- FOR_AI_AGENTS.md - AI agent guide
