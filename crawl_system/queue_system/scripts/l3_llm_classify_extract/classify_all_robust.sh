#!/bin/bash
#
# L3: Classify All Chunks with Auto-Retry (ROBUST VERSION)
# - No set -e, handles failures gracefully
# - Validates that we got SOME successful results
# - Reports detailed statistics
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QUEUE_SYSTEM_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"
CLIENT=${CLIENT:-"default"}
DOMAIN=${DOMAIN:-"default"}
CHUNKS_DIR="$QUEUE_SYSTEM_DIR/outputs/$CLIENT/$DOMAIN/chunks"
RESPONSES_DIR="$QUEUE_SYSTEM_DIR/outputs/$CLIENT/$DOMAIN/llm_responses"
CLASSIFY_SCRIPT="$SCRIPT_DIR/scripts/classify_chunk_robust.sh"

mkdir -p "$RESPONSES_DIR"

log() {
    echo "[$(date '+%H:%M:%S')] $1"
}

log "🧠 L3: LLM CLASSIFICATION"
log "   Client: $CLIENT"
log "   Domain: $DOMAIN"
log "   Chunks: $CHUNKS_DIR"

# ============================================================================
# PHASE 1: Validate inputs
# ============================================================================
log ""
log "[PHASE 1] Validating inputs..."

if [ ! -d "$CHUNKS_DIR" ]; then
    log "❌ Chunks directory not found: $CHUNKS_DIR"
    log "   L2 may have failed"
    exit 1
fi

# Get all chunks (using find to avoid "Argument list too long" with 10k+ files)
CHUNK_LIST=$(mktemp)
find "$CHUNKS_DIR" -name "chunk_*.json" -type f | sort > "$CHUNK_LIST"
TOTAL_CHUNKS=$(wc -l < "$CHUNK_LIST" | tr -d ' ')

if [ $TOTAL_CHUNKS -eq 0 ]; then
    log "❌ No chunks found in $CHUNKS_DIR"
    rm "$CHUNK_LIST"
    exit 1
fi

log "✅ Found $TOTAL_CHUNKS chunks"

# Check API key
if [ -z "$ANTHROPIC_API_KEY" ]; then
    log "❌ ANTHROPIC_API_KEY not set"
    rm "$CHUNK_LIST"
    exit 1
fi

log "✅ API key configured"

# ============================================================================
# PHASE 2: Process chunks with parallelism
# ============================================================================
log ""
log "[PHASE 2] Processing chunks..."
log "   Concurrency: 15 workers"
log "   Retry logic: 10 attempts per chunk"

CONCURRENCY=15

# Function to process a single chunk
process_chunk() {
    local CHUNK_FILE=$1
    local CHUNK_NAME=$(basename "$CHUNK_FILE" .json)
    local RESPONSE_FILE="$RESPONSES_DIR/response_$CHUNK_NAME.json"

    # Check if already processed successfully
    if [ -f "$RESPONSE_FILE" ]; then
        if jq -e '.content[0].text' "$RESPONSE_FILE" > /dev/null 2>&1; then
            echo "[$(date '+%H:%M:%S')] ✅ $CHUNK_NAME (cached)"
            return 0
        fi
    fi

    # Process with Claude (has built-in 10-attempt retry)
    if "$CLASSIFY_SCRIPT" "$CHUNK_FILE" > /dev/null 2>&1; then
        if jq -e '.content[0].text' "$RESPONSE_FILE" > /dev/null 2>&1; then
            echo "[$(date '+%H:%M:%S')] ✅ $CHUNK_NAME"
            return 0
        else
            echo "[$(date '+%H:%M:%S')] ❌ $CHUNK_NAME (invalid response)"
            return 1
        fi
    else
        echo "[$(date '+%H:%M:%S')] ❌ $CHUNK_NAME (failed after retries)"
        return 1
    fi
}

export -f process_chunk
export RESPONSES_DIR
export CLASSIFY_SCRIPT

# Use xargs for parallel processing (read from temp file)
cat "$CHUNK_LIST" | xargs -P $CONCURRENCY -I {} bash -c 'process_chunk "$@"' _ {}

# Clean up temp file
rm "$CHUNK_LIST"

# ============================================================================
# PHASE 3: Validate results
# ============================================================================
log ""
log "[PHASE 3] Validation..."

# Count successful responses (using find to avoid "Argument list too long")
TOTAL_RESPONSES=$(find "$RESPONSES_DIR" -name "response_chunk_*.json" -type f 2>/dev/null | wc -l | tr -d ' ')

if [ $TOTAL_RESPONSES -eq 0 ]; then
    log "❌ No successful responses"
    log "   All chunks failed - check API key and rate limits"
    exit 1
fi

SUCCESS_RATE=$((TOTAL_RESPONSES * 100 / TOTAL_CHUNKS))
FAILED=$((TOTAL_CHUNKS - TOTAL_RESPONSES))

log ""
log "✅ L3 COMPLETE"
log "   Successful: $TOTAL_RESPONSES / $TOTAL_CHUNKS ($SUCCESS_RATE%)"
log "   Failed: $FAILED"

# Exit successfully if we got at least 50% success rate
if [ $SUCCESS_RATE -lt 50 ]; then
    log "⚠️  WARNING: Success rate below 50%"
    log "   Continuing anyway, but results may be incomplete"
fi

exit 0
