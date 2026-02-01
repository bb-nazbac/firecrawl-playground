#!/bin/bash
#
# ROBUST PIPELINE ORCHESTRATOR
# Runs L1 → L2 → L3 → L4 with comprehensive error handling
# Usage: ./run_pipeline_robust.sh <target_url>
#

TARGET_URL=$1

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QUEUE_SYSTEM_DIR="$(dirname "$SCRIPT_DIR")"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Get CLIENT from environment or default to "default"
CLIENT=${CLIENT:-"default"}

# Extract domain from URL (or use environment variable)
if [ -z "$DOMAIN" ]; then
    DOMAIN=$(echo "$TARGET_URL" | sed -E 's|https?://||; s|www\.||; s|/.*||; s|\..*||')
fi

# Create log directory
LOG_DIR="$QUEUE_SYSTEM_DIR/logs/$CLIENT/$DOMAIN"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/${DOMAIN}_${TIMESTAMP}.log"

# Export variables for child processes
export CLIENT
export DOMAIN
export TIMESTAMP

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ❌ ERROR: $1" | tee -a "$LOG_FILE"
}

# ============================================================================
# VALIDATION AND USAGE
# ============================================================================

if [ -z "$TARGET_URL" ]; then
    echo "Usage: $0 <target_url>"
    echo "Example: $0 'https://example.com/directory'"
    exit 1
fi

log "================================================================================"
log "ROBUST COMPANY SCRAPER PIPELINE"
log "================================================================================"
log "Target URL: $TARGET_URL"
log "Client: $CLIENT"
log "Domain: $DOMAIN"
log "Timestamp: $TIMESTAMP"
log "Working directory: $QUEUE_SYSTEM_DIR"
log "Log file: $LOG_FILE"
log ""

# ============================================================================
# PRE-FLIGHT CHECKS
# ============================================================================

log "[PRE-FLIGHT] Running pre-flight checks..."

# Check 1: API Keys
log "  Checking API keys..."

ENV_FILE="$QUEUE_SYSTEM_DIR/../.env"
if [ ! -f "$ENV_FILE" ]; then
    log_error ".env file not found at $ENV_FILE"
    exit 1
fi

source "$ENV_FILE"

if [ -z "$FIRECRAWL_API_KEY" ]; then
    log_error "FIRECRAWL_API_KEY not set in .env"
    exit 1
fi

if [ -z "$ANTHROPIC_API_KEY" ]; then
    log_error "ANTHROPIC_API_KEY not set in .env"
    exit 1
fi

log "  ✅ API keys configured"

# Check 2: Disk Space
log "  Checking disk space..."

AVAILABLE_MB=$(df -m "$QUEUE_SYSTEM_DIR" | tail -1 | awk '{print $4}')

if [ "$AVAILABLE_MB" -lt 500 ]; then
    log_error "Insufficient disk space: ${AVAILABLE_MB}MB available (need 500MB minimum)"
    exit 1
fi

log "  ✅ Disk space: ${AVAILABLE_MB}MB available"

# Check 3: Network connectivity
log "  Checking network connectivity..."

if ! curl -s --max-time 5 https://api.firecrawl.dev/v2/health > /dev/null 2>&1; then
    log_error "Cannot reach Firecrawl API (network issue or API down)"
    exit 1
fi

log "  ✅ Network connectivity OK"

# Check 4: Python and dependencies
log "  Checking Python..."

if ! command -v python3 &> /dev/null; then
    log_error "python3 not found"
    exit 1
fi

if ! python3 -c "import requests, json" 2>/dev/null; then
    log_error "Python dependencies missing (requests, json)"
    exit 1
fi

log "  ✅ Python environment OK"

# Check 5: Required tools
log "  Checking required tools..."

for cmd in jq curl bash; do
    if ! command -v $cmd &> /dev/null; then
        log_error "$cmd not found"
        exit 1
    fi
done

log "  ✅ Required tools available"

log "[PRE-FLIGHT] ✅ All checks passed"
log ""

# Export API keys for child processes
export FIRECRAWL_API_KEY
export ANTHROPIC_API_KEY
export OPENAI_API_KEY

# Create output directories
mkdir -p "$QUEUE_SYSTEM_DIR/outputs/$CLIENT/$DOMAIN"

# ============================================================================
# L1: CRAWL WITH MARKDOWN
# ============================================================================

log "[L1] CRAWL WITH MARKDOWN"
log "  Starting crawl (limit: 20000, concurrency: 50)..."

# Initiate crawl
CRAWL_RESPONSE=$(curl -s -X POST https://api.firecrawl.dev/v2/crawl \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"url\": \"$TARGET_URL\",
    \"allowSubdomains\": true,
    \"limit\": 20000,
    \"maxConcurrency\": 50,
    \"maxDiscoveryDepth\": 5,
    \"allowExternalLinks\": false,
    \"scrapeOptions\": {
      \"formats\": [\"markdown\"],
      \"onlyMainContent\": true,
      \"blockAds\": true
    }
  }")

CRAWL_ID=$(echo "$CRAWL_RESPONSE" | jq -r '.id // empty')

if [ -z "$CRAWL_ID" ]; then
    log_error "Failed to start crawl"
    log "  Response: $CRAWL_RESPONSE"
    exit 1
fi

log "  Crawl started: $CRAWL_ID"

# Fetch segments with robust script
log "  Fetching segments..."

if ! /usr/bin/python3 -u "$SCRIPT_DIR/l1_crawl_with_markdown/fetch_segments.py" "$CRAWL_ID" 2>&1 | tee -a "$LOG_FILE"; then
    log_error "L1 failed - could not fetch segments"
    exit 1
fi

# Validate L1 output
SEGMENTS_DIR="$QUEUE_SYSTEM_DIR/outputs/$CLIENT/$DOMAIN/segments"

if [ ! -d "$SEGMENTS_DIR" ] || [ -z "$(ls -A "$SEGMENTS_DIR" 2>/dev/null)" ]; then
    log_error "L1 failed - no segments downloaded"
    exit 1
fi

SEGMENT_COUNT=$(find "$SEGMENTS_DIR" -name "segment_*.json" | wc -l | tr -d ' ')

if [ "$SEGMENT_COUNT" -eq 0 ]; then
    log_error "L1 failed - no segment files found"
    exit 1
fi

log "[L1] ✅ COMPLETE - $SEGMENT_COUNT segments"
log ""

# ============================================================================
# L2: MERGE AND CHUNK
# ============================================================================

log "[L2] MERGE AND CHUNK"

if ! /usr/bin/python3 "$SCRIPT_DIR/l2_merge_and_chunk/merge_and_split.py" 2>&1 | tee -a "$LOG_FILE"; then
    log_error "L2 failed - could not create chunks"
    exit 1
fi

# Validate L2 output
CHUNKS_DIR="$QUEUE_SYSTEM_DIR/outputs/$CLIENT/$DOMAIN/chunks"

if [ ! -d "$CHUNKS_DIR" ] || [ -z "$(ls -A "$CHUNKS_DIR" 2>/dev/null)" ]; then
    log_error "L2 failed - no chunks created"
    exit 1
fi

CHUNK_COUNT=$(find "$CHUNKS_DIR" -name "chunk_*.json" | wc -l | tr -d ' ')

if [ "$CHUNK_COUNT" -eq 0 ]; then
    log_error "L2 failed - no chunk files found"
    exit 1
fi

log "[L2] ✅ COMPLETE - $CHUNK_COUNT chunks"
log ""

# ============================================================================
# L3: LLM CLASSIFY & EXTRACT
# ============================================================================

log "[L3] LLM CLASSIFY & EXTRACT"

if ! bash "$SCRIPT_DIR/l3_llm_classify_extract/classify_all_with_retry.sh" 2>&1 | tee -a "$LOG_FILE"; then
    log_error "L3 failed - classification errors"
    exit 1
fi

# Validate L3 output
RESPONSES_DIR="$QUEUE_SYSTEM_DIR/outputs/$CLIENT/$DOMAIN/llm_responses"

if [ ! -d "$RESPONSES_DIR" ] || [ -z "$(ls -A "$RESPONSES_DIR" 2>/dev/null)" ]; then
    log_error "L3 failed - no responses generated"
    exit 1
fi

RESPONSE_COUNT=$(find "$RESPONSES_DIR" -name "response_chunk_*.json" | wc -l | tr -d ' ')

if [ "$RESPONSE_COUNT" -eq 0 ]; then
    log_error "L3 failed - no response files found"
    exit 1
fi

SUCCESS_RATE=$((RESPONSE_COUNT * 100 / CHUNK_COUNT))

log "[L3] ✅ COMPLETE - $RESPONSE_COUNT/$CHUNK_COUNT responses ($SUCCESS_RATE%)"
log ""

# ============================================================================
# L4: DEDUPE AND EXPORT
# ============================================================================

log "[L4] DEDUPE AND EXPORT"

if ! /usr/bin/python3 "$SCRIPT_DIR/l4_dedupe_and_export/export_final.py" 2>&1 | tee -a "$LOG_FILE"; then
    log_error "L4 failed - could not export results"
    exit 1
fi

# Validate L4 output
OUTPUT_DIR="$QUEUE_SYSTEM_DIR/outputs/$CLIENT/$DOMAIN"
FINAL_CSV="$OUTPUT_DIR/${DOMAIN}_${TIMESTAMP}.csv"

if [ ! -f "$FINAL_CSV" ]; then
    log_error "L4 failed - CSV not created"
    exit 1
fi

COMPANY_COUNT=$(tail -n +2 "$FINAL_CSV" | wc -l | tr -d ' ')

if [ "$COMPANY_COUNT" -eq 0 ]; then
    log_error "L4 failed - no companies in CSV"
    exit 1
fi

log "[L4] ✅ COMPLETE"
log ""

# ============================================================================
# COPY TO CLIENT OUTPUTS
# ============================================================================

log "[CLIENT OUTPUTS] Copying CSV to client outputs folder..."

CLIENT_OUTPUTS_DIR="$QUEUE_SYSTEM_DIR/../client_outputs/$CLIENT/$DOMAIN"
mkdir -p "$CLIENT_OUTPUTS_DIR"

if [ -f "$FINAL_CSV" ]; then
    cp "$FINAL_CSV" "$CLIENT_OUTPUTS_DIR/"
    log "  ✅ CSV copied to: client_outputs/$CLIENT/$DOMAIN/${DOMAIN}_${TIMESTAMP}.csv"
else
    log "  ⚠️  CSV not found, skipping client outputs copy"
fi

log ""

# ============================================================================
# FINAL SUMMARY
# ============================================================================

log "================================================================================"
log "✅ PIPELINE COMPLETE!"
log "================================================================================"

WITH_DOMAINS=$(tail -n +2 "$FINAL_CSV" | awk -F',' '$2 != ""' | wc -l | tr -d ' ')
DOMAIN_PCT=$((WITH_DOMAINS * 100 / COMPANY_COUNT))

log "SUMMARY:"
log "  Client: $CLIENT"
log "  Domain: $DOMAIN"
log "  Pages crawled: $(cat "$FINAL_CSV" | wc -l | tr -d ' ')"
log "  Companies extracted: $COMPANY_COUNT"
log "  With domains: $WITH_DOMAINS ($DOMAIN_PCT%)"
log ""
log "OUTPUT LOCATIONS:"
log "  Pipeline outputs: $OUTPUT_DIR"
log "    - ${DOMAIN}_${TIMESTAMP}.csv"
log "    - ${DOMAIN}_${TIMESTAMP}.json"
log "  Client outputs: ../client_outputs/$CLIENT/$DOMAIN/"
log "    - ${DOMAIN}_${TIMESTAMP}.csv"
log "  Log: $LOG_FILE"
log ""

log "✅ DONE!"
exit 0
