# Pipeline Queue System

**Queue-based orchestration for running multiple pipeline jobs sequentially**

---

## Quick Start

### Add a Job to the Queue

```bash
./queue_add.sh <client> <url>
```

**Example:**
```bash
./queue_add.sh openinfo "https://sandwich.org.uk/directory"
```

### Start the Queue Manager (Background)

```bash
./queue_manager.sh &
```

The manager runs continuously, processing queued jobs one at a time.

### Check Queue Status

```bash
./queue_status.sh
```

Shows:
- Active jobs with PIDs
- Pending queue
- Completion statistics

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    QUEUE SYSTEM FLOW                         │
└─────────────────────────────────────────────────────────────┘

USER
  │
  ├─→ ./queue_add.sh <client> <url>
  │        │
  │        └─→ queue/queue.txt (pending jobs)
  │                │
  │                │  Format: client|domain|url
  │                │  Example: openinfo|sandwich|https://...
  │
  └─→ ./queue_manager.sh (background daemon)
           │
           ├─→ POLL queue.txt every 5 seconds
           │
           ├─→ CHECK IF JOB RUNNING
           │    └─ Is active.json empty?
           │
           ├─→ START NEXT JOB (if nothing running)
           │    │
           │    └─→ ./run_pipeline.sh <url>
           │         ├─ L1: Crawl
           │         ├─ L2: Merge & Chunk
           │         ├─ L3: LLM Classification
           │         └─ L4: Dedupe & Export
           │
           ├─→ TRACK PROGRESS
           │    └─ queue/active.json (job_id → {url, pid, started})
           │
           └─→ ON COMPLETION
                ├─ SUCCESS → queue/completed.txt
                └─ FAILURE → queue/failed.txt
```

---

## How It Works

### Simple Serial Execution

The queue system uses a straightforward approach:

**One Job at a Time**:
- Manager checks if any job is currently running
- If `active.json` is empty, starts the next job from `queue.txt`
- Waits for job to complete before starting another

**Why This Works**:
- ✅ Prevents API rate limit issues (natural throttling)
- ✅ No complex lock management needed
- ✅ Easy to monitor and debug
- ✅ Reliable - no race conditions

**Job Execution**:
- Each job runs the complete pipeline: L1 → L2 → L3 → L4
- Job runs in background, manager tracks the PID
- Manager polls every 5 seconds to check if job finished
- On completion, checks for CSV output to determine success/failure

### Job Lifecycle

```
PENDING → ACTIVE → COMPLETED/FAILED

queue.txt    active.json    completed.txt
  │              │          failed.txt
  │              │
  └──(picked)──→ │
                 │
            (processing)
                 │
                 └──(done)──→ ✅/❌
```

### Job State Files

| File | Purpose | Format | Example |
|------|---------|--------|---------|
| `queue/queue.txt` | Pending jobs | `client\|domain\|url` | `openinfo\|sandwich\|https://...` |
| `queue/active.json` | Running jobs | `{job_id: {url, pid, started}}` | `{"openinfo/sandwich": {...}}` |
| `queue/completed.txt` | Successful jobs | `job_id\|url\|timestamp` | `openinfo/sandwich\|https://...\|Thu...` |
| `queue/failed.txt` | Failed jobs | `job_id\|url\|timestamp` | `openinfo/sandwich\|https://...\|Thu...` |

### Logs

**Manager Log**:
```bash
queue/manager.log
```
- Manager activity (start/stop, job transitions)
- Timestamped entries for auditing

**Job Logs**:
```bash
queue/logs/{client}_{domain}.log
```
- Full pipeline execution log for each job
- Includes L1/L2/L3/L4 output
- Useful for debugging failures

---

## Monitoring

### Check Current Status

```bash
./queue_status.sh
```

**Sample Output**:
```
╔════════════════════════════════════════════════════════════════╗
║            PIPELINE QUEUE STATUS                               ║
╚════════════════════════════════════════════════════════════════╝

⚙️  ACTIVE JOBS:
   openinfo/sandwich → PID: 12345

📋 PENDING QUEUE:
   Total jobs: 3

   1. openinfo|tuco|https://tuco.ac.uk/
   2. openinfo|countryrange|https://countryrangegroup.com/
   3. openinfo|western|https://westerninternational.co.uk/

📊 STATISTICS:
   ✅ Completed: 5
   ❌ Failed:    1
```

### Monitor Manager in Real-Time

```bash
tail -f queue/manager.log
```

### Check Job Progress

```bash
# Watch specific job log
tail -f queue/logs/openinfo_sandwich.log

# Count processed chunks (L3 stage)
ls l3_llm_classify_extract/outputs/openinfo/sandwich/llm_responses/ | wc -l
```

---

## Troubleshooting

### Job Failed at L3 (LLM Classification)

**Symptom**: Job appears in `queue/failed.txt`, log shows "❌ chunk_XXXX invalid"

**Cause**:
- LLM API error (rate limit, timeout, authentication)
- Invalid chunk content (no company data)
- Malformed JSON response

**Solution**:
```bash
# 1. Check job log for specific error
cat queue/logs/openinfo_domain.log

# 2. Check LLM response files for errors
ls -la l3_llm_classify_extract/outputs/openinfo/domain/llm_responses/

# 3. If rate limit, wait and re-add job
./queue_add.sh openinfo "https://original-url.com"

# 4. If invalid content, may not be recoverable
```

### Manager Stopped Running

**Symptom**: Jobs not processing, `ps aux | grep queue_manager` shows nothing

**Cause**: Manager crashed or was terminated

**Solution**:
```bash
# 1. Check manager log for crash reason
tail -50 queue/manager.log

# 2. Restart manager
./queue_manager.sh &

# 3. Verify it's running
ps aux | grep queue_manager
```

### Too Many Jobs Failing

**Symptom**: High failure rate in `queue/failed.txt`

**Common Causes**:
- **API Key Issues**: Check `.env` has valid keys
- **Rate Limits**: Too many jobs queued, hitting API limits
- **Bad URLs**: URLs not crawlable (404, auth required, etc.)

**Solution**:
```bash
# 1. Review failures
cat queue/failed.txt

# 2. Check common failure pattern
for log in queue/logs/*.log; do
    echo "=== $log ==="
    grep -A5 "ERROR\|❌" "$log" | head -10
done

# 3. If API key issue, fix .env and clear failed jobs
# Then re-add manually
```

### Clearing the Queue

```bash
# Stop manager
pkill -f queue_manager.sh

# Clear all queue files
> queue/queue.txt
> queue/active.json
> queue/completed.txt
> queue/failed.txt

# Restart manager
./queue_manager.sh &
```

---

## File Reference

### Queue Directory Structure

```
/queue
    /logs
        {client}_{domain}.log  # Per-job pipeline logs
    active.json                # Currently running job
    completed.txt              # Successfully completed jobs
    failed.txt                 # Failed jobs
    manager.log                # Queue manager activity log
    queue.txt                  # Pending jobs (FIFO)
```

### Active Jobs Format (active.json)

```json
{
  "openinfo/sandwich": {
    "url": "https://sandwich.org.uk/directory",
    "pid": "12345",
    "started": 1729714507
  }
}
```

---

## Operational Best Practices

### Adding Multiple Jobs

Use a loop for bulk additions:

```bash
# From a file
while IFS=',' read -r client url; do
    ./queue_add.sh "$client" "$url"
done < urls.txt

# From array
urls=(
    "https://sandwich.org.uk/directory"
    "https://tuco.ac.uk/"
    "https://countryrangegroup.com/"
)

for url in "${urls[@]}"; do
    ./queue_add.sh openinfo "$url"
done
```

### Running Manager as a Service

Use `nohup` to keep manager running after logout:

```bash
nohup ./queue_manager.sh > queue/manager_nohup.log 2>&1 &
```

### Monitoring Long-Running Queues

Set up a simple monitoring script:

```bash
#!/bin/bash
# monitor_queue.sh - Check every 5 minutes

while true; do
    echo "=== $(date) ==="
    ./queue_status.sh
    echo ""
    sleep 300
done
```

---

## Known Limitations

1. **No Pause/Resume**: Jobs run to completion or failure; cannot be paused between stages
2. **No Priority Queue**: Jobs processed in FIFO order only
3. **No Concurrent L2/L4**: L2 and L4 stages could run concurrently but currently don't due to monolithic pipeline
4. **No Job Editing**: Cannot modify queued jobs (must remove and re-add)
5. **Serial Execution Only**: Only one job can run at a time (prevents API rate limits but slower throughput)

---

## Future Enhancements

- [ ] Break `run_pipeline.sh` into per-stage scripts for true stage-by-stage execution
- [ ] Job priority support
- [ ] Web UI for queue management
- [ ] Email notifications on completion/failure
- [ ] Concurrent L2/L4 execution (non-API stages can run in parallel)
- [ ] Queue persistence across manager restarts
- [ ] Job retry with exponential backoff
- [ ] Parallel job execution with configurable concurrency limits

---

## Summary

The queue system enables **unattended multi-URL processing**:

✅ Add multiple jobs with `./queue_add.sh`
✅ Start manager with `./queue_manager.sh &`
✅ Monitor with `./queue_status.sh`
✅ Check logs in `queue/manager.log` and `queue/logs/`
✅ Handle failures by checking `queue/failed.txt`

**Serial execution prevents API rate limit issues** while **automatic job processing** eliminates manual intervention.
