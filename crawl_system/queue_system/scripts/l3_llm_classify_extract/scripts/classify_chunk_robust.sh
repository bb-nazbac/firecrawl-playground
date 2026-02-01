#!/bin/bash
# L3: Classify a Single Chunk with Claude (ROBUST VERSION)
# Usage: ./classify_chunk_robust.sh /path/to/chunk_0001.json

CHUNK_FILE=$1

# Use relative paths from script location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
L3_DIR="$(dirname "$SCRIPT_DIR")"
QUEUE_SYSTEM_DIR="$(dirname "$(dirname "$L3_DIR"))"

# Get client and domain from environment
CLIENT=${CLIENT:-"default"}
DOMAIN=${DOMAIN:-"default"}

RESPONSES_DIR="$QUEUE_SYSTEM_DIR/outputs/$CLIENT/$DOMAIN/llm_responses"

mkdir -p "$RESPONSES_DIR"

if [ -z "$CHUNK_FILE" ]; then
    echo "Usage: $0 /path/to/chunk_0001.json"
    exit 1
fi

# Validate input file exists
if [ ! -f "$CHUNK_FILE" ]; then
    echo "❌ ERROR: Chunk file not found: $CHUNK_FILE"
    exit 1
fi

CHUNK_NAME="$(basename "$CHUNK_FILE" .json)"

# Load .env from queue_system parent (firecrawl_playground)
ENV_FILE="$QUEUE_SYSTEM_DIR/../.env"
if [ ! -f "$ENV_FILE" ]; then
    echo "❌ ERROR: .env not found at $ENV_FILE"
    exit 1
fi

source "$ENV_FILE"

if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "❌ ERROR: ANTHROPIC_API_KEY not set in .env"
    exit 1
fi

# Extract page data with FULL markdown
PAGES_DATA=$(cat "$CHUNK_FILE" | jq '.pages | map({
  id,
  url,
  title,
  markdown,
  markdown_length
})')

# Create prompt
PROMPT="You are analyzing pages from a website to identify which ones contain company information.

GOAL: Find pages that contain company NAMES and company WEBSITE DOMAINS/URLs.

<critical_instruction>
CRITICAL: This is EXHAUSTIVE extraction.
- Count how many companies are on the page
- Extract EVERY SINGLE ONE
- If you count 125, extract 125
- Do NOT stop after patterns become clear
- Do NOT provide \"representative samples\"
</critical_instruction>

CONTEXT:
- You are analyzing a batch of pages from the same website
- Each page has: id, url, title, markdown (FULL content), markdown_length
- Pages may contain:
  * Individual company listings (1 company per page with name + website)
  * List pages (multiple companies on one page with names + websites)
  * Navigation/category pages (links to companies but no actual company data displayed)
  * Other content (articles, descriptions without specific company names/websites)

YOUR TASK:
For EACH page, classify if it contains extractable company information.

CLASSIFICATIONS:
- \"company_individual\": Page about 1 specific company (has company name + website/domain)
- \"company_list\": Page lists multiple companies (has multiple company names + websites/domains)
- \"navigation\": Portal/menu page (links to company pages but doesn't display company data itself)
- \"other\": Does not contain company names and websites

CRITICAL INSTRUCTIONS FOR WEBSITE EXTRACTION:
- Extract the COMPANY'S OWN website domain (e.g., \"acmecorp.com\", \"ajaxindustries.com\")
- DO NOT extract the directory website itself (e.g., DO NOT use \"achrnews.com\" or listing URLs)
- Look for links labeled as company website, homepage, or in contact sections
- Common patterns: \"Website:\", \"Visit:\", \"http://companyname.com\", \"www.companyname.com\"
- If page shows company name but NO actual company website, leave website as empty \"\"
- Only extract if you find the ACTUAL company's domain, not the directory listing URL

PAGES TO ANALYZE:
$PAGES_DATA

Respond with ONLY JSON:
{
  \"classifications\": [
    {
      \"id\": 1,
      \"classification\": \"company_individual|company_list|navigation|other\",
      \"confidence\": \"high|medium|low\",
      \"reasoning\": \"brief why\",
      \"companies_extracted\": [
        {
          \"name\": \"Company Name\",
          \"website\": \"https://company.com\"
        }
      ]
    }
  ]
}

EXTRACTION RULES:
- If classification = \"company_individual\": Extract the 1 company (name + website)
- If classification = \"company_list\": Extract ALL companies you find (names + websites)
- If classification = \"navigation\" or \"other\": companies_extracted = []
- Extract from the markdown_preview provided
- If website/domain not found, use empty string \"\"
- Look for company names (e.g., \"Acme Corp\", \"XYZ LLC\") and websites (e.g., \"https://...\", \"www...\")

<critical_instruction>
CRITICAL: This is EXHAUSTIVE extraction.
- Count how many companies are on the page
- Extract EVERY SINGLE ONE
- If you count 125, extract 125
- Do NOT stop after patterns become clear
- DO NOT provide \"representative samples\"
</critical_instruction>"

# Call Claude with retry logic
PROMPT_JSON=$(echo "$PROMPT" | jq -Rs .)
MAX_RETRIES=10
RETRY_COUNT=0
SUCCESS=false

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
  # Make API call
  HTTP_CODE=$(curl -s -w "%{http_code}" -X POST https://api.anthropic.com/v1/messages \
    -H "x-api-key: $ANTHROPIC_API_KEY" \
    -H "anthropic-version: 2023-06-01" \
    -H "content-type: application/json" \
    -d "{
      \"model\": \"claude-sonnet-4-5-20250929\",
      \"max_tokens\": 8192,
      \"temperature\": 0,
      \"messages\": [{\"role\": \"user\", \"content\": $PROMPT_JSON}]
    }" -o "$RESPONSES_DIR/response_$CHUNK_NAME.json")

  # Check if response is valid
  if jq -e '.content[0].text' "$RESPONSES_DIR/response_$CHUNK_NAME.json" > /dev/null 2>&1; then
    SUCCESS=true
    break
  fi

  # Check error type
  ERROR_TYPE=$(jq -r '.error.type // "unknown"' "$RESPONSES_DIR/response_$CHUNK_NAME.json" 2>/dev/null)
  ERROR_MSG=$(jq -r '.error.message // "unknown"' "$RESPONSES_DIR/response_$CHUNK_NAME.json" 2>/dev/null)

  RETRY_COUNT=$((RETRY_COUNT + 1))

  if [ $RETRY_COUNT -lt $MAX_RETRIES ]; then
    # Exponential backoff: 2^retry seconds (2, 4, 8, 16, 32...)
    WAIT_TIME=$((2 ** RETRY_COUNT))
    # Cap at 60 seconds
    if [ $WAIT_TIME -gt 60 ]; then
      WAIT_TIME=60
    fi

    # Add jitter for rate limits (random 0-5s)
    JITTER=$((RANDOM % 5))
    WAIT_TIME=$((WAIT_TIME + JITTER))

    echo "⚠️  Attempt $RETRY_COUNT failed (HTTP $HTTP_CODE, $ERROR_TYPE), retrying in ${WAIT_TIME}s..." >&2
    sleep $WAIT_TIME
  fi
done

if [ "$SUCCESS" = true ]; then
  exit 0
else
  echo "❌ Failed after $MAX_RETRIES attempts: $ERROR_TYPE - $ERROR_MSG" >&2
  exit 1
fi
