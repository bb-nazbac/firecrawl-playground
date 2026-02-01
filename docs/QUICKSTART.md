# Quick Start Guide

## Run the Pipeline

### Option 1: Single URL (Direct Execution)

**One command:**
```bash
./run_pipeline.sh "https://YOUR-TARGET-SITE.com/directory"
```

**That's it!** The pipeline will:
1. Crawl the site (gets all pages with markdown)
2. Merge and chunk (1 page per chunk)
3. LLM classify (Claude extracts companies)
4. Dedupe and export (clean CSV)

### Option 2: Multiple URLs (Queue System)

**For processing multiple sites unattended:**

```bash
# 1. Add jobs to queue
./queue_add.sh myclient "https://site1.com/directory"
./queue_add.sh myclient "https://site2.com/suppliers"
./queue_add.sh myclient "https://site3.com/members"

# 2. Start queue manager (background)
./queue_manager.sh &

# 3. Monitor progress
./queue_status.sh
```

**The queue system will:**
- Process jobs one at a time (respects API rate limits)
- Track progress automatically
- Log all activity to `queue/manager.log`
- Handle failures gracefully

**See [QUEUE.md](QUEUE.md) for full queue documentation.**

---

## Get Results

**Output file:**
```bash
cat l4_dedupe_and_export/outputs/final_companies_*.csv
```

**Columns:**
- `name` - Company name
- `domain` - Normalized domain (e.g., `company.com`)
- `website_original` - Full URL from extraction
- `classification_type` - How it was found
- `source_file` - LLM response file

---

## Expected Time

**For ~5,000 page site:**
- L1 Crawl: ~5-10 minutes
- L2 Merge: ~1 minute
- L3 LLM: ~30-45 minutes (with retries)
- L4 Export: ~1 minute

**Total: ~45-60 minutes**

---

## Expected Cost

**For ~5,000 page site:**
- Crawl: ~$50 (1 credit per page)
- LLM: ~$20 (Claude Sonnet)
- **Total: ~$70**

---

## Success Rates (From Testing)

- Classification: 97.89% success
- Domain extraction: 93.1% of companies
- Deduplication: Aggressive (removes name variations)

---

## Requirements

1. API keys in `/Users/bahaa/Documents/Clients/Toolbx/.env`:
   ```
   FIRECRAWL_API_KEY=fc-xxx
   ANTHROPIC_API_KEY=sk-xxx
   ```

2. System Python: `/usr/bin/python3` (not homebrew)

3. Dependencies: curl, jq, bash

---

## Monitoring Progress

**Check logs:**
```bash
tail -f pipeline_run_*.log
```

**Check L3 progress:**
```bash
ls l3_llm_classify_extract/outputs/llm_responses/ | wc -l
```

---

## Troubleshooting

**If rate limits hit:**
- Pipeline auto-retries up to 10 cycles
- Uses 75 concurrent (safe for 400k token/min limit)
- Gradual cooldown between cycles

**If crawl times out:**
- Increase limit in `run_pipeline.sh`
- Or adjust `maxDiscoveryDepth`

---

**Built and validated on ACHR directory (extracted 1,412 companies with 93.1% domain capture)**

