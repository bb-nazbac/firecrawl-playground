#!/bin/bash
#
# Add a job to the pipeline queue
# Usage: ./queue_add.sh <client> <url>
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QUEUE_DIR="$SCRIPT_DIR/queue"
QUEUE_FILE="$QUEUE_DIR/queue.txt"

# Parse arguments
CLIENT=$1
URL=$2

if [ -z "$CLIENT" ] || [ -z "$URL" ]; then
    echo "Usage: $0 <client> <url>"
    echo ""
    echo "Examples:"
    echo "  $0 openinfo https://sandwich.org.uk/directory"
    echo "  $0 acme https://example.com/suppliers"
    exit 1
fi

# Extract domain from URL
DOMAIN=$(echo "$URL" | sed -E 's|https?://||; s|www\.||; s|/.*||; s|\..*||')

# Create queue entry: client|domain|url
QUEUE_ENTRY="$CLIENT|$DOMAIN|$URL"

# Check if already in queue or active
if grep -q "^$QUEUE_ENTRY$" "$QUEUE_FILE" 2>/dev/null; then
    echo "⚠️  Job already in queue: $CLIENT/$DOMAIN"
    exit 1
fi

if jq -e ".[\"$CLIENT/$DOMAIN\"]" "$QUEUE_DIR/active.json" > /dev/null 2>&1; then
    echo "⚠️  Job already running: $CLIENT/$DOMAIN"
    exit 1
fi

# Add to queue
echo "$QUEUE_ENTRY" >> "$QUEUE_FILE"

echo "✅ Added to queue:"
echo "   Client: $CLIENT"
echo "   Domain: $DOMAIN"
echo "   URL: $URL"
echo ""
echo "Queue position: $(wc -l < "$QUEUE_FILE")"
