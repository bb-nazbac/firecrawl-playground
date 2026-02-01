#!/bin/bash
# Test if Firecrawl /v2/search supports pagination

source ../../../../.env

echo "Testing pagination parameters..."
echo ""

# Test 1: offset parameter
echo "TEST 1: offset parameter"
curl -X POST https://api.firecrawl.dev/v2/search \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "clínica dental Madrid", "limit": 10, "offset": 10}' \
  -w "\nHTTP: %{http_code}\n" -s | jq '{success: .success, error: .error, resultsCount: (.data.web | length), firstUrl: .data.web[0].url}' 2>/dev/null
echo ""

# Test 2: page parameter  
echo "TEST 2: page parameter"
curl -X POST https://api.firecrawl.dev/v2/search \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "clínica dental Madrid", "limit": 10, "page": 2}' \
  -w "\nHTTP: %{http_code}\n" -s | jq '{success: .success, error: .error, resultsCount: (.data.web | length)}' 2>/dev/null
echo ""

# Test 3: skip parameter
echo "TEST 3: skip parameter"
curl -X POST https://api.firecrawl.dev/v2/search \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "clínica dental Madrid", "limit": 10, "skip": 10}' \
  -w "\nHTTP: %{http_code}\n" -s | jq '{success: .success, error: .error, resultsCount: (.data.web | length)}' 2>/dev/null
echo ""

# Test 4: startIndex parameter
echo "TEST 4: startIndex parameter"
curl -X POST https://api.firecrawl.dev/v2/search \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "clínica dental Madrid", "limit": 10, "startIndex": 10}' \
  -w "\nHTTP: %{http_code}\n" -s | jq '{success: .success, error: .error, resultsCount: (.data.web | length)}' 2>/dev/null
echo ""

# Baseline: Get first 10 results to compare URLs
echo "BASELINE: First 10 results (for comparison)"
curl -X POST https://api.firecrawl.dev/v2/search \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "clínica dental Madrid", "limit": 10}' \
  -s | jq '{firstUrl: .data.web[0].url, tenthUrl: .data.web[9].url}' 2>/dev/null
