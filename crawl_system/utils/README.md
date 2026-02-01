# Utilities

Helper scripts for specialized tasks and analysis.

---

## Directory Structure

```
utils/
├── erudus/          # Large single-page list splitting
└── analysis/        # Extraction analysis tools
```

---

## Erudus Scripts

**Purpose:** Handle websites with 1,000+ companies on a SINGLE page

**Problem:** Normal chunking creates one massive chunk → LLM stops early, misses companies

**Solution:** Split single large page into multiple smaller chunks for better LLM processing

### Scripts

**`split_erudus_simple.py`** - Recommended
```bash
/usr/bin/python3 utils/erudus/split_erudus_simple.py
```

Splits large single-page lists into 10 manageable chunks:
- Chunk 1: Header + Wholesalers section (if exists)
- Chunks 2-10: Manufacturers split evenly (~165 companies each)

**Input:** `l2_merge_and_chunk/outputs/{client}/erudus/chunks/chunk_0001.json`
**Output:** Same directory, overwrites with 10 new chunks

**`split_erudus.py`** - Advanced version with section detection

**`export_erudus_simple.py`** - Custom export for Erudus format

### Usage Example

```bash
# Run normal pipeline first (creates 1 massive chunk)
export CLIENT="openinfo"
export DOMAIN="erudus"
./run_pipeline.sh "https://erudus.com/approved-suppliers"

# Split the massive chunk
cd utils/erudus
/usr/bin/python3 split_erudus_simple.py
cd ../..

# Continue pipeline from L3
./main_pipeline/l3_llm_classify_extract/classify_all_with_retry.sh
/usr/bin/python3 ./main_pipeline/l4_dedupe_and_export/export_final.py
```

### When to Use

- Website has 500+ companies on ONE page
- L3 classification shows low extraction rate (<50%)
- You see "Counted 1000 but extracted 440" in logs

---

## Analysis Scripts

**Purpose:** Debug extraction failures and analyze data quality

### Scripts

**`analyze_empty_websites_by_type.py`**

Analyzes companies without websites by classification type:

```bash
/usr/bin/python3 utils/analysis/analyze_empty_websites_by_type.py
```

Output:
```
COMPANY_INDIVIDUAL:
  Total: 123
  With website: 78 (63%)
  WITHOUT website: 45 (37%)

COMPANY_LIST:
  Total: 456
  With website: 444 (97%)
  WITHOUT website: 12 (3%)
```

**Note:** Hardcoded path to specific output directory (line 4) - edit before running

---

**`check_extraction_failure.py`**

Checks why specific chunks failed extraction:

```bash
/usr/bin/python3 utils/analysis/check_extraction_failure.py
```

Looks for:
- Pages with markdown links but no extracted companies
- Mismatches between available data and extracted data

**Note:** Hardcoded paths (lines 6-7) - edit before running

---

**`find_directory_page_failures.py`**

Finds companies where directory URL was extracted instead of company website:

```bash
/usr/bin/python3 utils/analysis/find_directory_page_failures.py
```

Example bad extraction:
- ❌ Wrong: `thewholesaler.co.uk/company/acme` (directory URL)
- ✅ Right: `acme.com` (company's own domain)

**Note:** Hardcoded paths - edit before running

---

**`find_empty_websites.py`**

Simple count of companies without websites:

```bash
/usr/bin/python3 utils/analysis/find_empty_websites.py
```

Output:
```
Total companies: 567
With websites: 523 (92%)
Without websites: 44 (8%)
```

**Note:** Hardcoded paths - edit before running

---

## Important Notes

⚠️ **All analysis scripts have hardcoded paths** to specific output directories

Before running:
1. Edit the script
2. Update paths on lines 4-7 (varies by script)
3. Point to your actual output directory

Example:
```python
# Change this:
responses_dir = Path("l3_llm_classify_extract/outputs/openinfo/unitaswholesale/llm_responses")

# To this:
responses_dir = Path("main_pipeline/l3_llm_classify_extract/outputs/myclient/mydomain/llm_responses")
```

---

## System Python Requirement

All scripts use system Python:
```bash
/usr/bin/python3
```

**Do not use:**
- `/opt/homebrew/bin/python3` (sandbox issues)
- `python3` (may resolve to homebrew)

---

For complete documentation, see [`../docs/COMPLETE_PIPELINE_DOCUMENTATION.md`](../docs/COMPLETE_PIPELINE_DOCUMENTATION.md)
