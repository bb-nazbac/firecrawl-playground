#!/bin/bash
# Main Pipeline Orchestrator
# Usage: ./run_pipeline.sh <target_url>

set -e  # Exit on error

TARGET_URL=$1

# Get script directory (works wherever folder is located)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$SCRIPT_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Get CLIENT from environment or default to "default"
CLIENT=${CLIENT:-"default"}

# Extract domain from URL (e.g., https://example.com/path -> example)
# If DOMAIN is already set in environment (by queue manager), use it
if [ -z "$DOMAIN" ]; then
    DOMAIN=$(echo "$TARGET_URL" | sed -E 's|https?://||; s|www\.||; s|/.*||; s|\..*||')
fi

# Create client/domain-specific log directory
LOG_DIR="$BASE_DIR/main_pipeline/logs/$CLIENT/$DOMAIN"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/${DOMAIN}_${TIMESTAMP}.log"

# Export variables for child processes
export CLIENT
export DOMAIN
export TIMESTAMP

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

if [ -z "$TARGET_URL" ]; then
    echo "Usage: $0 <target_url>"
    echo "Example: $0 'https://example.com/directory'"
    exit 1
fi

log "================================================================================"
log "COMPANY SCRAPER PIPELINE - PRODUCTION RUN"
log "================================================================================"
log "Target URL: $TARGET_URL"
log "Client: $CLIENT"
log "Domain: $DOMAIN"
log "Timestamp: $TIMESTAMP"
log "Working directory: $BASE_DIR"
log "Log file: $LOG_FILE"
log ""

# Create client/domain-specific output directories
mkdir -p "$BASE_DIR/main_pipeline/l1_crawl_with_markdown/outputs/$CLIENT/$DOMAIN"
mkdir -p "$BASE_DIR/main_pipeline/l2_merge_and_chunk/outputs/$CLIENT/$DOMAIN"
mkdir -p "$BASE_DIR/main_pipeline/l3_llm_classify_extract/outputs/$CLIENT/$DOMAIN"
mkdir -p "$BASE_DIR/main_pipeline/l4_dedupe_and_export/outputs/$CLIENT/$DOMAIN"

# Load .env from script directory or parent
if [ -f "$BASE_DIR/.env" ]; then
    source "$BASE_DIR/.env"
elif [ -f "$BASE_DIR/../.env" ]; then
    source "$BASE_DIR/../.env"
else
    log "ERROR: .env file not found!"
    log "Create .env with FIRECRAWL_API_KEY and ANTHROPIC_API_KEY"
    exit 1
fi

# Export variables for child processes
export FIRECRAWL_API_KEY
export ANTHROPIC_API_KEY
export OPENAI_API_KEY

# ================================================================================
# L1: CRAWL WITH MARKDOWN
# ================================================================================
log "[L1] CRAWL WITH MARKDOWN"
log "Starting crawl (limit: 10000, concurrency: 50)..."

curl -X POST https://api.firecrawl.dev/v2/crawl \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"url\": \"$TARGET_URL\",
    \"allowSubdomains\": true,
    \"limit\": 10000,
    \"maxConcurrency\": 50,
    \"maxDiscoveryDepth\": 5,
    \"allowExternalLinks\": false,
    \"scrapeOptions\": {
      \"formats\": [\"markdown\"],
      \"onlyMainContent\": true,
      \"blockAds\": true
    }
  }" -o "$BASE_DIR/main_pipeline/l1_crawl_with_markdown/crawl_job.json"

CRAWL_ID=$(cat "$BASE_DIR/main_pipeline/l1_crawl_with_markdown/crawl_job.json" | jq -r '.id')
log "Crawl started: $CRAWL_ID"

# Poll until complete and fetch all segments
log "Fetching all segments..."
/usr/bin/python3 -u "$BASE_DIR/main_pipeline/l1_crawl_with_markdown/fetch_segments.py" "$CRAWL_ID"

log "[L1] COMPLETE"
log ""

# ================================================================================
# L2: MERGE AND CHUNK
# ================================================================================
log "[L2] MERGE AND CHUNK"
/usr/bin/python3 "$BASE_DIR/main_pipeline/l2_merge_and_chunk/merge_and_split.py"
log "[L2] COMPLETE"
log ""

# ================================================================================
# L3: LLM CLASSIFY & EXTRACT
# ================================================================================
log "[L3] LLM CLASSIFY & EXTRACT"
$BASE_DIR/main_pipeline/l3_llm_classify_extract/classify_all_with_retry.sh
log "[L3] COMPLETE"
log ""

# ================================================================================
# L4: DEDUPE AND EXPORT
# ================================================================================
log "[L4] DEDUPE AND EXPORT"
/usr/bin/python3 "$BASE_DIR/main_pipeline/l4_dedupe_and_export/export_final.py"
log "[L4] COMPLETE"
log ""

log "================================================================================"
log "PIPELINE COMPLETE!"
log "================================================================================"
log "Final output: $BASE_DIR/main_pipeline/l4_dedupe_and_export/outputs/$CLIENT/$DOMAIN/${DOMAIN}_${TIMESTAMP}.csv"
log "================================================================================"

# Copy CSV to client_outputs folder for easy access
FINAL_CSV="$BASE_DIR/main_pipeline/l4_dedupe_and_export/outputs/$CLIENT/$DOMAIN/${DOMAIN}_${TIMESTAMP}.csv"
CLIENT_OUTPUTS_DIR="$BASE_DIR/client_outputs/$CLIENT/$DOMAIN"
mkdir -p "$CLIENT_OUTPUTS_DIR"

if [ -f "$FINAL_CSV" ]; then
    cp "$FINAL_CSV" "$CLIENT_OUTPUTS_DIR/"
    log ""
    log "📁 CSV copied to client outputs:"
    log "   $CLIENT_OUTPUTS_DIR/${DOMAIN}_${TIMESTAMP}.csv"
    log ""
fi

# Show summary
if [ -f "$FINAL_CSV" ]; then
    COMPANY_COUNT=$(tail -n +2 "$FINAL_CSV" | wc -l | tr -d ' ')
    WITH_DOMAINS=$(tail -n +2 "$FINAL_CSV" | awk -F',' '$2 != ""' | wc -l | tr -d ' ')

    log ""
    log "SUMMARY:"
    log "  Client: $CLIENT"
    log "  Domain: $DOMAIN"
    log "  Companies extracted: $COMPANY_COUNT"
    log "  With domains: $WITH_DOMAINS ($((WITH_DOMAINS * 100 / COMPANY_COUNT))%)"
    log "  Output folder: main_pipeline/l4_dedupe_and_export/outputs/$CLIENT/$DOMAIN/"
    log "  CSV file: ${DOMAIN}_${TIMESTAMP}.csv"
    log "  JSON file: ${DOMAIN}_${TIMESTAMP}.json"
    log ""
fi

log "✅ DONE!"

