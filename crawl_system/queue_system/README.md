# Robust Queue System

**Isolated, battle-tested pipeline with comprehensive error handling**

## What's Different from the Main System?

This is a **completely isolated** version of the pipeline with:

✅ **Retry logic on ALL stages** (L1, L2, L3, L4)
✅ **Pre-flight checks** (disk space, API keys, network)
✅ **Graceful error handling** (no `set -e`, handles partial failures)
✅ **Comprehensive validation** (validates output at each stage)
✅ **Detailed logging** (every step logged with timestamps)
✅ **Isolated outputs** (won't interfere with main pipeline)

## Directory Structure

```
queue_system/
├── scripts/
│   ├── l1_crawl_with_markdown/
│   │   └── fetch_segments_robust.py      # Retry logic for Firecrawl API
│   ├── l2_merge_and_chunk/
│   │   └── merge_and_split_robust.py     # Validation for segments/chunks
│   ├── l3_llm_classify_extract/
│   │   ├── classify_all_robust.sh        # Parallel processing with retries
│   │   └── scripts/
│   │       └── classify_chunk_robust.sh  # 10-attempt retry with backoff
│   ├── l4_dedupe_and_export/
│   │   └── export_final_robust.py        # Handles partial results
│   └── run_pipeline_robust.sh            # Main orchestrator
├── outputs/                               # All outputs isolated here
│   └── {client}/
│       └── {domain}/
│           ├── segments/
│           ├── chunks/
│           ├── llm_responses/
│           └── *.csv, *.json
├── logs/                                  # Detailed logs
├── queue/
│   ├── queue.txt                          # Pending jobs
│   ├── active.json                        # Currently running
│   ├── completed.txt                      # Success log
│   ├── failed.txt                         # Failure log
│   └── manager.log                        # Queue manager activity
├── queue_manager.sh                       # Process jobs one-by-one
├── queue_add.sh                           # Add URL to queue
└── queue_status.sh                        # Check progress
```

## Quick Start

### 1. Add URLs to Queue

```bash
cd queue_system

./queue_add.sh test "https://example1.com/directory"
./queue_add.sh test "https://example2.com/directory"
./queue_add.sh test "https://example3.com/directory"
```

### 2. Start Queue Manager

```bash
./queue_manager.sh &
```

The manager runs in the background, processing one job at a time.

### 3. Check Status

```bash
./queue_status.sh
```

Output:
```
╔════════════════════════════════════════════════════════════════╗
║         ROBUST QUEUE SYSTEM STATUS                            ║
╚════════════════════════════════════════════════════════════════╝

⚙️  ACTIVE JOBS:
   test/example1 → PID: 12345 (started: 2025-10-26 20:00:00)

📋 PENDING QUEUE:
   Total jobs: 2

   1. test/example2
      https://example2.com/directory
   2. test/example3
      https://example3.com/directory

📊 STATISTICS:
   ✅ Completed: 0
   ❌ Failed:    0
```

### 4. Monitor in Real-Time

```bash
# Watch queue status
watch -n 5 ./queue_status.sh

# Watch manager log
tail -f queue/manager.log

# Watch specific job
tail -f queue/logs/test_example1.log
```

## What Makes It Robust?

### L1: Firecrawl Crawl
- ✅ 10-attempt retry for API calls with exponential backoff
- ✅ Handles rate limits automatically (waits and retries)
- ✅ Validates JSON responses
- ✅ Continues even if some segments fail (partial success)

### L2: Merge & Chunk
- ✅ Validates segment files exist
- ✅ Handles malformed JSON gracefully
- ✅ Skips empty pages (doesn't fail)
- ✅ Checks disk space before writing

### L3: LLM Classification
- ✅ 10-attempt retry per chunk with exponential backoff
- ✅ Handles rate limits with jittered backoff
- ✅ Validates API responses
- ✅ Succeeds if ≥50% of chunks complete
- ✅ Exports partial results

### L4: Dedupe & Export
- ✅ Validates L3 responses exist
- ✅ Handles malformed responses gracefully
- ✅ Continues even if some responses fail
- ✅ Checks disk space before writing
- ✅ Exports whatever data is available

### Pre-Flight Checks
Before starting ANY pipeline, checks:
- ✅ API keys are configured
- ✅ Disk space available (500MB minimum)
- ✅ Network connectivity to Firecrawl
- ✅ Python environment OK
- ✅ Required tools installed (jq, curl, bash)

## Error Scenarios Handled

| Error | Behavior |
|-------|----------|
| Firecrawl API down | Retries 10x with backoff, then fails gracefully |
| Rate limit hit | Waits with exponential backoff, continues retrying |
| Network timeout | Retries with increasing delays |
| Malformed JSON | Logs error, skips file, continues processing |
| Disk full | Detects early, exits with clear error |
| Empty responses | Skips empty data, exports what's available |
| Partial failures | Exports partial results if ≥50% succeeds |

## Outputs

All outputs are **isolated** in `queue_system/outputs/`:

```
outputs/
├── Food Distributors USA/           # ⭐ ALL CSVs consolidated here
│   ├── domain1_timestamp.csv
│   ├── domain2_timestamp.csv
│   └── domain3_timestamp.csv
└── {client}/
    └── {domain}/
        ├── {domain}_{timestamp}.csv    # Individual results
        ├── {domain}_{timestamp}.json   # Full data + metadata
        └── segments/, chunks/, llm_responses/
```

**Consolidated CSVs**: Every CSV is automatically copied to `outputs/Food Distributors USA/` so you can easily access all results from all domains in one place!

## Logs

Comprehensive logging at multiple levels:

**Queue Manager**: `queue/manager.log`
- When jobs start/complete/fail
- Queue transitions

**Pipeline Runs**: `queue/logs/{client}_{domain}.log`
- Full pipeline execution
- Each stage's progress
- Errors and retries

**Per-Stage Logs**: `logs/{client}/{domain}/`
- Detailed stage-specific logs

## Queue Management

### Add Multiple Jobs

```bash
# From file
while read url; do
    ./queue_add.sh test "$url"
done < urls.txt

# From array
for url in "https://site1.com" "https://site2.com"; do
    ./queue_add.sh test "$url"
done
```

### Stop Manager

```bash
pkill -f queue_manager.sh
```

### Clear Queue

```bash
> queue/queue.txt
> queue/completed.txt
> queue/failed.txt
echo "{}" > queue/active.json
```

### Re-run Failed Jobs

```bash
cat queue/failed.txt | while IFS='|' read -r job_id url timestamp; do
    IFS='/' read -r client domain <<< "$job_id"
    ./queue_add.sh "$client" "$url"
done
```

## Testing

The system is ready to test on 5 websites. Simply:

1. **Add 5 URLs** using `queue_add.sh`
2. **Start manager** with `queue_manager.sh &`
3. **Monitor progress** with `queue_status.sh`
4. **Check results** in `outputs/{client}/{domain}/`

## Differences from Main System

| Feature | Main System | Queue System |
|---------|-------------|--------------|
| **Error Handling** | `set -e` (crashes on error) | Graceful failures |
| **Retry Logic** | Only L3 | All stages (L1-L4) |
| **Pre-flight Checks** | None | Comprehensive |
| **Partial Results** | Fails if any stage fails | Exports partial data |
| **Outputs** | Mixed with main | Isolated |
| **Logging** | Basic | Comprehensive |
| **Testing** | Production only | Safe testing environment |

## Ready to Test!

Give me **5 test URLs** and I'll:
1. Add them to the queue
2. Start the manager
3. Monitor progress
4. Report results

The system will run completely isolated from your existing pipelines.
