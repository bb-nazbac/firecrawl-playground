#!/bin/bash
#
# L3: Classify and Extract Companies using OpenAI GPT-4o with JSON Schema
# Uses exhaustive extraction with count-first approach
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
L3_DIR="$(dirname "$SCRIPT_DIR")"
CHUNKS_DIR="$L3_DIR/../l2_merge_and_chunk/outputs/chunks"
RESPONSES_DIR="$L3_DIR/outputs/llm_responses"
CHUNK_FILE="$1"

mkdir -p "$RESPONSES_DIR"

# Validate input
if [ ! -f "$CHUNK_FILE" ]; then
  echo "❌ ERROR: Chunk file not found: $CHUNK_FILE"
  exit 1
fi

# Load env
if [ -f "$L3_DIR/../../.env" ]; then
  source "$L3_DIR/../../.env"
elif [ -f "$L3_DIR/../.env" ]; then
  source "$L3_DIR/../.env"
fi

if [ -z "$OPENAI_API_KEY" ]; then
  echo "❌ ERROR: OPENAI_API_KEY not set"
  exit 1
fi

CHUNK_NAME=$(basename "$CHUNK_FILE" .json)
echo "Processing $CHUNK_NAME..."

# Extract page data
PAGES_DATA=$(cat "$CHUNK_FILE" | jq -c '.pages')

# Create exhaustive extraction prompt
PROMPT="You are performing EXHAUSTIVE data extraction from website pages listing companies.

CRITICAL MISSION: Extract EVERY SINGLE company from EVERY page provided.

<critical_instruction>
CRITICAL: This is EXHAUSTIVE extraction.
- This is NOT sampling - you must extract ALL companies
- Count total companies across ALL pages first
- Extract EVERY SINGLE ONE
- If you count 125, extract 125
- Do NOT stop after patterns become clear
- Do NOT provide \"representative samples\"
- VERIFY: Your extracted count MUST match your total count
</critical_instruction>

TASK:
1. Count total number of companies across ALL pages
2. Extract ALL of them (name + website/domain)
3. Validate: extracted count MUST equal total count
4. Set extraction_complete to true ONLY if you extracted everything

PAGES TO ANALYZE:
$PAGES_DATA

EXTRACTION RULES:
- Extract the COMPANY'S OWN website domain (e.g., \"acmecorp.com\", \"example.com\")
- DO NOT extract the directory website itself
- Look for links labeled as company website, homepage, or in contact sections
- Common patterns: \"Website:\", \"Visit:\", \"http://companyname.com\", \"www.companyname.com\"
- If page shows company name but NO actual company website, use empty string \"\"
- Only extract if you find the ACTUAL company's domain, not the directory listing URL

VALIDATION:
- Count ALL companies on ALL pages
- Extract EVERY SINGLE company
- total_companies_counted MUST equal length of companies_extracted array
- extraction_complete = true ONLY if counts match

REMEMBER: If you count 109 companies, you must extract 109 companies. Anything less is incomplete."

# Escape prompt for JSON
PROMPT_JSON=$(echo "$PROMPT" | jq -Rs .)

# Call OpenAI with JSON Schema
curl -X POST https://api.openai.com/v1/chat/completions \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"gpt-4o\",
    \"messages\": [
      {
        \"role\": \"system\",
        \"content\": \"You are an expert data extractor. Your mission is to extract ALL companies exhaustively. Never sample, never stop early, always extract 100% of what you count.\"
      },
      {
        \"role\": \"user\",
        \"content\": $PROMPT_JSON
      }
    ],
    \"response_format\": {
      \"type\": \"json_schema\",
      \"json_schema\": {
        \"name\": \"company_extraction\",
        \"strict\": true,
        \"schema\": {
          \"type\": \"object\",
          \"properties\": {
            \"total_companies_counted\": {
              \"type\": \"integer\",
              \"description\": \"Total number of companies found across all pages\"
            },
            \"companies_extracted\": {
              \"type\": \"array\",
              \"items\": {
                \"type\": \"object\",
                \"properties\": {
                  \"name\": {
                    \"type\": \"string\",
                    \"description\": \"Company name\"
                  },
                  \"website\": {
                    \"type\": \"string\",
                    \"description\": \"Company website domain or URL (empty string if not found)\"
                  }
                },
                \"required\": [\"name\", \"website\"],
                \"additionalProperties\": false
              }
            },
            \"extraction_complete\": {
              \"type\": \"boolean\",
              \"description\": \"True if all counted companies were extracted (count matches array length)\"
            }
          },
          \"required\": [\"total_companies_counted\", \"companies_extracted\", \"extraction_complete\"],
          \"additionalProperties\": false
        }
      }
    },
    \"max_tokens\": 16000,
    \"temperature\": 0
  }" -o "$RESPONSES_DIR/response_$CHUNK_NAME.json" 2>&1

echo "✅ Response saved to: response_$CHUNK_NAME.json"
