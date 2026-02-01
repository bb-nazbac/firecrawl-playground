#!/bin/bash
#
# L3: Classify All Chunks with Auto-Retry
# Processes all chunks from L2 using OpenAI GPT-4o with progressive retry
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLIENT=${CLIENT:-"default"}
DOMAIN=${DOMAIN:-"default"}
CHUNKS_DIR="$SCRIPT_DIR/../l2_merge_and_chunk/outputs/$CLIENT/$DOMAIN/chunks"
RESPONSES_DIR="$SCRIPT_DIR/outputs/$CLIENT/$DOMAIN/llm_responses"
CLASSIFY_SCRIPT="$SCRIPT_DIR/scripts/classify_chunk.sh"

mkdir -p "$RESPONSES_DIR"

# Get all chunks (using find to avoid "Argument list too long" with 10k+ files)
CHUNK_LIST=$(mktemp)
find "$CHUNKS_DIR" -name "chunk_*.json" -type f | sort > "$CHUNK_LIST"
TOTAL_CHUNKS=$(wc -l < "$CHUNK_LIST" | tr -d ' ')

if [ $TOTAL_CHUNKS -eq 0 ]; then
    echo "❌ No chunks found in $CHUNKS_DIR"
    rm "$CHUNK_LIST"
    exit 1
fi

echo "[$(date '+%H:%M:%S')] LLM CLASSIFICATION WITH CLAUDE SONNET 4.5"
echo "[$(date '+%H:%M:%S')] =========================================="
echo "[$(date '+%H:%M:%S')] Total chunks: $TOTAL_CHUNKS"
echo "[$(date '+%H:%M:%S')]"

# Process chunks with parallelism
CONCURRENCY=30
PROCESSED=0
FAILED=0

# Function to process a single chunk
process_chunk() {
    local CHUNK_FILE=$1
    local CHUNK_NAME=$(basename "$CHUNK_FILE" .json)
    local RESPONSE_FILE="$RESPONSES_DIR/response_$CHUNK_NAME.json"

    # Check if already processed
    if [ -f "$RESPONSE_FILE" ]; then
        if jq -e '.content[0].text' "$RESPONSE_FILE" > /dev/null 2>&1; then
            echo "[$(date '+%H:%M:%S')] ✅ $CHUNK_NAME already processed"
            return 0
        fi
    fi

    # Process with Claude
    echo "[$(date '+%H:%M:%S')] Processing $CHUNK_NAME..."
    if "$CLASSIFY_SCRIPT" "$CHUNK_FILE" > /dev/null 2>&1; then
        if jq -e '.content[0].text' "$RESPONSE_FILE" > /dev/null 2>&1; then
            echo "[$(date '+%H:%M:%S')] ✅ $CHUNK_NAME completed"
            return 0
        else
            echo "[$(date '+%H:%M:%S')] ❌ $CHUNK_NAME invalid"
            return 1
        fi
    else
        echo "[$(date '+%H:%M:%S')] ❌ $CHUNK_NAME failed"
        return 1
    fi
}

export -f process_chunk
export RESPONSES_DIR
export CLASSIFY_SCRIPT

# Use xargs for parallel processing (read from temp file)
cat "$CHUNK_LIST" | xargs -P $CONCURRENCY -I {} bash -c 'process_chunk "$@"' _ {}

echo "[$(date '+%H:%M:%S')]"
echo "[$(date '+%H:%M:%S')] ✅ All chunks processed!"
echo "[$(date '+%H:%M:%S')]"

# Clean up temp file
rm "$CHUNK_LIST"

# Count results (using find to avoid "Argument list too long")
TOTAL_RESPONSES=$(find "$RESPONSES_DIR" -name "response_chunk_*.json" -type f | wc -l | tr -d ' ')
echo "[$(date '+%H:%M:%S')] ================================="
echo "[$(date '+%H:%M:%S')] FINAL: $TOTAL_RESPONSES / $TOTAL_CHUNKS"
echo "[$(date '+%H:%M:%S')] ================================="
