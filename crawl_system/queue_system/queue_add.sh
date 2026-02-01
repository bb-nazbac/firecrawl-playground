#!/bin/bash
#
# Add a URL to the queue
# Usage: ./queue_add.sh <client> <url>
#

CLIENT=$1
URL=$2

if [ -z "$CLIENT" ] || [ -z "$URL" ]; then
    echo "Usage: $0 <client> <url>"
    echo "Example: $0 test 'https://example.com/directory'"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QUEUE_FILE="$SCRIPT_DIR/queue/queue.txt"

mkdir -p "$SCRIPT_DIR/queue"
touch "$QUEUE_FILE"

# Extract domain from URL
DOMAIN=$(echo "$URL" | sed -E 's|https?://||; s|www\.||; s|/.*||; s|\..*||')

# Check if already in queue
if grep -q "^$CLIENT|$DOMAIN|$URL$" "$QUEUE_FILE"; then
    echo "❌ Already in queue: $CLIENT/$DOMAIN"
    exit 1
fi

# Add to queue
echo "$CLIENT|$DOMAIN|$URL" >> "$QUEUE_FILE"

echo "✅ Added to queue:"
echo "   Client: $CLIENT"
echo "   Domain: $DOMAIN"
echo "   URL: $URL"
echo ""
echo "Queue position: $(wc -l < "$QUEUE_FILE" | tr -d ' ')"
