#!/bin/bash
#
# Show queue status
# Usage: ./queue_status.sh
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QUEUE_FILE="$SCRIPT_DIR/queue/queue.txt"
ACTIVE_FILE="$SCRIPT_DIR/queue/active.json"
COMPLETED_FILE="$SCRIPT_DIR/queue/completed.txt"
FAILED_FILE="$SCRIPT_DIR/queue/failed.txt"

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║         ROBUST QUEUE SYSTEM STATUS                            ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Active jobs
echo "⚙️  ACTIVE JOBS:"
if [ -f "$ACTIVE_FILE" ] && [ -s "$ACTIVE_FILE" ]; then
    jq -r 'to_entries[] | "   \(.key) → PID: \(.value.pid) (started: \(.value.started | strftime("%Y-%m-%d %H:%M:%S")))"' "$ACTIVE_FILE" 2>/dev/null

    if [ $? -ne 0 ]; then
        echo "   None"
    fi
else
    echo "   None"
fi

echo ""

# Pending queue
echo "📋 PENDING QUEUE:"
if [ -f "$QUEUE_FILE" ] && [ -s "$QUEUE_FILE" ]; then
    QUEUE_COUNT=$(wc -l < "$QUEUE_FILE" | tr -d ' ')
    echo "   Total jobs: $QUEUE_COUNT"
    echo ""

    i=1
    while IFS='|' read -r client domain url; do
        echo "   $i. $client/$domain"
        echo "      $url"
        i=$((i + 1))

        # Only show first 10
        if [ $i -gt 10 ]; then
            echo "   ... and $((QUEUE_COUNT - 10)) more"
            break
        fi
    done < "$QUEUE_FILE"
else
    echo "   Empty"
fi

echo ""

# Statistics
echo "📊 STATISTICS:"

COMPLETED=0
if [ -f "$COMPLETED_FILE" ]; then
    COMPLETED=$(wc -l < "$COMPLETED_FILE" | tr -d ' ')
fi

FAILED=0
if [ -f "$FAILED_FILE" ]; then
    FAILED=$(wc -l < "$FAILED_FILE" | tr -d ' ')
fi

echo "   ✅ Completed: $COMPLETED"
echo "   ❌ Failed:    $FAILED"

if [ $FAILED -gt 0 ]; then
    echo ""
    echo "Recent failures:"
    tail -3 "$FAILED_FILE" 2>/dev/null | while IFS='|' read -r job_id url timestamp; do
        echo "   - $job_id ($timestamp)"
    done
fi

echo ""
