# Crawl System - Architecture Documentation

**System Type**: Legacy Production System
**Created**: October 2025
**Status**: Operational (Legacy)
**Last Updated**: 2025-11-14

---

## 📐 System Overview

The crawl_system is a bash + Python hybrid pipeline that crawls websites using Firecrawl API and extracts company data using Claude AI. It processes jobs through a queue system and outputs organized CSV/JSON files.

**Primary Use Case**: Extract company listings from directory websites (e.g., paginasamarillas.es, rentechdigital.com, whatclinic.com)

**Architecture Pattern**: Monolithic bash orchestration with Python utilities

---

## 🏗️ Architecture Components

### **1. Queue System (Production Mode)**

**Location**: `crawl_system/queue_system/`

#### **Queue Files** (`queue_system/queue/`)

```
queue.txt            # Pending jobs (format: CLIENT|DOMAIN|URL)
active.json          # Currently running job + PID
completed.txt        # Finished jobs with timestamps
failed.txt           # Failed jobs with timestamps
manager.log          # Queue manager execution log
```

#### **Core Scripts**

**`queue_add.sh`** - Add jobs to queue
```bash
#!/bin/bash
# Extract domain from URL
DOMAIN=$(echo "$URL" | sed -E 's|https?://||; s|www\.||; s|/.*||; s|\..*||')

# Check if already queued
if grep -q "^$CLIENT|$DOMAIN|$URL$" "$QUEUE_FILE"; then
    echo "❌ Already in queue: $CLIENT/$DOMAIN"
    exit 1
fi

# Add to queue
echo "$CLIENT|$DOMAIN|$URL" >> "$QUEUE_FILE"
```

**`queue_manager.sh`** - Process jobs serially
```bash
#!/bin/bash
# Main loop
while true; do
    # Process any active job first
    process_active_job

    # If nothing running, start next job from queue
    if ! is_job_running; then
        job=$(get_next_job)
        if [ $? -eq 0 ] && [ -n "$job" ]; then
            # Remove from queue
            remove_from_queue "$job"

            # Start pipeline in background
            CLIENT=$client DOMAIN=$domain \
                "$SCRIPT_DIR/scripts/run_pipeline_robust.sh" "$url" \
                > "$QUEUE_DIR/logs/${client}_${domain}.log" 2>&1 &

            # Track in active.json
            add_to_active "$job_id" "$url" "$pid"
        fi
    fi

    sleep 5
done
```

**`queue_status.sh`** - Display queue state
```bash
#!/bin/bash
# Show active jobs
jq -r 'to_entries[] | "\(.key) → PID: \(.value.pid)"' "$ACTIVE_FILE"

# Show pending queue
while IFS='|' read -r client domain url; do
    echo "   $i. $client/$domain"
done < "$QUEUE_FILE"

# Statistics
COMPLETED=$(wc -l < "$COMPLETED_FILE" | tr -d ' ')
FAILED=$(wc -l < "$FAILED_FILE" | tr -d ' ')
```

---

### **2. Pipeline Orchestrator**

**Location**: `crawl_system/queue_system/scripts/run_pipeline_robust.sh`

**Flow**:
```
run_pipeline_robust.sh
  ↓
[PRE-FLIGHT CHECKS]
  - API keys configured
  - Disk space (500MB minimum)
  - Network connectivity
  - Python + dependencies
  - Required tools (jq, curl, bash)
  ↓
[L1] Firecrawl Crawl
  ↓
[L2] Merge & Chunk
  ↓
[L3] LLM Classify & Extract
  ↓
[L4] Dedupe & Export
  ↓
[COPY TO CLIENT OUTPUTS]
  ↓
[FINAL SUMMARY]
```

**Key Features**:
- Pre-flight validation (exits early if environment broken)
- Per-layer validation (exits if layer fails)
- Cost tracking (via logs)
- Client/domain isolation
- Automatic CSV copying to `client_outputs/`

**Exit Strategy**: `set -e` (exit on any error)

---

### **3. Layer 1: Firecrawl Crawl**

**Location**: `queue_system/scripts/l1_crawl_with_markdown/fetch_segments.py`

**Responsibility**: Initiate crawl, poll for completion, fetch all segments

**Implementation**:

```python
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

CRAWL_ID=$(echo "$CRAWL_RESPONSE" | jq -r '.id')

# Poll until complete (5s intervals)
retries = 0
max_retries = 10
while True:
    resp = requests.get(
        f"https://api.firecrawl.dev/v2/crawl/{CRAWL_ID}",
        headers={"Authorization": f"Bearer {FIRECRAWL_KEY}"},
        timeout=30
    )

    data = resp.json()
    status = data.get('status')
    completed = data.get('completed', 0)
    total = data.get('total', 0)

    print(f"  Status: {status} - {completed}/{total}", flush=True)

    if status == 'completed':
        break

    time.sleep(5)

# Fetch all segments (paginated)
segment_num = 0
skip = 0
while True:
    segment_num += 1

    if segment_num == 1:
        url = f"https://api.firecrawl.dev/v2/crawl/{CRAWL_ID}"
    else:
        url = f"https://api.firecrawl.dev/v2/crawl/{CRAWL_ID}?skip={skip}"

    resp = requests.get(url, headers={"Authorization": f"Bearer {FIRECRAWL_KEY}"})
    data = resp.json()

    # Save segment
    segment_file = SEGMENTS_DIR / f"segment_{segment_num:03d}.json"
    with open(segment_file, 'w') as f:
        json.dump(data, f)

    data_count = len(data.get('data', []))
    skip += data_count

    if not data.get('next'):
        break
```

**Output**:
```
outputs/{CLIENT}/{DOMAIN}/segments/
  segment_001.json
  segment_002.json
  segment_003.json
  ...
```

**Segment Structure**:
```json
{
  "success": true,
  "status": "completed",
  "total": 4700,
  "completed": 4700,
  "creditsUsed": 4700,
  "expiresAt": "2025-11-21T10:30:00.000Z",
  "next": "https://api.firecrawl.dev/v2/crawl/abc123?skip=100",
  "data": [
    {
      "markdown": "# Company Name\n\nWebsite: https://example.com\nPhone: +34 123 456 789",
      "metadata": {
        "title": "Company Name - Directory Listing",
        "sourceURL": "https://paginasamarillas.es/company-123",
        "statusCode": 200
      }
    }
  ]
}
```

**Error Handling**:
- Exponential backoff on API errors (2s, 4s, 8s, 16s, ...)
- Max 10 retries per request
- Exits if crawl fails to complete

**Cost**: $0.025 per page (4,700 pages = $117.50)

---

### **4. Layer 2: Merge & Chunk**

**Location**: `queue_system/scripts/l2_merge_and_chunk/merge_and_split_robust.py`

**Responsibility**: Merge all segments into single dataset, split into 1-page chunks

**Implementation**:

```python
# PHASE 1: Validate inputs
segment_files = sorted(SEGMENTS_DIR.glob("segment_*.json"))
if not segment_files:
    log(f"❌ No segment files found")
    sys.exit(1)

# Check disk space (100MB minimum)
has_space, available_mb = check_disk_space(SEGMENTS_DIR.parent)
if not has_space:
    log(f"❌ Insufficient disk space: {available_mb}MB")
    sys.exit(1)

# PHASE 2: Merge segments with validation
all_pages = []
failed_segments = []

for seg_file in segment_files:
    success, pages, error = validate_segment_file(seg_file)

    if not success:
        log(f"  ⚠️  Failed to parse {seg_file.name}: {error}")
        failed_segments.append(seg_file.name)
        continue

    all_pages.extend(pages)

# PHASE 3: Create chunks (1 page per chunk)
for i, page in enumerate(all_pages, 1):
    markdown = page.get('markdown', '')

    # Skip empty pages
    if not markdown or len(markdown.strip()) == 0:
        empty_pages += 1
        continue

    chunk_data = {
        'chunk_id': i,
        'page_count': 1,
        'pages': [{
            'id': 1,
            'url': page.get('metadata', {}).get('sourceURL', ''),
            'title': page.get('metadata', {}).get('title', ''),
            'markdown': markdown,
            'markdown_length': len(markdown)
        }]
    }

    chunk_file = CHUNKS_DIR / f"chunk_{i:04d}.json"
    with open(chunk_file, 'w') as f:
        json.dump(chunk_data, f, indent=2)
```

**Output**:
```
outputs/{CLIENT}/{DOMAIN}/chunks/
  chunk_0001.json  # Page 1
  chunk_0002.json  # Page 2
  chunk_0003.json  # Page 3
  ...
```

**Chunk Structure**:
```json
{
  "chunk_id": 1,
  "page_count": 1,
  "pages": [
    {
      "id": 1,
      "url": "https://paginasamarillas.es/clinic-123",
      "title": "Clinica Dental Madrid - Directory Listing",
      "markdown": "# Clinica Dental Madrid\n\nWebsite: https://clinicadentalmadrid.es\nPhone: +34 91 123 4567",
      "markdown_length": 8234
    }
  ]
}
```

**Error Handling**:
- Validates each segment file (JSON decode errors handled)
- Skips empty pages (logged but doesn't fail)
- Exits if no chunks created
- Max 10 write failures tolerated (disk full protection)

**Cost**: $0 (local processing)

---

### **5. Layer 3: LLM Classify & Extract**

**Location**: `queue_system/scripts/l3_llm_classify_extract/classify_all_with_retry.sh`

**Responsibility**: Process all chunks with Claude, extract company data

**Implementation**:

**Master Script** (`classify_all_with_retry.sh`):
```bash
# Get all chunks
find "$CHUNKS_DIR" -name "chunk_*.json" -type f | sort > "$CHUNK_LIST"
TOTAL_CHUNKS=$(wc -l < "$CHUNK_LIST")

# Process chunks in parallel (30 concurrent)
CONCURRENCY=30

process_chunk() {
    local CHUNK_FILE=$1
    local CHUNK_NAME=$(basename "$CHUNK_FILE" .json)
    local RESPONSE_FILE="$RESPONSES_DIR/response_$CHUNK_NAME.json"

    # Check if already processed
    if [ -f "$RESPONSE_FILE" ]; then
        if jq -e '.content[0].text' "$RESPONSE_FILE" > /dev/null 2>&1; then
            return 0  # Already done
        fi
    fi

    # Process with Claude
    "$CLASSIFY_SCRIPT" "$CHUNK_FILE"
}

export -f process_chunk

# Parallel execution using xargs
cat "$CHUNK_LIST" | xargs -P $CONCURRENCY -I {} bash -c 'process_chunk "$@"' _ {}
```

**Per-Chunk Script** (`scripts/classify_chunk.sh`):
```bash
# Extract page data from chunk
PAGES_DATA=$(cat "$CHUNK_FILE" | jq '.pages | map({
  id,
  url,
  title,
  markdown,
  markdown_length
})')

# Build prompt
PROMPT="You are analyzing pages from a website to identify company information.

GOAL: Find pages that contain company NAMES and company WEBSITE DOMAINS/URLs.

CRITICAL: This is EXHAUSTIVE extraction.
- Count how many companies are on the page
- Extract EVERY SINGLE ONE
- If you count 125, extract 125

CLASSIFICATIONS:
- \"company_individual\": Page about 1 specific company
- \"company_list\": Page lists multiple companies
- \"navigation\": Portal/menu page (no actual company data)
- \"other\": Does not contain company names and websites

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
}"

# Call Claude with retry logic (exponential backoff)
MAX_RETRIES=10
RETRY_COUNT=0
SUCCESS=false

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
  curl -X POST https://api.anthropic.com/v1/messages \
    -H "x-api-key: $ANTHROPIC_API_KEY" \
    -H "anthropic-version: 2023-06-01" \
    -H "content-type: application/json" \
    -d "{
      \"model\": \"claude-sonnet-4-5-20250929\",
      \"max_tokens\": 8192,
      \"temperature\": 0,
      \"messages\": [{\"role\": \"user\", \"content\": $PROMPT_JSON}]
    }" -o "$RESPONSES_DIR/response_$CHUNK_NAME.json"

  # Check if response is valid
  if jq -e '.content[0].text' "$RESPONSES_DIR/response_$CHUNK_NAME.json" > /dev/null; then
    SUCCESS=true
    break
  fi

  RETRY_COUNT=$((RETRY_COUNT + 1))

  # Exponential backoff: 2^retry seconds (capped at 60s)
  WAIT_TIME=$((2 ** RETRY_COUNT))
  if [ $WAIT_TIME -gt 60 ]; then
    WAIT_TIME=60
  fi

  sleep $WAIT_TIME
done
```

**Output**:
```
outputs/{CLIENT}/{DOMAIN}/llm_responses/
  response_chunk_0001.json
  response_chunk_0002.json
  response_chunk_0003.json
  ...
```

**Response Structure**:
```json
{
  "id": "msg_123",
  "type": "message",
  "role": "assistant",
  "content": [
    {
      "type": "text",
      "text": "```json\n{\n  \"classifications\": [\n    {\n      \"id\": 1,\n      \"classification\": \"company_individual\",\n      \"confidence\": \"high\",\n      \"reasoning\": \"Page contains single clinic with name and website\",\n      \"companies_extracted\": [\n        {\n          \"name\": \"Clinica Dental Madrid\",\n          \"website\": \"https://clinicadentalmadrid.es\"\n        }\n      ]\n    }\n  ]\n}\n```"
    }
  ],
  "model": "claude-sonnet-4-5-20250929",
  "usage": {
    "input_tokens": 8942,
    "output_tokens": 256
  }
}
```

**Error Handling**:
- Per-chunk retry (up to 10 attempts with exponential backoff)
- Validates response has `.content[0].text` field
- Skips already-processed chunks (resume capability)
- Concurrent processing (30 threads via xargs)
- Failed chunks logged but pipeline continues

**Cost**:
- Claude Sonnet 4: $3/1M input, $15/1M output
- Average per page: ~$0.045 (4,700 pages = $211.50)

---

### **6. Layer 4: Dedupe & Export**

**Location**: `queue_system/scripts/l4_dedupe_and_export/export_final_robust.py`

**Responsibility**: Parse LLM responses, deduplicate companies, export CSV/JSON

**Implementation**:

```python
# PHASE 1: Validate inputs
response_files = sorted(L3_RESPONSES.glob("response_chunk_*.json"))
if not response_files:
    log(f"❌ No response files found")
    sys.exit(1)

# PHASE 2: Parse responses with error handling
all_companies = []
parse_failures = []

for response_file in response_files:
    with open(response_file) as f:
        response_data = json.load(f)

    success, companies, error = parse_llm_response(response_data, response_file.name)

    if success:
        all_companies.extend(companies)
    else:
        parse_failures.append((response_file.name, error))

# Parse function handles both OpenAI and Claude formats
def parse_llm_response(response_data, response_file_name):
    # Try Claude format
    if 'content' in response_data:
        content_text = response_data.get('content', [{}])[0].get('text', '')
    # Try OpenAI format
    elif 'choices' in response_data:
        content_text = response_data.get('choices', [{}])[0].get('message', {}).get('content', '')

    # Strip markdown code blocks
    content_text = re.sub(r'^```(?:json)?\s*\n', '', content_text)
    content_text = re.sub(r'\n```\s*$', '', content_text)

    # Parse JSON
    result = json.loads(content_text)

    # Handle Claude format
    if 'classifications' in result:
        for classification in result.get('classifications', []):
            for company in classification.get('companies_extracted', []):
                companies.append({
                    'name': clean_company_name(company.get('name', '')),
                    'website_original': company.get('website', ''),
                    'domain': normalize_domain(company.get('website', '')),
                    'classification_type': classification.get('classification', 'other'),
                    'source_file': response_file_name
                })

# PHASE 3: Deduplication
# Find names with domains (prioritize these)
names_with_domains = set()
for company in all_companies:
    if company['domain']:
        normalized = normalize_company_name(company['name'])
        names_with_domains.add(normalized)

# Dedupe by domain first, then by name
by_domain = {}  # domain → company
by_name_only = {}  # name → company

for company in all_companies:
    domain = company['domain'].lower().strip()
    normalized_name = normalize_company_name(company['name'])

    if domain:
        # Has domain - keep first occurrence per domain
        if domain not in by_domain:
            by_domain[domain] = company
    else:
        # No domain - only keep if name doesn't exist with domain
        if normalized_name not in names_with_domains:
            if normalized_name not in by_name_only:
                by_name_only[normalized_name] = company

unique_companies = list(by_domain.values()) + list(by_name_only.values())

# Helper functions
def normalize_domain(website):
    """
    https://www.example.com/path?query → example.com
    """
    website = re.sub(r'^https?://', '', website)
    website = re.sub(r'^www\.', '', website)
    website = website.split('/')[0].split('?')[0].split(':')[0]
    return website.lower().strip()

def normalize_company_name(name):
    """
    Normalize for deduplication matching
    """
    normalized = name.lower()
    normalized = normalized.replace(' inc.', ' inc')
    normalized = normalized.replace(' llc.', ' llc')
    normalized = normalized.replace(' corp.', ' corp')
    return normalized.strip()

# PHASE 4: Export results
# JSON
with open(json_output, 'w') as f:
    json.dump({
        'metadata': {
            'domain': DOMAIN,
            'timestamp': TIMESTAMP,
            'total_responses': len(response_files),
            'companies_found': len(unique_companies)
        },
        'companies': unique_companies
    }, f, indent=2)

# CSV
with open(csv_output, 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=[
        'name',
        'domain',
        'website_original',
        'classification_type',
        'source_file'
    ])
    writer.writeheader()
    writer.writerows(unique_companies)
```

**Output**:
```
outputs/{CLIENT}/{DOMAIN}/
  {DOMAIN}_{TIMESTAMP}.json
  {DOMAIN}_{TIMESTAMP}.csv
```

**CSV Structure**:
```csv
name,domain,website_original,classification_type,source_file
Clinica Dental Madrid,clinicadentalmadrid.es,https://clinicadentalmadrid.es,company_individual,response_chunk_0001.json
Acme Corp,acmecorp.com,https://www.acmecorp.com/,company_list,response_chunk_0123.json
```

**Deduplication Logic**:
1. **Priority**: Companies with domains > companies without domains
2. **By Domain**: Keep first occurrence per domain (e.g., `example.com`)
3. **By Name**: Only if name doesn't exist with domain elsewhere
4. **Normalization**:
   - Domain: `https://www.example.com/path` → `example.com`
   - Name: Case-insensitive, suffix normalization (Inc., LLC, Corp.)

**Error Handling**:
- Continues despite parse failures (logs errors)
- Handles both Claude and OpenAI response formats
- Strips markdown code blocks from JSON responses
- Exits if zero companies extracted

**Cost**: $0 (local processing)

---

## 📊 Data Flow Diagram

```
USER INPUT
  └─ queue_add.sh "ClientName" "https://example.com/directory"
       ↓
QUEUE MANAGER (queue_manager.sh)
  └─ Polls queue.txt every 5s
  └─ Starts run_pipeline_robust.sh in background
       ↓
─────────────────────────────────────────────────────────────
L1: FIRECRAWL CRAWL (fetch_segments.py)
─────────────────────────────────────────────────────────────
  1. Initiate crawl via POST /v2/crawl
     {
       "url": "https://example.com/directory",
       "limit": 20000,
       "maxConcurrency": 50,
       "maxDepth": 5
     }
  2. Poll GET /v2/crawl/{id} every 5s until status=completed
  3. Fetch segments via GET /v2/crawl/{id}?skip=N (paginated)
  4. Save to outputs/{CLIENT}/{DOMAIN}/segments/segment_*.json

OUTPUT: 47 segments (4,700 pages)
COST: $117.50 (4,700 × $0.025)
       ↓
─────────────────────────────────────────────────────────────
L2: MERGE & CHUNK (merge_and_split_robust.py)
─────────────────────────────────────────────────────────────
  1. Load all segment_*.json files
  2. Validate each segment (JSON parsing)
  3. Merge into all_pages[] array
  4. Create 1 chunk per page (chunk_NNNN.json)
  5. Save to outputs/{CLIENT}/{DOMAIN}/chunks/

OUTPUT: 4,700 chunks
COST: $0
       ↓
─────────────────────────────────────────────────────────────
L3: LLM CLASSIFY & EXTRACT (classify_all_with_retry.sh)
─────────────────────────────────────────────────────────────
  1. Find all chunk_*.json files
  2. Process in parallel (30 concurrent via xargs)
  3. For each chunk:
     a. Build prompt with page markdown
     b. Call Claude Sonnet 4 via POST /v1/messages
     c. Retry up to 10 times (exponential backoff)
     d. Validate response has .content[0].text
     e. Save to llm_responses/response_chunk_*.json
  4. Skip already-processed chunks (resume)

OUTPUT: 4,550 responses (150 failed)
COST: $211.50 (avg $0.045/page × 4,700)
       ↓
─────────────────────────────────────────────────────────────
L4: DEDUPE & EXPORT (export_final_robust.py)
─────────────────────────────────────────────────────────────
  1. Load all response_chunk_*.json files
  2. Parse each response:
     a. Extract .content[0].text (Claude format)
     b. Strip markdown code blocks
     c. Parse JSON
     d. Extract companies_extracted[] array
  3. Deduplication:
     a. Prioritize companies with domains
     b. Keep first occurrence per domain
     c. Keep name-only if name doesn't exist with domain
  4. Export:
     a. JSON: metadata + companies array
     b. CSV: name, domain, website_original, classification_type, source_file

OUTPUT:
  - {DOMAIN}_{TIMESTAMP}.csv (3,171 unique companies)
  - {DOMAIN}_{TIMESTAMP}.json
COST: $0
       ↓
COPY TO CLIENT OUTPUTS
  └─ cp to client_outputs/{CLIENT}/{DOMAIN}/
       ↓
FINAL SUMMARY (logged)
  - Companies extracted: 3,171
  - With domains: 3,171 (100%)
  - Output: client_outputs/doppel/paginasamarillas/
```

---

## 🔧 Configuration

### **Environment Variables** (`.env` in parent directory)

```bash
FIRECRAWL_API_KEY=fc-xxxxx
ANTHROPIC_API_KEY=sk-ant-xxxxx
```

### **Firecrawl Settings** (in `run_pipeline_robust.sh:159-174`)

```json
{
  "url": "$TARGET_URL",
  "allowSubdomains": true,           // Crawl blog.example.com if starting from example.com
  "limit": 20000,                     // Max 20,000 pages
  "maxConcurrency": 50,               // Process 50 pages simultaneously
  "maxDiscoveryDepth": 5,             // Follow links 5 clicks deep
  "allowExternalLinks": false,        // Stay on same domain + subdomains
  "scrapeOptions": {
    "formats": ["markdown"],          // Return markdown content
    "onlyMainContent": true,          // Strip navigation/footer
    "blockAds": true                  // Remove advertisements
  }
}
```

### **Claude Settings** (in `classify_chunk.sh:145-148`)

```json
{
  "model": "claude-sonnet-4-5-20250929",
  "max_tokens": 8192,
  "temperature": 0,
  "messages": [{"role": "user", "content": "..."}]
}
```

### **Concurrency Settings**

```bash
# L3 Classification (classify_all_with_retry.sh:36)
CONCURRENCY=30  # Process 30 chunks in parallel

# Retry Logic (classify_chunk.sh:134)
MAX_RETRIES=10  # Up to 10 retries per chunk
WAIT_TIME=$((2 ** RETRY_COUNT))  # Exponential backoff: 2s, 4s, 8s, 16s, 32s, 64s
```

---

## 💰 Cost Model

### **Per Run (Example: paginasamarillas.es)**

```
L1 Firecrawl Crawl:
  - Pages crawled: 4,700
  - Cost per page: $0.025
  - Total: $117.50

L2 Merge & Chunk:
  - Cost: $0 (local processing)

L3 LLM Classification:
  - Model: Claude Sonnet 4
  - Pages classified: 4,550 (150 failed)
  - Average per page: ~$0.045
  - Total: $204.75

L4 Dedupe & Export:
  - Cost: $0 (local processing)

─────────────────────────────────
TOTAL: ~$322.25
```

### **Cost by Model**

```
Claude Haiku 3.5:
  $0.80/1M input, $4/1M output
  Average: ~$0.003/page

Claude Sonnet 4:
  $3/1M input, $15/1M output
  Average: ~$0.045/page (15x more than Haiku)

Claude Opus 4:
  $15/1M input, $75/1M output
  Average: ~$0.225/page (75x more than Haiku)
```

### **Cost by Crawl Size**

```
1,000 pages:
  Firecrawl: $25
  Claude Sonnet 4: $45
  Total: ~$70

10,000 pages:
  Firecrawl: $250
  Claude Sonnet 4: $450
  Total: ~$700

20,000 pages:
  Firecrawl: $500
  Claude Sonnet 4: $900
  Total: ~$1,400
```

---

## 🛡️ Error Handling

### **Approach**: Exit on Failure (`set -e`)

**Philosophy**:
- Any layer failure stops the pipeline
- Manual intervention required
- No automatic re-runs

### **Validation Points**

**Pre-flight** (run_pipeline_robust.sh:66-140):
```bash
# Check 1: API Keys
if [ -z "$FIRECRAWL_API_KEY" ]; then
    log_error "FIRECRAWL_API_KEY not set"
    exit 1
fi

# Check 2: Disk Space (500MB minimum)
AVAILABLE_MB=$(df -m "$QUEUE_SYSTEM_DIR" | tail -1 | awk '{print $4}')
if [ "$AVAILABLE_MB" -lt 500 ]; then
    log_error "Insufficient disk space: ${AVAILABLE_MB}MB"
    exit 1
fi

# Check 3: Network Connectivity
if ! curl -s --max-time 5 https://api.firecrawl.dev/v2/health > /dev/null; then
    log_error "Cannot reach Firecrawl API"
    exit 1
fi

# Check 4: Python Dependencies
if ! python3 -c "import requests, json" 2>/dev/null; then
    log_error "Python dependencies missing"
    exit 1
fi

# Check 5: Required Tools
for cmd in jq curl bash; do
    if ! command -v $cmd &> /dev/null; then
        log_error "$cmd not found"
        exit 1
    fi
done
```

**Per-Layer Validation** (run_pipeline_robust.sh:194-298):
```bash
# After L1
SEGMENT_COUNT=$(find "$SEGMENTS_DIR" -name "segment_*.json" | wc -l)
if [ "$SEGMENT_COUNT" -eq 0 ]; then
    log_error "L1 failed - no segment files found"
    exit 1
fi

# After L2
CHUNK_COUNT=$(find "$CHUNKS_DIR" -name "chunk_*.json" | wc -l)
if [ "$CHUNK_COUNT" -eq 0 ]; then
    log_error "L2 failed - no chunk files found"
    exit 1
fi

# After L3
RESPONSE_COUNT=$(find "$RESPONSES_DIR" -name "response_chunk_*.json" | wc -l)
if [ "$RESPONSE_COUNT" -eq 0 ]; then
    log_error "L3 failed - no response files found"
    exit 1
fi

# After L4
if [ ! -f "$FINAL_CSV" ]; then
    log_error "L4 failed - CSV not created"
    exit 1
fi

COMPANY_COUNT=$(tail -n +2 "$FINAL_CSV" | wc -l)
if [ "$COMPANY_COUNT" -eq 0 ]; then
    log_error "L4 failed - no companies in CSV"
    exit 1
fi
```

### **Retry Logic**

**L1 (Firecrawl Polling)** - Exponential backoff:
```python
retries = 0
max_retries = 10
while True:
    try:
        resp = requests.get(url, timeout=30)
        # Process response
        retries = 0  # Reset on success

    except Exception as e:
        retries += 1
        if retries > max_retries:
            print(f"❌ Max retries exceeded")
            sys.exit(1)
        time.sleep(10 * retries)  # 10s, 20s, 30s, ...
```

**L3 (Claude API)** - Exponential backoff (capped at 60s):
```bash
MAX_RETRIES=10
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    curl -X POST https://api.anthropic.com/v1/messages ... \
        -o response.json

    # Check if valid
    if jq -e '.content[0].text' response.json > /dev/null; then
        break  # Success
    fi

    RETRY_COUNT=$((RETRY_COUNT + 1))
    WAIT_TIME=$((2 ** RETRY_COUNT))  # 2s, 4s, 8s, 16s, 32s, 64s

    if [ $WAIT_TIME -gt 60 ]; then
        WAIT_TIME=60  # Cap at 60s
    fi

    sleep $WAIT_TIME
done
```

---

## 📁 Directory Structure

```
crawl_system/
├── queue_system/                    # Production queue system
│   ├── queue/                       # Queue state files
│   │   ├── queue.txt                # Pending: CLIENT|DOMAIN|URL
│   │   ├── active.json              # Running: {job_id: {url, pid, started}}
│   │   ├── completed.txt            # Done: CLIENT/DOMAIN|URL|timestamp
│   │   ├── failed.txt               # Failed: CLIENT/DOMAIN|URL|timestamp
│   │   └── manager.log              # Queue manager log
│   │
│   ├── outputs/                     # Per-job outputs
│   │   └── {CLIENT}/
│   │       └── {DOMAIN}/
│   │           ├── segments/        # L1 output
│   │           ├── chunks/          # L2 output
│   │           ├── llm_responses/   # L3 output
│   │           ├── {DOMAIN}_{TS}.csv  # L4 CSV
│   │           └── {DOMAIN}_{TS}.json # L4 JSON
│   │
│   ├── logs/                        # Per-job logs
│   │   └── {CLIENT}/
│   │       └── {DOMAIN}/
│   │           └── {DOMAIN}_{TS}.log
│   │
│   ├── scripts/                     # Pipeline implementation
│   │   ├── run_pipeline_robust.sh   # Main orchestrator
│   │   ├── l1_crawl_with_markdown/
│   │   │   └── fetch_segments.py
│   │   ├── l2_merge_and_chunk/
│   │   │   └── merge_and_split_robust.py
│   │   ├── l3_llm_classify_extract/
│   │   │   ├── classify_all_with_retry.sh
│   │   │   └── scripts/
│   │   │       └── classify_chunk.sh
│   │   └── l4_dedupe_and_export/
│   │       └── export_final_robust.py
│   │
│   ├── queue_add.sh                 # Add job to queue
│   ├── queue_status.sh              # View queue status
│   └── queue_manager.sh             # Background daemon
│
├── client_outputs/                  # Final CSVs (auto-copied)
│   └── {CLIENT}/
│       └── {DOMAIN}/
│           └── {DOMAIN}_{TS}.csv
│
├── main_pipeline/                   # Legacy single-job pipeline
│   └── (same structure as queue_system/scripts)
│
├── run_pipeline.sh                  # Legacy single-job runner
├── README.md                        # User documentation
└── ARCHITECTURE.md                  # This file
```

---

## 🚀 Usage

### **Add Job to Queue**

```bash
cd crawl_system/queue_system
./queue_add.sh "doppel" "https://paginasamarillas.es/search/clinicas-madrid"
```

### **Start Queue Manager** (if not running)

```bash
nohup ./queue_manager.sh > logs/queue_manager.log 2>&1 &
```

### **Check Queue Status**

```bash
./queue_status.sh
```

Output:
```
╔════════════════════════════════════════════════════════════════╗
║         ROBUST QUEUE SYSTEM STATUS                            ║
╚════════════════════════════════════════════════════════════════╝

⚙️  ACTIVE JOBS:
   doppel/paginasamarillas → PID: 12345 (started: 2025-11-14 10:30:00)

📋 PENDING QUEUE:
   Total jobs: 3

   1. doppel/rentechdigital
      https://rentechdigital.com/directory
   2. toolbx/phccweb
      https://eweb.phccweb.org/member-directory
   3. fuse/neurology
      https://example.com/neurology-clinics

📊 STATISTICS:
   ✅ Completed: 15
   ❌ Failed:    2
```

### **Monitor Active Job**

```bash
tail -f logs/doppel/paginasamarillas/paginasamarillas_20251114_103000.log
```

### **Run Single Job** (without queue)

```bash
cd crawl_system
CLIENT=doppel DOMAIN=test ./run_pipeline.sh "https://example.com"
```

---

## 🎯 Production Results

### **Doppel Client** (November 2025)

| Domain | Pages | Companies | Domains | Success Rate |
|--------|-------|-----------|---------|--------------|
| paginasamarillas.es | 10,747 | 10,747 | 3,171 | 29% |
| rentechdigital.com | 7,279 | 7,279 | 3,656 | 50% |
| whatclinic.com | 953 | 953 | 16 | 1.7% |
| clinicinspain (cosmetic) | 11 | 11 | 11 | 100% |
| clinicinspain (dental) | 48 | 48 | 27 | 56% |
| clinicinspain (implants) | 15 | 15 | 14 | 93% |

**Total**: 19,053 companies, 6,895 domains (36%)

### **Toolbx Client** (November 2025)

| Domain | Pages | Companies | Domains | Success Rate |
|--------|-------|-----------|---------|--------------|
| eweb.phccweb.org | 225 | 225 | 188 | 84% |
| phccconnect2025 | 93 | 93 | 86 | 92% |

**Total**: 318 companies, 274 domains (86%)

---

## ⚠️ Known Limitations

### **1. Directory Sites with Click-Through Design**

**Problem**: Sites like whatclinic.com have low domain extraction rates (1.7%)

**Cause**:
- Clinic websites not displayed as text on listing pages
- Require clicking into detail pages to see website
- Website URLs often in buttons/links (not rendered in markdown)

**Solution**: Use sites where websites are clearly displayed as text (e.g., clinicinspain.com = 70-100% success)

### **2. Failed Crawls**

**doctoralia.es** - Timeout (empty response)
- Issue: `curl -s` suppresses errors, no timeout configured
- Result: Pipeline waits indefinitely

**dnb.com** - Anti-bot protection
- Heavy rate limiting
- 502 errors
- Crawl too slow (1,202/4,725 pages in 2 hours)

### **3. Error Handling**

**Exit on Failure** - Pipeline stops, all work lost
- No automatic re-runs
- No partial results saved
- Manual intervention required

### **4. Hard-Coded Prompt**

**Single Extraction Pattern** - Hard-coded in `classify_chunk.sh:55-130`
- Cannot easily change extraction fields
- Cannot reuse for different use cases
- Prompt embedded in bash script

### **5. No Progress Tracking**

**Limited Observability**
- No real-time progress file
- No cost tracking during execution
- No diagnostics per layer
- Only basic logs

### **6. No Domain Deduplication During Pipeline**

**Duplicate Processing**
- Same domain scraped multiple times (e.g., Mayo Clinic in 15 cities)
- Wastes API calls
- Wastes classification costs
- Only deduplicated at final export

---

## 🔄 Comparison with crawl_system_prod

| Feature | crawl_system (Legacy) | crawl_system_prod (Planned) |
|---------|----------------------|---------------------------|
| **Architecture** | Bash + Python scripts | Python OOP (3,600+ LOC) |
| **Configuration** | Hard-coded in scripts | YAML configs + JSON specs |
| **Crawl & Extraction** | Tightly coupled | Decoupled (mix-and-match) |
| **Error Handling** | Exit on failure | Continue + retry + re-run |
| **Progress Tracking** | Logs only | Real-time progress.json |
| **Cost Tracking** | Post-hoc calculation | Real-time with budget limits |
| **Diagnostics** | Basic logs | Per-layer diagnostics files |
| **Failure Tracking** | None | failures_l{N}.json for re-runs |
| **Domain Dedup** | Final export only | In-pipeline cache (L2-L4) |
| **Retry Logic** | Per-chunk (10 retries) | Configurable per layer |
| **Resume Capability** | Partial (L3 only) | Full (all layers) |
| **Observability** | Minimal | Comprehensive (6 output files) |
| **Testability** | Difficult (bash scripts) | Easy (modular Python) |
| **Extensibility** | Edit scripts | Add configs/specs |

---

**Created**: 2025-11-14
**Purpose**: Document legacy crawl_system architecture for comparison and migration planning
**Status**: Complete
