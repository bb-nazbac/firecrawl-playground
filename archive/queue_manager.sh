#!/bin/bash
#
# Simple Queue Manager - Process pipeline jobs one at a time
# Usage: ./queue_manager.sh
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QUEUE_DIR="$SCRIPT_DIR/queue"
QUEUE_FILE="$QUEUE_DIR/queue.txt"
ACTIVE_FILE="$QUEUE_DIR/active.json"
COMPLETED_FILE="$QUEUE_DIR/completed.txt"
FAILED_FILE="$QUEUE_DIR/failed.txt"

LOG_FILE="$QUEUE_DIR/manager.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Get next job from queue
get_next_job() {
    if [ ! -s "$QUEUE_FILE" ]; then
        return 1
    fi
    head -n 1 "$QUEUE_FILE"
    return 0
}

# Remove job from queue
remove_from_queue() {
    local job=$1
    grep -v "^$job$" "$QUEUE_FILE" > "$QUEUE_FILE.tmp" || true
    mv "$QUEUE_FILE.tmp" "$QUEUE_FILE"
}

# Add job to active list
add_to_active() {
    local job_id=$1
    local url=$2
    local pid=$3

    jq --arg id "$job_id" --arg url "$url" --arg pid "$pid" \
        '. + {($id): {url: $url, pid: $pid, started: now}}' \
        "$ACTIVE_FILE" > "$ACTIVE_FILE.tmp"
    mv "$ACTIVE_FILE.tmp" "$ACTIVE_FILE"
}

# Remove from active
remove_from_active() {
    local job_id=$1

    jq --arg id "$job_id" 'del(.[$id])' "$ACTIVE_FILE" > "$ACTIVE_FILE.tmp"
    mv "$ACTIVE_FILE.tmp" "$ACTIVE_FILE"
}

# Check if any job is currently running
is_job_running() {
    local count=$(jq 'length' "$ACTIVE_FILE")
    [ "$count" -gt 0 ]
}

# Check if pipeline completed successfully
check_pipeline_success() {
    local client=$1
    local domain=$2

    # Check if final CSV exists
    local csv_count=$(find "$SCRIPT_DIR/l4_dedupe_and_export/outputs/$client/$domain/" -name "*.csv" 2>/dev/null | wc -l)
    [ "$csv_count" -gt 0 ]
}

# Process active job (check for completion)
process_active_job() {
    local active_jobs=$(jq -r 'to_entries[] | "\(.key)|\(.value.url)|\(.value.pid)"' "$ACTIVE_FILE")

    if [ -z "$active_jobs" ]; then
        return 0
    fi

    while IFS='|' read -r job_id url pid; do
        [ -z "$job_id" ] && continue

        # Parse job_id
        IFS='/' read -r client domain <<< "$job_id"

        # Check if process is still running
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            # Still running
            return 0
        fi

        # Process finished - check if successful
        log "Job $job_id finished (PID: $pid)"

        if check_pipeline_success "$client" "$domain"; then
            log "  ✅ Job $job_id COMPLETE!"
            echo "$job_id|$url|$(date)" >> "$COMPLETED_FILE"
        else
            log "  ❌ Job $job_id FAILED"
            echo "$job_id|$url|$(date)" >> "$FAILED_FILE"
        fi

        # Remove from active
        remove_from_active "$job_id"
    done <<< "$active_jobs"
}

# Start a pipeline job
start_pipeline() {
    local client=$1
    local domain=$2
    local url=$3
    local job_id="$client/$domain"

    log "Starting job: $job_id"
    log "  URL: $url"

    # Run pipeline in background
    CLIENT=$client DOMAIN=$domain "$SCRIPT_DIR/run_pipeline.sh" "$url" > "$QUEUE_DIR/logs/${client}_${domain}.log" 2>&1 &
    local pid=$!

    add_to_active "$job_id" "$url" "$pid"
    log "  Started (PID: $pid)"

    return 0
}

# Main loop
log "========================================="
log "Queue Manager Started"
log "========================================="

# Create logs directory
mkdir -p "$QUEUE_DIR/logs"

# Initialize active.json if missing
if [ ! -f "$ACTIVE_FILE" ]; then
    echo "{}" > "$ACTIVE_FILE"
fi

while true; do
    # Process any active job first
    process_active_job

    # If nothing is running, try to start next job from queue
    if ! is_job_running; then
        job=$(get_next_job)
        if [ $? -eq 0 ] && [ -n "$job" ]; then
            IFS='|' read -r client domain url <<< "$job"
            job_id="$client/$domain"

            log "Found queued job: $job_id"

            # Remove from queue
            remove_from_queue "$job"

            # Start the pipeline
            if start_pipeline "$client" "$domain" "$url"; then
                log "  Started successfully"
            else
                log "  Failed to start"
                echo "$job" >> "$QUEUE_FILE"
            fi
        fi
    fi

    # Sleep before next iteration
    sleep 5
done
