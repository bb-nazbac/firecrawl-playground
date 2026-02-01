#!/bin/bash
# Split Erudus into 10 chunks

ORIGINAL="/Users/bahaa/Documents/Clients/firecrawl_playground/l2_merge_and_chunk/outputs/openinfo/erudus/chunks/chunk_0001_ORIGINAL.json"
MD_FILE="/tmp/erudus_full.md"
CHUNKS_DIR="/Users/bahaa/Documents/Clients/firecrawl_playground/l2_merge_and_chunk/outputs/openinfo/erudus/chunks"

URL="https://erudus.com/whos-using-erudus/"
TITLE="Who's using Erudus"

# Extract header (lines 1-20)
sed -n '1,20p' "$MD_FILE" > /tmp/header.md

# Extract wholesalers section (lines 21-199)
sed -n '1,199p' "$MD_FILE" > /tmp/chunk1.md

# Create chunk 1 (Wholesalers)
MD_CONTENT=$(cat /tmp/chunk1.md | jq -Rs .)
cat > "${CHUNKS_DIR}/chunk_0001.json" <<EOF
{
  "chunk_id": 1,
  "page_count": 1,
  "pages": [
    {
      "id": 1,
      "url": "${URL}",
      "title": "${TITLE} - Part 1/10 (Wholesalers)",
      "markdown": ${MD_CONTENT},
      "markdown_length": $(wc -c < /tmp/chunk1.md)
    }
  ]
}
EOF
echo "Created chunk_0001.json (194 wholesalers)"

# Split manufacturers (lines 200-1684) into 9 chunks
# 1460 manufacturers / 9 = ~162 per chunk
MANUF_START=200
MANUF_END=1684
TOTAL_MANUF=1460
PER_CHUNK=162

for i in {2..10}; do
    CHUNK_NUM=$(printf "%04d" $i)

    # Calculate line ranges for this chunk
    if [ $i -eq 2 ]; then
        # First manufacturer chunk includes the header
        START_LINE=200
    else
        # Subsequent chunks start after "## Manufacturers" header
        START_LINE=$((200 + ($i - 2) * PER_CHUNK + 2))
    fi

    if [ $i -eq 10 ]; then
        # Last chunk gets all remaining
        END_LINE=1684
    else
        END_LINE=$((START_LINE + PER_CHUNK - 1))
    fi

    # Create chunk file
    if [ $i -eq 2 ]; then
        # First manufacturer chunk: header + manufacturers section start
        sed -n "1,20p" "$MD_FILE" > /tmp/chunk${i}.md
        sed -n "${START_LINE},${END_LINE}p" "$MD_FILE" >> /tmp/chunk${i}.md
    else
        # Other chunks: just header + "## Manufacturers" + companies for this chunk
        sed -n "1,19p" "$MD_FILE" > /tmp/chunk${i}.md
        echo "" >> /tmp/chunk${i}.md
        echo "## Manufacturers" >> /tmp/chunk${i}.md
        echo "" >> /tmp/chunk${i}.md
        sed -n "${START_LINE},${END_LINE}p" "$MD_FILE" >> /tmp/chunk${i}.md
    fi

    MD_CONTENT=$(cat /tmp/chunk${i}.md | jq -Rs .)
    MANUF_COUNT=$(grep -c "^- " /tmp/chunk${i}.md)

    cat > "${CHUNKS_DIR}/chunk_${CHUNK_NUM}.json" <<EOF
{
  "chunk_id": ${i},
  "page_count": 1,
  "pages": [
    {
      "id": 1,
      "url": "${URL}",
      "title": "${TITLE} - Part ${i}/10 (Manufacturers)",
      "markdown": ${MD_CONTENT},
      "markdown_length": $(wc -c < /tmp/chunk${i}.md)
    }
  ]
}
EOF
    echo "Created chunk_${CHUNK_NUM}.json (~${MANUF_COUNT} manufacturers)"
done

echo ""
echo "✅ Successfully created 10 chunks!"
ls -lh "${CHUNKS_DIR}"/chunk_*.json | grep -v ORIGINAL
