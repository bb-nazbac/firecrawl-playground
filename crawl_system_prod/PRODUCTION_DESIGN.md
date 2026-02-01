# Crawl System - Production Design v2.0

**Status**: 🚧 Design Phase
**Created**: 2025-11-14
**Updated**: 2025-11-14
**Confidence**: 95%

---

## 📐 Core Philosophy

**User Mental Model:**
> I want to crawl **[TARGET URL]** and extract **[COMPANY DATA]** using **[EXTRACTION SPEC]**, for **[CLIENT]**

**Key Insight: Crawling and Extraction are Decoupled**
- Crawl configuration changes per target (flexible)
- Extraction spec is reusable (mix-and-match)
- Same crawl can use different extraction specs
- Same extraction spec can apply to different crawls

**Configuration Approach:**
- **YAML run config**: What to crawl + which extraction to use
- **JSON extraction spec**: How to extract data (reusable across crawls)
- **Complete CSV output**: All data + reasoning + evidence (user filters in Excel)

---

## 🎯 User Workflow

### **Step 1: Create Run Config**

```yaml
# /configs/runs/doppel_paginasamarillas.yaml

client: doppel

# What to crawl
crawl:
  target_url: "https://www.paginasamarillas.es/search/clinics-madrid"
  allow_subdomains: true
  limit: 20000
  max_concurrency: 50
  max_depth: 5
  allow_external_links: false

# How to extract company data
extraction_spec: spanish_clinic_extraction

# Optional: Test with small subset
test_mode: 10  # Process only 10 pages
```

### **Step 2: Run Pipeline**

```bash
python run_pipeline.py doppel_paginasamarillas
```

### **Step 3: Get Complete CSV**

```csv
company_name,domain,website,phone,address,extraction_confidence,extraction_reasoning,extraction_evidence,source_url,tokens_input,tokens_output
Clinica Dental Madrid,clinicadentalmadrid.es,https://clinicadentalmadrid.es,+34 91 123 4567,"Calle Mayor 10, Madrid",high,"Clear company listing with contact details","Found on main content: 'Clinica Dental Madrid - Contact: +34 91...'",https://paginasamarillas.es/clinica-123,8234,189
```

### **Step 4: Filter & Analyze in Excel**

Filter/sort by any column:
- High confidence only: `extraction_confidence="high"`
- With domains: `domain != ""`
- Read reasoning for any extraction

---

## 🔄 Mix-and-Match Examples

### **Same Crawl, Different Extraction:**

```yaml
# Run 1: Extract basic company info
crawl:
  target_url: "https://paginasamarillas.es/search/clinics"
extraction_spec: basic_company_extraction

# Run 2: Extract detailed clinic info (same crawl!)
crawl:
  target_url: "https://paginasamarillas.es/search/clinics"
extraction_spec: detailed_clinic_extraction
```

### **Different Crawl, Same Extraction:**

```yaml
# Run 1: Spanish yellow pages
crawl:
  target_url: "https://paginasamarillas.es/search/clinics"
extraction_spec: basic_company_extraction

# Run 2: Italian yellow pages (same extraction!)
crawl:
  target_url: "https://paginegialle.it/search/cliniche"
extraction_spec: basic_company_extraction
```

---

## 📁 Directory Structure

```
/crawl_system_prod/

  # User edits these per run
  /configs/
    /runs/
      TEMPLATE.yaml                              ← Template to copy
      doppel_paginasamarillas.yaml               ← Crawl + Extraction combo
      doppel_rentechdigital.yaml                 ← Different combo
      toolbx_phccweb.yaml                        ← Another client

    # Reusable extraction specs
    /specs/
      /extraction/
        TEMPLATE.json                            ← Template to copy
        basic_company_extraction.json            ← Reusable extraction
        detailed_clinic_extraction.json          ← Reusable extraction
        spanish_clinic_extraction.json           ← Reusable extraction
        restaurant_extraction.json               ← Reusable extraction

  # Core infrastructure
  /core/
    __init__.py
    config_loader.py                 # YAML config validation
    spec_loader.py                   # JSON spec validation
    progress_tracker.py              # Real-time progress
    cost_tracker.py                  # Cost tracking
    diagnostics.py                   # Diagnostics & failures
    domain_cache.py                  # Deduplication cache
    layer_crawl.py                   # L1: Firecrawl Crawl
    layer_merge.py                   # L2: Merge Segments
    layer_chunk.py                   # L3: Create Chunks
    layer_classify.py                # L4: LLM Extract
    layer_export.py                  # L5: Export CSV
    layer_dedupe.py                  # L6: Deduplicate

  # Client outputs (isolated per run)
  /outputs/
    /{client}/
      /run_{run_id}/
        # Final results
        final_results.csv

        # Progress tracking
        progress.json

        # Per-layer diagnostics
        diagnostics_l1_crawl.json
        diagnostics_l2_merge.json
        diagnostics_l3_chunk.json
        diagnostics_l4_classify.json
        diagnostics_l5_export.json
        diagnostics_l6_dedupe.json

        # Failure tracking (for re-runs)
        failures_l1_crawl.json
        failures_l4_classify.json

        # Cost breakdown
        costs.json

        # Exhaustive logs
        run.log

        # Raw data (per layer)
        /l1_segments/
          segment_001.json
          segment_002.json
        /l2_merged/
          merged_data.json
        /l3_chunks/
          chunk_0001.json
          chunk_0002.json
        /l4_classified/
          response_chunk_0001.json
          response_chunk_0002.json

        # Temporary cache (24hr TTL)
        .cache_domains_24hr.json

  # Entry point
  run_pipeline.py                                ← Main orchestrator

  # Documentation
  PRODUCTION_DESIGN.md                           ← This file
  README.md                                      ← User guide
```

---

## 📄 Run Config Format (YAML)

### **Template:**

```yaml
# /configs/runs/TEMPLATE.yaml

#══════════════════════════════════════════════════════════════
# WHO IS THIS FOR?
#══════════════════════════════════════════════════════════════

# Client identifier (string)
# Creates isolated output folders: /outputs/{client}/
client: doppel

#══════════════════════════════════════════════════════════════
# CRAWL CONFIGURATION (WHAT to crawl)
#══════════════════════════════════════════════════════════════

crawl:
  # Target URL to crawl (string)
  # Starting point for the crawl
  # Examples:
  #   "https://paginasamarillas.es/search/clinics-madrid"
  #   "https://rentechdigital.com/directory"
  #   "https://whatclinic.com/dentists/spain"
  target_url: "https://paginasamarillas.es/search/clinics-madrid"

  # Allow subdomains (boolean)
  # true: Crawl blog.example.com if starting from example.com
  # false: Stay on exact domain
  allow_subdomains: true

  # Page limit (integer)
  # Maximum pages to crawl
  # Typical: 1000 (small site) | 10000 (medium) | 20000 (large)
  limit: 20000

  # Max concurrency (integer)
  # How many pages to scrape simultaneously
  # Typical: 30 (conservative) | 50 (standard) | 100 (aggressive)
  max_concurrency: 50

  # Max discovery depth (integer)
  # How many clicks deep to follow links
  # Typical: 3 (shallow) | 5 (standard) | 10 (deep)
  max_depth: 5

  # Allow external links (boolean)
  # true: Follow links to other domains
  # false: Stay on same domain (+ subdomains)
  allow_external_links: false

  # Scrape options
  scrape_options:
    formats: ["markdown"]
    only_main_content: true
    block_ads: true

#══════════════════════════════════════════════════════════════
# EXTRACTION CONFIGURATION (HOW to extract company data)
#══════════════════════════════════════════════════════════════

# Extraction spec name (string)
# References: /configs/specs/extraction/{extraction_spec}.json
# Examples:
#   basic_company_extraction
#   detailed_clinic_extraction
#   spanish_clinic_extraction
extraction_spec: spanish_clinic_extraction

#══════════════════════════════════════════════════════════════
# OPTIONAL OVERRIDES (Usually leave commented out)
#══════════════════════════════════════════════════════════════

# Test mode: Process only first N pages (integer or null)
# test_mode: 10

# Resume mode: Continue from previous run (boolean)
# resume: true

# Start from stage: Skip earlier stages (string)
# Options: crawl | merge | chunk | classify | export | dedupe
# start_from: classify

# Max cost limit: Warn if exceeded (integer or null)
# max_cost_usd: 500

# Concurrency: Threads for classification (integer)
# concurrency: 30

# Dry run: Preview without executing (boolean)
# dry_run: true
```

---

## 📄 Extraction Spec Format (JSON)

### **Template:**

```json
// /configs/specs/extraction/TEMPLATE.json
{
  "spec_name": "spanish_clinic_extraction",
  "description": "Extract clinic/company data from Spanish directory sites",

  // ────────────────────────────────────────────────────────────
  // CLASSIFICATION CATEGORIES (Optional)
  // ────────────────────────────────────────────────────────────

  "categories": [
    {
      "id": "company_listing",
      "label": "Company Listing",
      "description": "Page contains company/business information"
    },
    {
      "id": "directory_page",
      "label": "Directory Page",
      "description": "Page is a list/directory of multiple companies"
    },
    {
      "id": "other",
      "label": "Other",
      "description": "Not a company listing"
    }
  ],

  // ────────────────────────────────────────────────────────────
  // EXTRACTION FIELDS
  // ────────────────────────────────────────────────────────────

  "extraction_fields": {
    "company_name": {
      "type": "string",
      "required": true,
      "description": "Official name of company or business"
    },
    "domain": {
      "type": "string",
      "required": false,
      "description": "Website domain (e.g., example.com)"
    },
    "website": {
      "type": "string",
      "required": false,
      "description": "Full website URL (e.g., https://example.com)"
    },
    "phone": {
      "type": "string",
      "required": false,
      "description": "Primary contact phone number"
    },
    "email": {
      "type": "string",
      "required": false,
      "description": "Contact email address"
    },
    "address": {
      "type": "string",
      "required": false,
      "description": "Full street address"
    },
    "city": {
      "type": "string",
      "required": false,
      "description": "City location"
    },
    "postal_code": {
      "type": "string",
      "required": false,
      "description": "Postal/ZIP code"
    },
    "country": {
      "type": "string",
      "required": false,
      "description": "Country (if specified)"
    },
    "description": {
      "type": "string",
      "required": false,
      "description": "Company description or services offered"
    }
  },

  // ────────────────────────────────────────────────────────────
  // EXTRACTION QUESTIONS (Yes/No with reasoning)
  // ────────────────────────────────────────────────────────────

  "questions": [
    {
      "field": "has_website",
      "question": "Does this listing include a website URL?",
      "answer_type": "boolean",
      "reasoning_required": true,
      "reasoning_max_length": 100,
      "evidence_required": true
    },
    {
      "field": "has_contact_info",
      "question": "Does this listing include phone or email?",
      "answer_type": "boolean",
      "reasoning_required": true,
      "reasoning_max_length": 100,
      "evidence_required": false
    }
  ],

  // ────────────────────────────────────────────────────────────
  // LLM CONFIGURATION
  // ────────────────────────────────────────────────────────────

  "llm": {
    "model": "claude-3-5-haiku-20241022",
    "max_tokens": 1500,
    "temperature": 0
  }
}
```

---

## 🔄 Data Flow

```
RUN CONFIG (user fills out)
  ├─ client: "doppel"
  ├─ crawl:
  │   ├─ target_url: "https://paginasamarillas.es/search/clinics"
  │   ├─ limit: 20000
  │   └─ max_concurrency: 50
  └─ extraction_spec: "spanish_clinic_extraction"
       ↓
SYSTEM LOADS EXTRACTION SPEC
  └─ /configs/specs/extraction/spanish_clinic_extraction.json
       ↓
L1: CRAWL (Firecrawl)
  ├─ Initiate crawl with target_url
  ├─ Poll for completion (5s intervals)
  ├─ Fetch all segments (paginated API)
  └─ Output: segment_001.json, segment_002.json, ...
       ↓
L2: MERGE SEGMENTS
  ├─ Load all segment files
  ├─ Merge into single dataset
  ├─ Extract all pages with markdown
  └─ Output: merged_data.json (all pages)
       ↓
L3: CHUNK PAGES
  ├─ Split merged data into chunks
  ├─ 1 page per chunk (for LLM processing)
  └─ Output: chunk_0001.json, chunk_0002.json, ...
       ↓
L4: CLASSIFY & EXTRACT (Claude)
  ├─ Use extraction spec:
  │   - Categories (optional)
  │   - Extraction fields
  │   - Questions (yes/no with reasoning)
  └─ Output: Structured JSON per chunk
       {
         "company_name": "Clinica Dental Madrid",
         "domain": "clinicadentalmadrid.es",
         "website": "https://clinicadentalmadrid.es",
         "phone": "+34 91 123 4567",
         "has_website": true,
         "has_website_reasoning": "URL found in contact section",
         "has_website_evidence": "Visit us: https://clinicadentalmadrid.es"
       }
       ↓
L5: EXPORT (CSV)
  ├─ Combine all L4 results
  ├─ Include ALL results (no filtering)
  ├─ Include reasoning columns
  └─ Output: Complete CSV
       ↓
L6: DEDUPLICATE (Domain normalization)
  ├─ Add normalized_domain column
  ├─ Keep first occurrence per domain
  └─ Output: Deduplicated CSV
       ↓
FINAL OUTPUT
  └─ /outputs/{client}/run_{run_id}/final_results.csv
```

---

## 📊 CSV Output Structure

### **Columns:**

```
Basic Information:
  - company_name               (string)
  - domain                     (string or null)
  - website                    (string or null)
  - phone                      (string or null)
  - email                      (string or null)
  - address                    (string or null)
  - city                       (string or null)
  - postal_code                (string or null)
  - country                    (string or null)
  - description                (string or null)

Extraction Results (depends on spec):
  - has_website                (TRUE | FALSE)
  - has_website_reasoning      (text, max 100 chars)
  - has_website_evidence       (text)
  - has_contact_info           (TRUE | FALSE)
  - has_contact_reasoning      (text, max 100 chars)
  - extraction_confidence      (high | medium | low)

Metadata:
  - source_url                 (original URL from crawl)
  - classified_at              (ISO timestamp)
  - normalized_domain          (for deduplication)
  - tokens_input               (Claude usage)
  - tokens_output              (Claude usage)
```

---

## 💰 Cost Model

### **Cost Breakdown:**

```
L1 Crawl:         $117.50    (4,700 pages × $0.025 via Firecrawl)
L2 Merge:         $0         (local processing)
L3 Chunk:         $0         (local processing)
L4 Classification: $14.10    (4,700 pages × $0.003 avg Claude Haiku)
L5 Export:        $0         (local processing)
L6 Deduplication: $0         (local processing)
────────────────────────────
Total:            ~$131.60
```

### **Cost Varies by Model:**

```
Claude Haiku 3.5 (claude-3-5-haiku-20241022):
  $0.80/1M input tokens, $4/1M output tokens
  Average per page: ~$0.003

Claude Sonnet 4 (claude-sonnet-4-20250514):
  $3/1M input tokens, $15/1M output tokens
  Average per page: ~$0.045 (15x more expensive)

Claude Opus 4 (claude-opus-4-20250514):
  $15/1M input tokens, $75/1M output tokens
  Average per page: ~$0.225 (75x more expensive)
```

### **Cost by Crawl Size:**

```
1,000 pages:
  Firecrawl: $25
  Claude Haiku: $3
  Total: ~$28

10,000 pages:
  Firecrawl: $250
  Claude Haiku: $30
  Total: ~$280

20,000 pages:
  Firecrawl: $500
  Claude Haiku: $60
  Total: ~$560
```

---

## 🛡️ EFFICIENCY, RETRIES & ERROR HANDLING

### **Core Philosophy: "Re-run Failures, Not Abort"**

- Pipeline continues running despite failures
- All failures tracked in detail for later re-runs
- Exhaustive diagnostics per layer
- No data loss - every decision logged

---

### **📊 Output Structure Per Run**

Every run creates an isolated folder with complete diagnostics:

```
/outputs/{client}/run_{run_id}/

  # Final deliverable
  final_results.csv

  # Real-time tracking
  progress.json

  # Per-layer diagnostics
  diagnostics_l1_crawl.json
  diagnostics_l2_merge.json
  diagnostics_l3_chunk.json
  diagnostics_l4_classify.json
  diagnostics_l5_export.json
  diagnostics_l6_dedupe.json

  # Re-run capability
  failures_l1_crawl.json
  failures_l4_classify.json

  # Cost breakdown
  costs.json

  # Exhaustive logs
  run.log

  # Raw layer outputs
  /l1_segments/
  /l2_merged/
  /l3_chunks/
  /l4_classified/

  # Temporary cache (24hr)
  .cache_domains_24hr.json
```

---

### **📈 Progress Tracking (progress.json)**

**Real-time progress file updated throughout run:**

```json
{
  "run_id": "run_20251114_103000",
  "config_file": "configs/runs/doppel_paginasamarillas.yaml",
  "client": "doppel",
  "status": "running",
  "started_at": "2025-11-14T10:30:00Z",
  "updated_at": "2025-11-14T12:15:00Z",

  "layers": {
    "L1_crawl": {
      "status": "completed",
      "pages_crawled": 4700,
      "segments_fetched": 47,
      "duration_seconds": 3600
    },
    "L2_merge": {
      "status": "completed",
      "pages_merged": 4700,
      "duration_seconds": 30
    },
    "L3_chunk": {
      "status": "completed",
      "chunks_created": 4700,
      "duration_seconds": 15
    },
    "L4_classify": {
      "status": "running",
      "pages_classified": 2300,
      "pages_remaining": 2400,
      "failures": 15
    }
  },

  "costs": {
    "total_usd": 85.50,
    "remaining_budget_usd": 414.50,
    "max_limit_usd": 500,
    "warnings": []
  },

  "elapsed_seconds": 6300,
  "estimated_completion": "2025-11-14T13:00:00Z"
}
```

---

### **🔬 Layer Diagnostics (diagnostics_l{N}.json)**

**Example: diagnostics_l1_crawl.json**

```json
{
  "layer": "L1_CRAWL",
  "run_id": "run_20251114_103000",
  "started_at": "2025-11-14T10:30:00Z",
  "completed_at": "2025-11-14T11:30:00Z",
  "duration_seconds": 3600,

  "summary": {
    "crawl_id": "7344a202-f3c4-4864-820a-d5fdd245e7ff",
    "target_url": "https://paginasamarillas.es/search/clinics",
    "pages_crawled": 4700,
    "pages_requested": 10000,
    "pages_success_rate": 47.0,

    "segments_total": 47,
    "segments_fetched": 47,
    "segments_failed": 0,

    "poll_attempts": 720,
    "poll_duration_seconds": 3600
  },

  "costs": {
    "api": "firecrawl",
    "total_usd": 117.50,
    "pages_billed": 4700,
    "cost_per_page": 0.025
  },

  "failures": []
}
```

**Example: diagnostics_l4_classify.json**

```json
{
  "layer": "L4_CLASSIFY",
  "run_id": "run_20251114_103000",
  "started_at": "2025-11-14T11:45:00Z",
  "completed_at": "2025-11-14T12:15:00Z",
  "duration_seconds": 1800,

  "summary": {
    "chunks_total": 4700,
    "chunks_attempted": 4700,
    "chunks_successful": 4550,
    "chunks_failed": 150,

    "retries_total": 450,
    "retries_successful": 400,
    "retries_exhausted": 50,

    "success_rate_percent": 96.8
  },

  "costs": {
    "api": "anthropic",
    "model": "claude-3-5-haiku-20241022",
    "total_usd": 13.65,
    "pages_classified": 4550,
    "tokens_input": 13650000,
    "tokens_output": 910000,
    "pricing": {
      "cost_per_1m_input": 0.80,
      "cost_per_1m_output": 4.00
    },
    "breakdown": {
      "input_cost_usd": 10.92,
      "output_cost_usd": 2.73
    }
  },

  "failure_breakdown": {
    "timeout": 80,
    "529_overloaded": 40,
    "invalid_json_response": 20,
    "rate_limit": 10
  },

  "failures": [
    {
      "chunk_file": "chunk_0123.json",
      "source_url": "https://paginasamarillas.es/clinic-123",
      "error_type": "timeout",
      "retries_attempted": 3,
      "last_error": "Request timeout after 60s",
      "timestamp": "2025-11-14T12:05:00Z",
      "can_retry": true
    }
  ]
}
```

---

### **💰 Cost Tracking (costs.json)**

**Accurate cost breakdown per API and model:**

```json
{
  "run_id": "run_20251114_103000",
  "total_cost_usd": 131.15,
  "max_cost_limit_usd": 500,
  "remaining_budget_usd": 368.85,
  "warnings": [],

  "breakdown_by_layer": {
    "L1_crawl": {
      "api": "firecrawl",
      "cost_usd": 117.50,
      "pages_crawled": 4700,
      "cost_per_page": 0.025
    },

    "L2_merge": {
      "cost_usd": 0
    },

    "L3_chunk": {
      "cost_usd": 0
    },

    "L4_classify": {
      "api": "anthropic",
      "model": "claude-3-5-haiku-20241022",
      "cost_usd": 13.65,
      "pages_classified": 4550,
      "tokens_input": 13650000,
      "tokens_output": 910000,
      "pricing": {
        "cost_per_1m_input": 0.80,
        "cost_per_1m_output": 4.00
      },
      "breakdown": {
        "input_cost_usd": 10.92,
        "output_cost_usd": 2.73
      }
    },

    "L5_export": {
      "cost_usd": 0
    },

    "L6_dedupe": {
      "cost_usd": 0
    }
  }
}
```

---

### **🔄 Retry Logic**

**L1 (Crawl): Poll-based (no explicit retries)**
```python
L1_POLL_CONFIG = {
  "poll_interval_seconds": 5,
  "max_poll_attempts": 1440,  # 2 hours max (1440 × 5s)
  "timeout_on": [
    "no_response_after_2_hours",
    "api_error_persistent"
  ]
}
```

**L4 (Classify): Up to 3 retries**
```python
L4_RETRY_CONFIG = {
  "max_attempts": 3,
  "backoff": "exponential",  # 5s, 10s, 20s
  "retry_on": [
    "timeout",
    "529_overloaded",
    "rate_limit",
    "invalid_json_response"
  ],
  "skip_on": [
    "401_unauthorized",
    "insufficient_quota"
  ]
}
```

**Timeout Values:**
```python
TIMEOUTS = {
  "l1_crawl_completion": 7200,   # 2 hours for Firecrawl to complete
  "l4_classify_per_page": 60     # 60 seconds per page classification
}
```

---

### **❌ Error Handling & Failure Tracking**

**Failures per layer saved for re-runs:**

**Example: failures_l4_classify.json**

```json
{
  "layer": "L4_CLASSIFY",
  "run_id": "run_20251114_103000",
  "total_failures": 150,
  "can_retry_count": 100,
  "cannot_retry_count": 50,

  "failures": [
    {
      "chunk_file": "chunk_0123.json",
      "source_url": "https://paginasamarillas.es/clinic-123",
      "error_type": "timeout",
      "error_message": "Request timeout after 60s",
      "retries_attempted": 3,
      "last_attempt": "2025-11-14T12:05:00Z",
      "can_retry": true
    },
    {
      "chunk_file": "chunk_0456.json",
      "source_url": "https://paginasamarillas.es/clinic-456",
      "error_type": "invalid_json_response",
      "error_message": "Claude returned non-JSON response",
      "retries_attempted": 3,
      "last_attempt": "2025-11-14T12:10:00Z",
      "can_retry": true
    }
  ]
}
```

---

### **🔁 Re-run Strategy**

**Command to re-run failures from previous run:**

```bash
python run_pipeline.py doppel_paginasamarillas \
  --rerun-failures \
  --from-run run_20251114_103000
```

**Re-run Logic:**

```
Step 1: Load failure files from previous run
  - failures_l1_crawl.json (if any)
  - failures_l4_classify.json

Step 2: Skip completed layers
  - L1, L2, L3 already completed (use cached data)

Step 3: Re-run L4 failures only
  - Load L3 chunks that failed in previous run
  - Retry items with can_retry: true
  - Skip items that cannot be retried

Step 4: Generate new output
  - Combine previous successful results + new results
  - Export to new CSV
  - Update all diagnostics
```

---

### **🗂️ Domain Deduplication Cache (24hr)**

**Purpose:** Don't extract same domain twice in same run

**File: `.cache_domains_24hr.json`**

```json
{
  "created_at": "2025-11-14T10:30:00Z",
  "expires_at": "2025-11-15T10:30:00Z",

  "domains_seen": {
    "clinicadentalmadrid.es": {
      "first_seen_url": "https://paginasamarillas.es/clinic-123",
      "first_seen_chunk": "chunk_0123.json",
      "timestamp": "2025-11-14T11:45:00Z",
      "classified": true,
      "classify_success": true
    },
    "example-clinic.com": {
      "first_seen_url": "https://paginasamarillas.es/clinic-456",
      "first_seen_chunk": "chunk_0456.json",
      "timestamp": "2025-11-14T11:46:00Z",
      "classified": true,
      "classify_success": false
    }
  },

  "stats": {
    "pages_total": 4700,
    "domains_unique": 3171,
    "domains_duplicate": 1529,
    "domains_skipped_l4": 1529
  }
}
```

**Logic in L6 (Dedupe):**
```python
# After classification, deduplicate by domain
# Keep first occurrence per normalized domain
# Example: www.example.com → example.com
```

---

### **📝 Exhaustive Logging (run.log)**

**Human-readable log with every decision:**

```
[2025-11-14 10:30:00] INFO: ═══════════════════════════════════════
[2025-11-14 10:30:00] INFO: PIPELINE START
[2025-11-14 10:30:00] INFO: ═══════════════════════════════════════
[2025-11-14 10:30:00] INFO: Run ID: run_20251114_103000
[2025-11-14 10:30:00] INFO: Config: configs/runs/doppel_paginasamarillas.yaml
[2025-11-14 10:30:00] INFO: Client: doppel
[2025-11-14 10:30:00] INFO: Target URL: https://paginasamarillas.es/search/clinics
[2025-11-14 10:30:00] INFO: Extraction spec: spanish_clinic_extraction
[2025-11-14 10:30:00] INFO: Max cost limit: $500.00

[2025-11-14 10:30:01] INFO: ─────────────────────────────────────────
[2025-11-14 10:30:01] INFO: L1 CRAWL START
[2025-11-14 10:30:01] INFO: ─────────────────────────────────────────

[2025-11-14 10:30:01] INFO: Initiating Firecrawl crawl...
[2025-11-14 10:30:02] INFO: Crawl ID: 7344a202-f3c4-4864-820a-d5fdd245e7ff
[2025-11-14 10:30:02] INFO: Polling for completion (5s intervals)...

[2025-11-14 10:30:07] INFO: Poll 1: Status=scraping, 45/4700 pages
[2025-11-14 10:30:12] INFO: Poll 2: Status=scraping, 123/4700 pages
...
[2025-11-14 11:29:57] INFO: Poll 720: Status=completed, 4700/4700 pages

[2025-11-14 11:30:00] INFO: Fetching segments...
[2025-11-14 11:30:05] INFO: Segment 1: 100 pages
[2025-11-14 11:30:10] INFO: Segment 2: 100 pages
...
[2025-11-14 11:33:00] INFO: Segment 47: 100 pages

[2025-11-14 11:33:00] INFO: ✓ L1 Complete: 4700 pages | $117.50 | 1h 3m
[2025-11-14 11:33:00] INFO:

[2025-11-14 11:33:01] INFO: ─────────────────────────────────────────
[2025-11-14 11:33:01] INFO: L2 MERGE SEGMENTS
[2025-11-14 11:33:01] INFO: ─────────────────────────────────────────

[2025-11-14 11:33:01] INFO: Loading 47 segment files...
[2025-11-14 11:33:05] INFO: Merging 4700 pages...
[2025-11-14 11:33:30] INFO: ✓ L2 Complete: 4700 pages merged | 29s

[2025-11-14 11:33:31] INFO: ─────────────────────────────────────────
[2025-11-14 11:33:31] INFO: L3 CHUNK PAGES
[2025-11-14 11:33:31] INFO: ─────────────────────────────────────────

[2025-11-14 11:33:31] INFO: Creating chunks (1 page per chunk)...
[2025-11-14 11:33:45] INFO: ✓ L3 Complete: 4700 chunks created | 14s

[2025-11-14 11:33:46] INFO: ─────────────────────────────────────────
[2025-11-14 11:33:46] INFO: L4 CLASSIFY & EXTRACT (30 threads)
[2025-11-14 11:33:46] INFO: ─────────────────────────────────────────

[2025-11-14 11:33:50] INFO: [Thread-01] Processing chunk_0001.json
[2025-11-14 11:33:52] INFO: [Thread-01] Success: Clinica Dental Madrid | clinicadentalmadrid.es
[2025-11-14 11:33:52] INFO: Cost: $0.003 | Total: $117.50 / $500.00

[2025-11-14 11:34:00] WARN: [Thread-05] Failed: chunk_0123.json | timeout after 60s
[2025-11-14 11:34:00] INFO: [Thread-05] Retry 1/3: Wait 5s
[2025-11-14 11:34:05] INFO: [Thread-05] Retry 1 success
...

[2025-11-14 12:15:00] INFO: ✓ L4 Complete: 4550/4700 pages | $13.65 | 41m
[2025-11-14 12:15:00] WARN: Failures: 150 pages (see failures_l4_classify.json)

[2025-11-14 12:15:01] INFO: ─────────────────────────────────────────
[2025-11-14 12:15:01] INFO: L5 EXPORT & L6 DEDUPLICATE
[2025-11-14 12:15:01] INFO: ─────────────────────────────────────────

[2025-11-14 12:15:05] INFO: ✓ Exported: 4550 companies → final_results.csv
[2025-11-14 12:15:10] INFO: ✓ Deduplicated: 4550 → 3171 unique domains

[2025-11-14 12:15:10] INFO: ═══════════════════════════════════════
[2025-11-14 12:15:10] INFO: PIPELINE COMPLETE
[2025-11-14 12:15:10] INFO: ═══════════════════════════════════════
[2025-11-14 12:15:10] INFO: Duration: 1h 45m
[2025-11-14 12:15:10] INFO: Total cost: $131.15 / $500.00 (26.2%)
[2025-11-14 12:15:10] INFO: Results: outputs/doppel/run_20251114_103000/final_results.csv
```

---

## ✅ Design Principles

### **1. Crawling & Extraction Decoupled**

```
Crawl (run config) ≠ Extraction (spec)
Mix and match freely
Reuse extraction specs across different crawls
```

### **2. Complete Transparency**

```
CSV includes reasoning for every extraction
User can audit any decision
No hidden filtering
Exhaustive diagnostics per layer
```

### **3. Re-run Failures, Not Abort**

```
Pipeline continues despite failures
All failures tracked for re-runs
No data loss
Every decision logged
```

### **4. Accurate Cost Tracking**

```
Per-API cost tracking
Per-model pricing (Haiku vs Sonnet vs Opus)
Real-time budget monitoring
Cost warnings at 80% threshold
```

### **5. Domain Deduplication**

```
Don't process same domain twice
24hr temporary cache
Detailed dedup statistics
Cost savings through dedup
```

---

## 📋 Implementation Checklist

### **Core Infrastructure**
- [ ] YAML config loader with validation
- [ ] JSON spec loader with validation
- [ ] Run orchestrator (`run_pipeline.py`)
- [ ] Progress tracking system (`progress.json`)
- [ ] Cost tracking system (`costs.json`)
- [ ] Domain cache system (`.cache_domains_24hr.json`)

### **Diagnostics & Logging**
- [ ] Per-layer diagnostics writer (`diagnostics_l{N}.json`)
- [ ] Failure tracking per layer (`failures_l{N}.json`)
- [ ] Exhaustive logger (`run.log`)
- [ ] Console progress display (with progress bars)

### **L1 (Crawl)**
- [ ] Initiate Firecrawl crawl via API
- [ ] Poll for completion (5s intervals, 2hr timeout)
- [ ] Fetch all segments (paginated)
- [ ] Save segments to disk
- [ ] Cost tracking (Firecrawl pricing)
- [ ] Diagnostics integration
- [ ] Failure tracking

### **L2 (Merge)**
- [ ] Load all segment files
- [ ] Merge into single dataset
- [ ] Extract all pages with markdown
- [ ] Save merged data
- [ ] Diagnostics integration

### **L3 (Chunk)**
- [ ] Load merged data
- [ ] Split into chunks (1 page per chunk)
- [ ] Save chunks to disk
- [ ] Diagnostics integration

### **L4 (Classify)**
- [ ] Load extraction spec dynamically
- [ ] Retry logic (up to 3 retries, exponential backoff)
- [ ] JSON response cleaning (strip markdown)
- [ ] Concurrent processing (30 threads)
- [ ] Cost tracking (per-model pricing)
- [ ] Diagnostics integration
- [ ] Failure tracking

### **L5 (Export)**
- [ ] Load all L4 responses
- [ ] Export ALL results (no filtering)
- [ ] Include reasoning columns
- [ ] Include evidence columns
- [ ] CSV generation

### **L6 (Dedupe)**
- [ ] Domain normalization
- [ ] Keep first occurrence per domain
- [ ] Dedup statistics
- [ ] Final CSV output

### **Re-run Capability**
- [ ] `--rerun-failures` flag implementation
- [ ] Load previous failures
- [ ] Skip completed layers
- [ ] Combine previous + new results

### **Documentation**
- [ ] Update README.md with workflow
- [ ] Create 3-5 extraction spec examples
- [ ] Create 5+ run config examples
- [ ] Re-run failures guide

---

## 🚀 Usage Examples

### **Example 1: Spanish Yellow Pages (Clinics)**

```yaml
# configs/runs/doppel_paginasamarillas.yaml
client: doppel
crawl:
  target_url: "https://www.paginasamarillas.es/search/clinicas-madrid"
  limit: 20000
  max_concurrency: 50
extraction_spec: spanish_clinic_extraction
```

**Command:**
```bash
python run_pipeline.py doppel_paginasamarillas
```

**Expected Output:**
- ~10,000-20,000 pages crawled
- ~3,000-5,000 unique companies extracted
- Cost: ~$280-560 (depending on pages)

---

### **Example 2: Test Run (Small Subset)**

```yaml
# configs/runs/doppel_test.yaml
client: doppel
crawl:
  target_url: "https://www.paginasamarillas.es/search/clinicas-madrid"
  limit: 1000
  max_concurrency: 30
extraction_spec: basic_company_extraction
test_mode: 10  # Only process first 10 pages
```

**Command:**
```bash
python run_pipeline.py doppel_test
```

**Expected Output:**
- 10 pages processed (test mode)
- ~5-10 companies extracted
- Cost: ~$0.30

---

### **Example 3: Re-run Failures**

```bash
# Re-run only failed items from previous run
python run_pipeline.py doppel_paginasamarillas \
  --rerun-failures \
  --from-run run_20251114_103000
```

---

## 🎯 Key Improvements Over Legacy crawl_system

1. **✅ Decoupled architecture** - Crawl ≠ Extraction (mix-and-match)
2. **✅ Object-oriented Python** - Clean separation of concerns vs bash scripts
3. **✅ Production-grade error handling** - Continue on failure, retry logic, re-run capability
4. **✅ Cost management** - Real-time tracking, budget enforcement, per-API/model breakdown
5. **✅ Comprehensive diagnostics** - Per-layer stats, failure tracking, exhaustive logging
6. **✅ Output transparency** - Reasoning + evidence columns for every extraction
7. **✅ Modern codebase** - Type-safe, modular, testable, maintainable
8. **✅ Developer experience** - Dry-run validation, real-time progress, one-command re-runs
9. **✅ Multi-tenant ready** - Client isolation, concurrent runs, historical preservation
10. **✅ Domain deduplication** - Avoid duplicate processing in final export

---

**Status**: 🚧 Design Complete - Awaiting Requirements & Implementation
**Confidence**: 95%
**Next Step**: Gather additional requirements before implementation
