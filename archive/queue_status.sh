#!/bin/bash
#
# Show current queue status
# Usage: ./queue_status.sh
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QUEUE_DIR="$SCRIPT_DIR/queue"

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║            PIPELINE QUEUE STATUS                               ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Check locks
echo "🔒 RESOURCE LOCKS:"
if [ -f "$QUEUE_DIR/locks/crawl.lock" ]; then
    CRAWL_JOB=$(cat "$QUEUE_DIR/locks/crawl.lock")
    echo "   Crawl (L1):  🔴 LOCKED by $CRAWL_JOB"
else
    echo "   Crawl (L1):  🟢 AVAILABLE"
fi

if [ -f "$QUEUE_DIR/locks/llm.lock" ]; then
    LLM_JOB=$(cat "$QUEUE_DIR/locks/llm.lock")
    echo "   LLM (L3):    🔴 LOCKED by $LLM_JOB"
else
    echo "   LLM (L3):    🟢 AVAILABLE"
fi

echo ""

# Show active jobs
echo "⚙️  ACTIVE JOBS:"
if [ -s "$QUEUE_DIR/active.json" ] && [ "$(jq 'length' "$QUEUE_DIR/active.json")" -gt 0 ]; then
    jq -r 'to_entries[] | "   \(.key) → Stage: \(.value.stage) | PID: \(.value.pid // "N/A")"' "$QUEUE_DIR/active.json"
else
    echo "   (none)"
fi

echo ""

# Show pending queue
echo "📋 PENDING QUEUE:"
if [ -s "$QUEUE_DIR/queue.txt" ]; then
    QUEUE_COUNT=$(wc -l < "$QUEUE_DIR/queue.txt")
    echo "   Total jobs: $QUEUE_COUNT"
    echo ""
    head -10 "$QUEUE_DIR/queue.txt" | nl -w2 -s'. ' | sed 's/^/   /'
    if [ "$QUEUE_COUNT" -gt 10 ]; then
        echo "   ... and $((QUEUE_COUNT - 10)) more"
    fi
else
    echo "   (empty)"
fi

echo ""

# Show stats
echo "📊 STATISTICS:"
COMPLETED_COUNT=$(wc -l < "$QUEUE_DIR/completed.txt" 2>/dev/null || echo "0")
FAILED_COUNT=$(wc -l < "$QUEUE_DIR/failed.txt" 2>/dev/null || echo "0")
echo "   ✅ Completed: $COMPLETED_COUNT"
echo "   ❌ Failed:    $FAILED_COUNT"
echo ""
