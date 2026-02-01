# Client Outputs Feature

**Date Added:** 2025-10-28
**Feature:** Automatic CSV copying to centralized client folder

---

## What Was Added

A new `client_outputs/` directory at repository root where all final CSVs are automatically copied after pipeline completion.

### Structure

```
client_outputs/
└── {client_name}/
    └── {domain}/
        └── {domain}_{timestamp}.csv
```

**Example:**
```
client_outputs/
├── foodco/
│   ├── totalfood/
│   │   └── totalfood_20251027_120000.csv
│   └── specialtyfood/
│       └── specialtyfood_20251027_130000.csv
└── test/
    └── example/
        └── example_20251028_100000.csv
```

---

## How It Works

### Automatic Copying

After L4 (Dedupe & Export) completes, the pipeline automatically:
1. Creates directory: `client_outputs/{CLIENT}/{DOMAIN}/`
2. Copies CSV from original location to client_outputs
3. Logs the copy action

**Both pipeline systems supported:**
- Main pipeline (`run_pipeline.sh`)
- Queue system (`queue_system/scripts/run_pipeline_robust.sh`)

---

## Implementation Details

### Main Pipeline (run_pipeline.sh)

**Added lines 138-149:**
```bash
# Copy CSV to client_outputs folder for easy access
FINAL_CSV="$BASE_DIR/main_pipeline/l4_dedupe_and_export/outputs/$CLIENT/$DOMAIN/${DOMAIN}_${TIMESTAMP}.csv"
CLIENT_OUTPUTS_DIR="$BASE_DIR/client_outputs/$CLIENT/$DOMAIN"
mkdir -p "$CLIENT_OUTPUTS_DIR"

if [ -f "$FINAL_CSV" ]; then
    cp "$FINAL_CSV" "$CLIENT_OUTPUTS_DIR/"
    log ""
    log "📁 CSV copied to client outputs:"
    log "   $CLIENT_OUTPUTS_DIR/${DOMAIN}_${TIMESTAMP}.csv"
    log ""
fi
```

### Queue System (queue_system/scripts/run_pipeline_robust.sh)

**Added lines 301-317:**
```bash
# ============================================================================
# COPY TO CLIENT OUTPUTS
# ============================================================================

log "[CLIENT OUTPUTS] Copying CSV to client outputs folder..."

CLIENT_OUTPUTS_DIR="$QUEUE_SYSTEM_DIR/../client_outputs/$CLIENT/$DOMAIN"
mkdir -p "$CLIENT_OUTPUTS_DIR"

if [ -f "$FINAL_CSV" ]; then
    cp "$FINAL_CSV" "$CLIENT_OUTPUTS_DIR/"
    log "  ✅ CSV copied to: client_outputs/$CLIENT/$DOMAIN/${DOMAIN}_${TIMESTAMP}.csv"
else
    log "  ⚠️  CSV not found, skipping client outputs copy"
fi

log ""
```

**Also updated output summary (lines 337-343):**
```bash
log "OUTPUT LOCATIONS:"
log "  Pipeline outputs: $OUTPUT_DIR"
log "    - ${DOMAIN}_${TIMESTAMP}.csv"
log "    - ${DOMAIN}_${TIMESTAMP}.json"
log "  Client outputs: ../client_outputs/$CLIENT/$DOMAIN/"
log "    - ${DOMAIN}_${TIMESTAMP}.csv"
log "  Log: $LOG_FILE"
```

---

## Usage

### Setting Client Name

**Main Pipeline:**
```bash
export CLIENT="mycompany"
./run_pipeline.sh "https://example.com"

# CSV available at:
# - client_outputs/mycompany/example/example_20251028_120000.csv
# - main_pipeline/l4_dedupe_and_export/outputs/mycompany/example/example_20251028_120000.csv
```

**Queue System:**
```bash
cd queue_system
./queue_add.sh "mycompany" "https://example.com"

# CSV available at:
# - client_outputs/mycompany/example/example_20251028_120000.csv  (from root)
# - queue_system/outputs/mycompany/example/example_20251028_120000.csv
```

**Default:** If `CLIENT` not set, uses `"default"`

---

## Benefits

✅ **Easy access** - All CSVs for a client in one centralized location
✅ **Organized** - By client, then by domain
✅ **Preserved** - Original pipeline outputs remain untouched
✅ **Automatic** - No manual copying needed
✅ **Cross-pipeline** - Works with both main and queue systems
✅ **Backward compatible** - Existing scripts/paths still work

---

## What's Copied

**Only CSV files** are copied to `client_outputs/`.

**Not copied:**
- JSON files (remain in original location)
- Segments (L1 output)
- Chunks (L2 output)
- LLM responses (L3 output)
- Logs

**Original locations preserved:**
- Main: `main_pipeline/l1_crawl_with_markdown/outputs/...`
- Main: `main_pipeline/l2_merge_and_chunk/outputs/...`
- Main: `main_pipeline/l3_llm_classify_extract/outputs/...`
- Main: `main_pipeline/l4_dedupe_and_export/outputs/...`
- Queue: `queue_system/outputs/...`

---

## Finding CSVs

### List all CSVs for a client
```bash
ls -la client_outputs/mycompany/*/*.csv
```

### Count total companies for a client
```bash
cat client_outputs/mycompany/*/*.csv | tail -n +2 | wc -l
```

### Combine all CSVs for a client
```bash
# Get header from first CSV
head -1 $(find client_outputs/mycompany/ -name "*.csv" | head -1) > mycompany_all.csv

# Append all data (skip headers)
tail -n +2 -q client_outputs/mycompany/*/*.csv >> mycompany_all.csv
```

---

## Documentation Updates

**Files updated:**
- `README.md` - Added client_outputs to structure and examples
- `client_outputs/README.md` - NEW - Complete guide for client outputs
- `CLIENT_OUTPUTS_FEATURE.md` - NEW - This file (feature documentation)
- `run_pipeline.sh` - Added CSV copying logic
- `queue_system/scripts/run_pipeline_robust.sh` - Added CSV copying logic

---

## Testing

To test the feature:

```bash
# Test main pipeline
export CLIENT="test_client_outputs"
./run_pipeline.sh "https://example.com"

# Verify CSV copied
ls -la client_outputs/test_client_outputs/example/
cat client_outputs/test_client_outputs/example/*.csv

# Test queue system
cd queue_system
./queue_add.sh "test_client_outputs" "https://example.com"
./queue_manager.sh &

# Wait for completion, then verify
ls -la ../client_outputs/test_client_outputs/example/
```

---

## Cleanup

Remove old outputs:

```bash
# Remove CSVs older than 30 days
find client_outputs/ -name "*.csv" -mtime +30 -delete

# Remove specific client
rm -rf client_outputs/oldclient/

# Remove specific domain
rm -rf client_outputs/mycompany/olddomain/
```

---

**Feature complete and ready to use!** ✅
