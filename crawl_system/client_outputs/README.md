# Client Outputs

**Centralized location for all final CSVs, organized by client and domain**

---

## What This Is

This directory contains **copies** of all final CSV outputs from both pipeline systems, organized for easy access by client name.

**Structure:**
```
client_outputs/
└── {client_name}/
    └── {domain}/
        └── {domain}_{timestamp}.csv
```

---

## How It Works

### Automatic CSV Copying

After each pipeline completes L4 (Dedupe & Export), the final CSV is **automatically copied** here:

**Main Pipeline:**
```bash
# Original: main_pipeline/l4_dedupe_and_export/outputs/{client}/{domain}/{domain}_{timestamp}.csv
# Copy to:  client_outputs/{client}/{domain}/{domain}_{timestamp}.csv
```

**Queue System:**
```bash
# Original: queue_system/outputs/{client}/{domain}/{domain}_{timestamp}.csv
# Copy to:  client_outputs/{client}/{domain}/{domain}_{timestamp}.csv
```

---

## Example Structure

```
client_outputs/
├── foodco/
│   ├── totalfood/
│   │   └── totalfood_20251027_120000.csv
│   ├── specialtyfood/
│   │   └── specialtyfood_20251027_130000.csv
│   └── fooddirectory/
│       └── fooddirectory_20251027_140000.csv
├── test/
│   └── example/
│       └── example_20251028_100000.csv
└── default/
    └── acme/
        └── acme_20251028_110000.csv
```

---

## Benefits

✅ **Easy access** - All CSVs for a client in one place
✅ **Organized** - By client, then by domain
✅ **Preserved** - Original outputs remain untouched
✅ **Automatic** - No manual copying needed
✅ **Cross-pipeline** - Works with both main and queue systems

---

## Setting Client Name

### Main Pipeline

```bash
export CLIENT="mycompany"
./run_pipeline.sh "https://example.com/directory"

# CSV copied to: client_outputs/mycompany/example/example_20251028_120000.csv
```

**Default:** If `CLIENT` not set, uses `"default"`

### Queue System

```bash
cd queue_system
./queue_add.sh "mycompany" "https://example.com/directory"

# CSV copied to: client_outputs/mycompany/example/example_20251028_120000.csv
```

**Note:** First parameter to `queue_add.sh` is the client name

---

## Original Outputs Still Preserved

**All original pipeline outputs remain in their original locations:**

**Main Pipeline:**
- Segments: `main_pipeline/l1_crawl_with_markdown/outputs/{client}/{domain}/`
- Chunks: `main_pipeline/l2_merge_and_chunk/outputs/{client}/{domain}/`
- LLM Responses: `main_pipeline/l3_llm_classify_extract/outputs/{client}/{domain}/`
- Final CSV/JSON: `main_pipeline/l4_dedupe_and_export/outputs/{client}/{domain}/`

**Queue System:**
- All stages: `queue_system/outputs/{client}/{domain}/`

The `client_outputs/` folder contains **only CSVs**, copied for convenience.

---

## CSV Format

All CSVs have the same format:

```csv
name,domain,website_original,classification_type,source_file
Acme Corp,acme.com,https://www.acme.com,company_individual,chunk_0042
Beta Inc,beta.com,www.beta.com/,company_list,chunk_0015
```

**Columns:**
- `name` - Company name
- `domain` - Normalized domain (no http, www, paths)
- `website_original` - Original website as extracted
- `classification_type` - Page type (company_individual, company_list, navigation, other)
- `source_file` - Which chunk this came from

---

## Finding All CSVs for a Client

```bash
# List all CSVs for a client
ls -la client_outputs/mycompany/*/*.csv

# Count total companies across all domains
cat client_outputs/mycompany/*/*.csv | tail -n +2 | wc -l

# Combine all CSVs for a client (with header once)
head -1 client_outputs/mycompany/*/$(ls client_outputs/mycompany/*/ | head -1) > mycompany_all.csv
tail -n +2 -q client_outputs/mycompany/*/*.csv >> mycompany_all.csv
```

---

## Cleanup

To remove old outputs:

```bash
# Remove all CSVs older than 30 days
find client_outputs/ -name "*.csv" -mtime +30 -delete

# Remove specific client
rm -rf client_outputs/oldclient/

# Remove specific domain
rm -rf client_outputs/mycompany/olddomain/
```

---

## JSON Files

**Note:** Only CSV files are copied to `client_outputs/`.

JSON files remain in the original pipeline outputs:
- Main: `main_pipeline/l4_dedupe_and_export/outputs/{client}/{domain}/{domain}_{timestamp}.json`
- Queue: `queue_system/outputs/{client}/{domain}/{domain}_{timestamp}.json`

JSON files contain:
- Full company data
- Metadata (counts, timestamps)
- All fields from CSV plus additional info

---

For complete pipeline documentation, see [`docs/COMPLETE_PIPELINE_DOCUMENTATION.md`](../docs/COMPLETE_PIPELINE_DOCUMENTATION.md)
