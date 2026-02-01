#!/bin/bash
# L1: Firecrawl API Systematic Testing
# Following OPTIMUS PRIME Commandment #2 (Round-Based Testing)

TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
LOG_DIR="../logs/l1_api_tests"
OUTPUT_DIR="../outputs"
LOG_FILE="$LOG_DIR/test_firecrawl_$TIMESTAMP.log"

mkdir -p "$LOG_DIR" "$OUTPUT_DIR"

echo "═══════════════════════════════════════════════════════════════" | tee -a "$LOG_FILE"
echo "SCRIPT: test_firecrawl.sh" | tee -a "$LOG_FILE"
echo "ROUND: 01 - Firecrawl API Diagnosis" | tee -a "$LOG_FILE"
echo "LAYER: L1 - API Tests" | tee -a "$LOG_FILE"
echo "STARTED: $(date -Iseconds)" | tee -a "$LOG_FILE"
echo "═══════════════════════════════════════════════════════════════" | tee -a "$LOG_FILE"

# Load API key
source ../../../.env

if [ -z "$FIRECRAWL_API_KEY" ]; then
    echo "❌ ERROR: FIRECRAWL_API_KEY not found" | tee -a "$LOG_FILE"
    exit 1
fi

echo "✅ API key loaded" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# Test 1: Minimal scrape test (google.com)
echo "═══════════════════════════════════════════════════════════════" | tee -a "$LOG_FILE"
echo "TEST 1: Minimal Scrape (google.com)" | tee -a "$LOG_FILE"
echo "═══════════════════════════════════════════════════════════════" | tee -a "$LOG_FILE"

echo "[$(date +%H:%M:%S)] Making API call..." | tee -a "$LOG_FILE"
HTTP_CODE=$(curl -X POST https://api.firecrawl.dev/v2/scrape \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.google.com", "formats": ["markdown"]}' \
  -o "$OUTPUT_DIR/test1_scrape_google.json" \
  -w "%{http_code}" \
  -s \
  --max-time 15 \
  2>> "$LOG_FILE")

if [ "$HTTP_CODE" = "200" ]; then
    echo "✅ TEST 1 PASSED: HTTP $HTTP_CODE" | tee -a "$LOG_FILE"
    jq '.success' "$OUTPUT_DIR/test1_scrape_google.json" 2>/dev/null | tee -a "$LOG_FILE"
else
    echo "❌ TEST 1 FAILED: HTTP $HTTP_CODE" | tee -a "$LOG_FILE"
    cat "$OUTPUT_DIR/test1_scrape_google.json" 2>/dev/null | tee -a "$LOG_FILE"
fi
echo "" | tee -a "$LOG_FILE"

# Test 2: Simple search test
echo "═══════════════════════════════════════════════════════════════" | tee -a "$LOG_FILE"
echo "TEST 2: Simple Search (test query)" | tee -a "$LOG_FILE"
echo "═══════════════════════════════════════════════════════════════" | tee -a "$LOG_FILE"

echo "[$(date +%H:%M:%S)] Making API call..." | tee -a "$LOG_FILE"
HTTP_CODE=$(curl -X POST https://api.firecrawl.dev/v2/search \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "dentist", "limit": 2}' \
  -o "$OUTPUT_DIR/test2_search_simple.json" \
  -w "%{http_code}" \
  -s \
  --max-time 15 \
  2>> "$LOG_FILE")

if [ "$HTTP_CODE" = "200" ]; then
    echo "✅ TEST 2 PASSED: HTTP $HTTP_CODE" | tee -a "$LOG_FILE"
    jq '.success' "$OUTPUT_DIR/test2_search_simple.json" 2>/dev/null | tee -a "$LOG_FILE"
else
    echo "❌ TEST 2 FAILED: HTTP $HTTP_CODE" | tee -a "$LOG_FILE"
    cat "$OUTPUT_DIR/test2_search_simple.json" 2>/dev/null | tee -a "$LOG_FILE"
fi
echo "" | tee -a "$LOG_FILE"

# Test 3: Spanish search
echo "═══════════════════════════════════════════════════════════════" | tee -a "$LOG_FILE"
echo "TEST 3: Spanish Search (clínica dental)" | tee -a "$LOG_FILE"
echo "═══════════════════════════════════════════════════════════════" | tee -a "$LOG_FILE"

echo "[$(date +%H:%M:%S)] Making API call..." | tee -a "$LOG_FILE"
HTTP_CODE=$(curl -X POST https://api.firecrawl.dev/v2/search \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "clínica dental", "limit": 2, "country": "ES"}' \
  -o "$OUTPUT_DIR/test3_search_spanish.json" \
  -w "%{http_code}" \
  -s \
  --max-time 15 \
  2>> "$LOG_FILE")

if [ "$HTTP_CODE" = "200" ]; then
    echo "✅ TEST 3 PASSED: HTTP $HTTP_CODE" | tee -a "$LOG_FILE"
    jq '.success' "$OUTPUT_DIR/test3_search_spanish.json" 2>/dev/null | tee -a "$LOG_FILE"
else
    echo "❌ TEST 3 FAILED: HTTP $HTTP_CODE" | tee -a "$LOG_FILE"
    cat "$OUTPUT_DIR/test3_search_spanish.json" 2>/dev/null | tee -a "$LOG_FILE"
fi
echo "" | tee -a "$LOG_FILE"

# Test 4: Full Madrid query
echo "═══════════════════════════════════════════════════════════════" | tee -a "$LOG_FILE"
echo "TEST 4: Full Madrid Query" | tee -a "$LOG_FILE"
echo "═══════════════════════════════════════════════════════════════" | tee -a "$LOG_FILE"

echo "[$(date +%H:%M:%S)] Making API call..." | tee -a "$LOG_FILE"
HTTP_CODE=$(curl -X POST https://api.firecrawl.dev/v2/search \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "clínica dental Madrid", "limit": 2, "country": "ES", "sources": ["web"]}' \
  -o "$OUTPUT_DIR/test4_search_madrid.json" \
  -w "%{http_code}" \
  -s \
  --max-time 15 \
  2>> "$LOG_FILE")

if [ "$HTTP_CODE" = "200" ]; then
    echo "✅ TEST 4 PASSED: HTTP $HTTP_CODE" | tee -a "$LOG_FILE"
    jq '.success' "$OUTPUT_DIR/test4_search_madrid.json" 2>/dev/null | tee -a "$LOG_FILE"
else
    echo "❌ TEST 4 FAILED: HTTP $HTTP_CODE" | tee -a "$LOG_FILE"
    cat "$OUTPUT_DIR/test4_search_madrid.json" 2>/dev/null | tee -a "$LOG_FILE"
fi
echo "" | tee -a "$LOG_FILE"

# Summary
echo "═══════════════════════════════════════════════════════════════" | tee -a "$LOG_FILE"
echo "COMPLETED: $(date -Iseconds)" | tee -a "$LOG_FILE"
echo "LOG: $LOG_FILE" | tee -a "$LOG_FILE"
echo "OUTPUTS: $OUTPUT_DIR/test*.json" | tee -a "$LOG_FILE"
echo "═══════════════════════════════════════════════════════════════" | tee -a "$LOG_FILE"
