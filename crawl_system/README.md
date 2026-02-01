# Firecrawl Crawl System

**Purpose:** Web scraping and company data extraction pipeline using Firecrawl API

**Version:** 2.0 (Reorganized November 2025)

---

## Overview

The Crawl System is a production-grade data extraction pipeline that:
- Crawls websites using Firecrawl v2 API
- Extracts company information using Claude Sonnet 4.5
- Manages multiple concurrent scrape jobs via queue system
- Organizes outputs by client and domain

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  CRAWL SYSTEM PIPELINE                                      │
└─────────────────────────────────────────────────────────────┘
           │
           ├─→ L1: Firecrawl API Crawl
           │   ├─ Input: Target URL
           │   └─ Output: Markdown pages (segments)
           │
           ├─→ L2: Merge & Chunk
           │   ├─ Input: L1 segments
           │   └─ Output: Chunked pages (1 page per chunk)
           │
           ├─→ L3: LLM Classification & Extraction
           │   ├─ Input: L2 chunks
           │   └─ Output: Classified company data (JSON)
           │
           └─→ L4: Dedupe & Export
               ├─ Input: L3 responses
               └─ Output: Final CSV + JSON
```

## Quick Start

### Add a Scrape Job

```bash
./queue_system/queue_add.sh "ClientName" "https://example.com/directory"
```

### Check Queue Status

```bash
./queue_system/queue_status.sh
```

### Start Queue Manager (if not running)

```bash
nohup ./queue_system/queue_manager.sh > queue_system/logs/queue_manager.log 2>&1 &
```

## Directory Structure

```
crawl_system/
├── queue_system/           # Job queue & orchestration
│   ├── queue/              # Queue state files
│   ├── outputs/            # Per-job outputs
│   ├── logs/               # Per-job logs
│   ├── scripts/            # Pipeline scripts
│   ├── queue_add.sh        # Add job to queue
│   ├── queue_status.sh     # Check queue status
│   └── queue_manager.sh    # Process jobs serially
│
├── main_pipeline/          # Original single-job pipeline (legacy)
│   └── l1_crawl_with_markdown/
│
├── client_outputs/         # Final CSVs organized by client
│   ├── ClientName/
│   │   ├── domain1/
│   │   │   └── domain1_timestamp.csv
│   │   └── domain2/
│   │       └── domain2_timestamp.csv
│
├── utils/                  # Shared utilities
│   └── l3_llm_classify_extract/
│       └── classify_all_with_retry.sh
│
├── run_pipeline.sh         # Single-job pipeline runner (legacy)
└── README.md               # This file
```

## Firecrawl Configuration

### Current Settings (queue_system/scripts/run_pipeline_robust.sh:159-174)

```json
{
  "url": "$TARGET_URL",
  "allowSubdomains": true,
  "limit": 20000,
  "maxConcurrency": 50,
  "maxDiscoveryDepth": 5,
  "allowExternalLinks": false,
  "scrapeOptions": {
    "formats": ["markdown"],
    "onlyMainContent": true,
    "blockAds": true
  }
}
```

### Parameters Explained

- **allowSubdomains: true** - Crawls subdomains (e.g., blog.example.com)
- **limit: 20000** - Maximum 20,000 pages per crawl
- **maxConcurrency: 50** - Process up to 50 pages simultaneously
- **maxDiscoveryDepth: 5** - Follow links up to 5 clicks deep
- **allowExternalLinks: false** - Stay on same domain + subdomains
- **formats: ["markdown"]** - Return content as markdown
- **onlyMainContent: true** - Extract main content only
- **blockAds: true** - Remove advertisements

## Outputs

### Final CSV Format

```csv
name,domain,website_original,classification_type,source_file
Company Name,companyname.com,https://www.companyname.com/,company_list,response_chunk_0001.json
```

### Output Locations

1. **Pipeline Outputs** (per-job):
   - `queue_system/outputs/ClientName/domain/`
   - Contains: segments, chunks, llm_responses, final CSV/JSON

2. **Client Outputs** (consolidated):
   - `client_outputs/ClientName/domain/`
   - Contains: Final CSV only (automatically copied)

## Recent Scrapes (November 2025)

### Doppel Client

| Domain | Companies | Domains | Success Rate |
|--------|-----------|---------|--------------|
| paginasamarillas.es | 10,747 | 3,171 | 29% |
| rentechdigital.com | 7,279 | 3,656 | 50% |
| whatclinic.com | 953 | 16 | 1.7% |
| clinicinspain (cosmetic) | 11 | 11 | 100% |
| clinicinspain-dental | 48 | 27 | 56% |
| clinicinspain-implants | 15 | 14 | 93% |

**Total:** 19,053 companies, 6,895 domains (36%)

### Toolbx Client

| Domain | Companies | Domains | Success Rate |
|--------|-----------|---------|--------------|
| eweb.phccweb.org | 225 | 188 | 84% |
| phccconnect2025 | 93 | 86 | 92% |

**Total:** 318 companies, 274 domains (86%)

## Environment Variables

Required in root `.env`:

```bash
FIRECRAWL_API_KEY=fc-xxxxx
ANTHROPIC_API_KEY=sk-ant-xxxxx
```

## Queue System Details

### Job Lifecycle

1. **QUEUED** - Added to `queue/queue.txt`
2. **ACTIVE** - Processing (recorded in `queue/active.json`)
3. **COMPLETED** - Finished successfully (logged in `queue/completed.txt`)
4. **FAILED** - Error occurred (logged in `queue/failed.txt`)

### Logs

- **Queue Manager:** `queue_system/logs/queue_manager.log`
- **Per-Job Logs:** `queue_system/logs/ClientName/domain/domain_timestamp.log`

### Manual Queue Operations

```bash
# View queue file directly
cat queue_system/queue/queue.txt

# View completed jobs
cat queue_system/queue/completed.txt

# View failed jobs
cat queue_system/queue/failed.txt

# Check active job
cat queue_system/queue/active.json
```

## Known Issues & Limitations

### Directory Sites

Sites like **whatclinic.com** (clinic directory) have low domain extraction rates because:
- Clinic websites not consistently displayed as text
- Require clicking into detail pages
- Website URLs often in buttons/links (not markdown)

**Solution:** Use sites where websites are clearly displayed (e.g., clinicinspain.com = 70-100% success)

### Failed Crawls

1. **doctoralia.es** - Timeout (empty response)
   - Issue: `curl -s` suppresses errors, no timeout configured

2. **dnb.com** - Anti-bot protection
   - Heavy rate limiting, 502 errors
   - Crawl too slow (1,202/4,725 pages in 2 hours)

## Troubleshooting

### Queue Not Processing

```bash
# Check if queue manager running
ps aux | grep queue_manager

# Restart queue manager
pkill -f queue_manager.sh
nohup ./queue_system/queue_manager.sh > queue_system/logs/queue_manager.log 2>&1 &
```

### Check Job Status

```bash
# View latest log
tail -50 queue_system/logs/ClientName/domain/domain_timestamp.log

# Monitor active crawl
watch -n 5 'tail -20 queue_system/logs/queue_manager.log'
```

### Re-run Failed Job

```bash
# Remove from failed.txt
grep -v "ClientName/domain" queue_system/queue/failed.txt > temp && mv temp queue_system/queue/failed.txt

# Add back to queue
./queue_system/queue_add.sh "ClientName" "https://example.com"
```

## Migration Notes

**November 4, 2025:** Reorganized into `/crawl_system` subfolder to prepare for `/search_system` development.

- All path references use relative paths (no changes needed)
- Queue system tested and operational from new location
- Existing outputs verified accessible

---

**Built with:** Firecrawl v2 API + Claude Sonnet 4.5
**Maintained by:** OPTIMUS PRIME Protocol
