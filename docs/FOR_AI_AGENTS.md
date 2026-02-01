# Documentation for AI Agents

**This folder contains a production-ready, general-purpose company scraping pipeline.**

---

## What This System Does

**Input:** Any website URL with company listings  
**Output:** CSV with company names and domains  
**Approach:** Crawl → LLM classification → Extraction → Deduplication

---

## How It Works

### L1: Crawl with Markdown
- Uses Firecrawl /v2/crawl endpoint
- Extracts markdown (onlyMainContent: true)
- Crawls up to 10,000 pages
- Concurrency: 50 (for speed)
- **Output:** Segmented JSON files with all pages

### L2: Merge and Chunk
- Merges all crawl segments into single dataset
- Splits into 1-page chunks for LLM processing
- **Why 1 page per chunk:** Better extraction accuracy
- **Output:** Individual JSON files (chunk_0001.json, chunk_0002.json, etc.)

### L3: LLM Classify & Extract
- Uses Claude 3.5 Sonnet
- Each chunk classified as: company_individual, company_list, navigation, other
- Extracts: company name + website domain
- **Progressive retry:** Handles rate limits automatically (up to 10 cycles)
- **Concurrency:** 75 (safe for 400k token/min limit)
- **Output:** Classification JSON for each chunk

### L4: Dedupe and Export
- Deduplicates by domain first, then normalized name
- Normalizes domains (removes http, www, paths)
- Normalizes names (handles "Inc." vs "Inc")
- Filters out listing URLs (keeps only actual company domains)
- **Output:** Clean CSV ready to use

---

## Key Design Principles

1. **GENERALIZED** - No website-specific logic, no hardcoded patterns
2. **RESILIENT** - Auto-retries rate limits, handles errors
3. **PORTABLE** - All paths relative, works anywhere
4. **SELF-CONTAINED** - All code, prompts, docs included

---

## The Prompt (Most Important!)

**Location:** `PROMPT.md` and `l3_llm_classify_extract/scripts/classify_chunk.sh`

**Key instructions:**
- Extract COMPANY'S OWN domain (not directory URL)
- Look for "Website:", http links in markdown
- If no domain found, return empty string
- Classify pages into 4 categories

**This prompt is what makes it work on any website!**

---

## File Structure

```
firecrawl_playground_prod/
├── run_pipeline.sh              ⭐ RUN THIS
├── README.md                    Overview
├── QUICKSTART.md                How to use
├── PROMPT.md                    The LLM prompt
├── CONFIG.md                    Configuration guide
├── FOR_AI_AGENTS.md            ⭐ YOU ARE HERE
│
├── l1_crawl_with_markdown/
│   ├── fetch_segments.py        ← Polls Firecrawl, saves segments
│   └── outputs/segments/        ← Crawl data
│
├── l2_merge_and_chunk/
│   ├── merge_and_split.py       ← Merges + creates 1-page chunks
│   └── outputs/chunks/          ← Ready for LLM
│
├── l3_llm_classify_extract/
│   ├── scripts/
│   │   └── classify_chunk.sh    ← Claude API call (1 chunk)
│   ├── classify_all_with_retry.sh  ← Processes all chunks with retry
│   └── outputs/llm_responses/   ← Classification results
│
└── l4_dedupe_and_export/
    ├── export_final.py          ← Dedupes + normalizes + exports
    └── outputs/                 ← FINAL CSV HERE
        └── final_companies_*.csv
```

---

## Configuration Requirements

**Must have `.env` file:**
```bash
FIRECRAWL_API_KEY=fc-xxx
ANTHROPIC_API_KEY=sk-ant-xxx
```

**Place .env in:**
- Project root (`firecrawl_playground_prod/.env`), OR
- Parent directory (scripts check both)

---

## Python Version Critical!

**MUST use:** `/usr/bin/python3` (system Python)  
**NOT:** `/opt/homebrew/bin/python3` (has sandbox file I/O issues)

**All scripts hardcode:** `/usr/bin/python3`

---

## Rate Limits & Retry Logic

**Anthropic limits (typical):**
- 400,000 tokens per minute
- Can't ramp 0→500 instantly (acceleration limit)

**Our solution:**
- 75 concurrent (safe for 400k/min)
- Progressive retry: Cycle 1-10 retries failures
- 10-second cooldown between cycles
- Checks for `.content` vs `.error` in responses

**Success rate:** 97.89% after retries

---

## Common Issues & Solutions

**Issue:** "Rate limit exceeded"  
**Solution:** Auto-retries, just wait. Takes 7 cycles typically.

**Issue:** "Python file I/O not working"  
**Solution:** Use `/usr/bin/python3`, not homebrew Python

**Issue:** "No companies extracted"  
**Solution:** Check if target URL actually has company data

**Issue:** "Low domain extraction rate (<50%)"  
**Solution:** Pages may not have actual company websites, only names

---

## Testing History

**Validated on:** ACHR HVACR Directory  
**Pages crawled:** 4,472  
**Companies found:** 1,412  
**With domains:** 1,314 (93.1%)  
**Classification success:** 97.89%  
**Cost:** ~$65

---

## To Adapt for Different Use Cases

**Change crawl scope:**
- Edit `run_pipeline.sh` line ~50
- Adjust: `limit`, `maxDiscoveryDepth`, `includePaths`

**Change LLM model:**
- Edit `classify_chunk.sh` line ~102
- Current: `claude-3-5-sonnet-20241022`
- Cheaper: `claude-3-5-haiku-20241022` (less accurate)

**Change prompt:**
- Edit `classify_chunk.sh` line ~35-95
- Or reference `PROMPT.md` for current version
- Test changes on sample pages first!

---

## For Another Agent

**You can:**
1. Copy entire folder to new location
2. Create `.env` with API keys
3. Run `./run_pipeline.sh <url>`
4. Get results

**Everything self-contained:**
- ✅ All code included
- ✅ All prompts documented
- ✅ All paths relative
- ✅ All docs explain everything

---

## Success Criteria

**95% confidence threshold:**
- Classification: >95% success
- Domain extraction: >90%
- No manual intervention

**Achieved in testing:** ✅ 97.89% classification, 93.1% domains

---

**This system is READY TO USE on any website with company listings!**

