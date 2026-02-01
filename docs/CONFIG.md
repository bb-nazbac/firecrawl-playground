# Configuration Guide

## API Keys Setup

**Create `.env` file in project root:**

```bash
# Location: /path/to/firecrawl_playground_prod/.env
FIRECRAWL_API_KEY=fc-your-key-here
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

**Or set environment variables:**
```bash
export FIRECRAWL_API_KEY="fc-xxx"
export ANTHROPIC_API_KEY="sk-ant-xxx"
```

---

## Pipeline Configuration

**All configurable values are in `run_pipeline.sh`**

### Crawl Settings (L1)
```bash
CRAWL_LIMIT=10000          # Max pages to crawl
CRAWL_CONCURRENCY=50       # Parallel crawl requests
CRAWL_DEPTH=5              # How deep to go
```

### LLM Settings (L3)
```bash
LLM_MODEL="claude-3-5-sonnet-20241022"
LLM_CONCURRENCY=75         # Must be ≤ token_limit/4000
MAX_RETRY_CYCLES=10        # How many retry attempts
```

### Rate Limits
**Your Anthropic limits:**
- Tokens per minute: 400,000
- Max safe concurrency: ~80-100 (with 4k tokens per chunk)

**If you hit limits:**
- Reduce `LLM_CONCURRENCY` to 50
- Increase wait time between cycles

---

## System Requirements

**Python:**
- Use system Python: `/usr/bin/python3`
- NOT homebrew Python (has sandbox issues)

**Shell:**
- bash (zsh works too)
- Requires: `jq`, `curl`, `bc`

**Disk Space:**
- ~1GB per 5,000 pages crawled
- Cleanup old runs if needed

---

## File Locations

**All paths are RELATIVE to script location:**
```bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
```

**This means:** Copy folder anywhere, it still works! ✅

---

## Customization

**Change the prompt:**
Edit: `l3_llm_classify_extract/scripts/classify_chunk.sh`
Line ~35: The PROMPT variable

**Change deduplication logic:**
Edit: `l4_dedupe_and_export/export_final.py`
Function: `normalize_company_name()`

**Change crawl filters:**
Edit: `run_pipeline.sh`
Add: `"includePaths": ["^/directory/.*$"]`

