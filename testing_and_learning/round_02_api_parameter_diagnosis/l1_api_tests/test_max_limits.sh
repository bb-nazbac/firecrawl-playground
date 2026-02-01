#!/bin/bash
# Round 02: Test MAXIMUM limits for Firecrawl v2 /search

TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
LOG_DIR="../logs/l1_api_tests"
OUTPUT_DIR="../outputs"
LOG_FILE="$LOG_DIR/test_max_limits_$TIMESTAMP.log"

mkdir -p "$LOG_DIR" "$OUTPUT_DIR"
source ../../../.env

echo "═══════════════════════════════════════════════════════════════" | tee "$LOG_FILE"
echo "ROUND 02: MAXIMUM LIMIT TESTING" | tee -a "$LOG_FILE"
echo "Goal: Find breaking point for 'limit' parameter" | tee -a "$LOG_FILE"
echo "═══════════════════════════════════════════════════════════════" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# Test 100 results
echo "TEST: limit=100" | tee -a "$LOG_FILE"
HTTP_CODE=$(curl -X POST https://api.firecrawl.dev/v2/search \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "clínica dental Madrid", "limit": 100}' \
  -o "$OUTPUT_DIR/test_limit_100.json" \
  -w "%{http_code}" -s \
  --max-time 120)
echo "  HTTP: $HTTP_CODE" | tee -a "$LOG_FILE"
if [ "$HTTP_CODE" = "200" ]; then
  jq '{success: .success, creditsUsed: .creditsUsed, resultsCount: (.data.web | length)}' "$OUTPUT_DIR/test_limit_100.json" 2>/dev/null | tee -a "$LOG_FILE"
else
  cat "$OUTPUT_DIR/test_limit_100.json" | tee -a "$LOG_FILE"
fi
echo "" | tee -a "$LOG_FILE"

# Test 250 results
echo "TEST: limit=250" | tee -a "$LOG_FILE"
HTTP_CODE=$(curl -X POST https://api.firecrawl.dev/v2/search \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "clínica dental Madrid", "limit": 250}' \
  -o "$OUTPUT_DIR/test_limit_250.json" \
  -w "%{http_code}" -s \
  --max-time 180)
echo "  HTTP: $HTTP_CODE" | tee -a "$LOG_FILE"
if [ "$HTTP_CODE" = "200" ]; then
  jq '{success: .success, creditsUsed: .creditsUsed, resultsCount: (.data.web | length)}' "$OUTPUT_DIR/test_limit_250.json" 2>/dev/null | tee -a "$LOG_FILE"
else
  cat "$OUTPUT_DIR/test_limit_250.json" | tee -a "$LOG_FILE"
fi
echo "" | tee -a "$LOG_FILE"

# Test 500 (ambitious!)
echo "TEST: limit=500" | tee -a "$LOG_FILE"
HTTP_CODE=$(curl -X POST https://api.firecrawl.dev/v2/search \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "clínica dental Madrid", "limit": 500}' \
  -o "$OUTPUT_DIR/test_limit_500.json" \
  -w "%{http_code}" -s \
  --max-time 300)
echo "  HTTP: $HTTP_CODE" | tee -a "$LOG_FILE"
if [ "$HTTP_CODE" = "200" ]; then
  jq '{success: .success, creditsUsed: .creditsUsed, resultsCount: (.data.web | length)}' "$OUTPUT_DIR/test_limit_500.json" 2>/dev/null | tee -a "$LOG_FILE"
else
  cat "$OUTPUT_DIR/test_limit_500.json" | tee -a "$LOG_FILE"
fi
echo "" | tee -a "$LOG_FILE"

echo "═══════════════════════════════════════════════════════════════" | tee -a "$LOG_FILE"
echo "✅ Maximum limit tests complete" | tee -a "$LOG_FILE"
echo "Log: $LOG_FILE" | tee -a "$LOG_FILE"
echo "═══════════════════════════════════════════════════════════════" | tee -a "$LOG_FILE"
