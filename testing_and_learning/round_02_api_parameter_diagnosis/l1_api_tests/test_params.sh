#!/bin/bash
# Round 02: Test Firecrawl v2 /search API parameters
# Goal: Find what parameters work vs fail

TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
LOG_DIR="../logs/l1_api_tests"
OUTPUT_DIR="../outputs"
LOG_FILE="$LOG_DIR/test_params_$TIMESTAMP.log"

mkdir -p "$LOG_DIR" "$OUTPUT_DIR"

source ../../../.env

echo "═══════════════════════════════════════════════════════════════" | tee "$LOG_FILE"
echo "ROUND 02: API Parameter Testing" | tee -a "$LOG_FILE"
echo "TIMESTAMP: $(date -Iseconds)" | tee -a "$LOG_FILE"
echo "═══════════════════════════════════════════════════════════════" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# Test 1: Minimal (just query + limit) - KNOWN TO WORK
echo "TEST 1: Minimal params (query + limit)" | tee -a "$LOG_FILE"
HTTP_CODE=$(curl -X POST https://api.firecrawl.dev/v2/search \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "clínica dental Madrid", "limit": 2}' \
  -o "$OUTPUT_DIR/test1_minimal.json" \
  -w "%{http_code}" -s)
echo "HTTP: $HTTP_CODE" | tee -a "$LOG_FILE"
jq '.success' "$OUTPUT_DIR/test1_minimal.json" 2>/dev/null | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# Test 2: With country
echo "TEST 2: With country parameter" | tee -a "$LOG_FILE"
HTTP_CODE=$(curl -X POST https://api.firecrawl.dev/v2/search \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "clínica dental Madrid", "limit": 2, "country": "ES"}' \
  -o "$OUTPUT_DIR/test2_with_country.json" \
  -w "%{http_code}" -s)
echo "HTTP: $HTTP_CODE" | tee -a "$LOG_FILE"
jq '.success' "$OUTPUT_DIR/test2_with_country.json" 2>/dev/null | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# Test 3: With scrapeOptions (minimal)
echo "TEST 3: With scrapeOptions (formats only)" | tee -a "$LOG_FILE"
HTTP_CODE=$(curl -X POST https://api.firecrawl.dev/v2/search \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "clínica dental Madrid", "limit": 2, "scrapeOptions": {"formats": ["markdown"]}}' \
  -o "$OUTPUT_DIR/test3_scrape_formats.json" \
  -w "%{http_code}" -s)
echo "HTTP: $HTTP_CODE" | tee -a "$LOG_FILE"
jq '.success' "$OUTPUT_DIR/test3_scrape_formats.json" 2>/dev/null | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# Test 4: Higher limit (10 results)
echo "TEST 4: Higher limit (10 results)" | tee -a "$LOG_FILE"
HTTP_CODE=$(curl -X POST https://api.firecrawl.dev/v2/search \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "clínica dental Madrid", "limit": 10}' \
  -o "$OUTPUT_DIR/test4_limit_10.json" \
  -w "%{http_code}" -s)
echo "HTTP: $HTTP_CODE" | tee -a "$LOG_FILE"
jq '.creditsUsed' "$OUTPUT_DIR/test4_limit_10.json" 2>/dev/null | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# Test 5: Even higher limit (50 results)
echo "TEST 5: High limit (50 results)" | tee -a "$LOG_FILE"
HTTP_CODE=$(curl -X POST https://api.firecrawl.dev/v2/search \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "clínica dental Madrid", "limit": 50}' \
  -o "$OUTPUT_DIR/test5_limit_50.json" \
  -w "%{http_code}" -s)
echo "HTTP: $HTTP_CODE" | tee -a "$LOG_FILE"
jq '{success: .success, creditsUsed: .creditsUsed, resultsCount: (.data.web | length)}' "$OUTPUT_DIR/test5_limit_50.json" 2>/dev/null | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

echo "═══════════════════════════════════════════════════════════════" | tee -a "$LOG_FILE"
echo "✅ Tests complete" | tee -a "$LOG_FILE"
echo "Log: $LOG_FILE" | tee -a "$LOG_FILE"
echo "Outputs: $OUTPUT_DIR/" | tee -a "$LOG_FILE"
echo "═══════════════════════════════════════════════════════════════" | tee -a "$LOG_FILE"
