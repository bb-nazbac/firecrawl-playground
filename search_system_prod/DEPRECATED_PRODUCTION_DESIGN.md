# Search System - Production Design v2.0

**Status**: 🚧 Design Phase
**Created**: 2025-11-09
**Updated**: 2025-11-09
**Confidence**: 97%

---

## 📐 Core Philosophy

**User Mental Model:**
> I want to search for **[QUERY]** in **[CITIES]**, then analyze results with **[ANALYSIS SPEC]**, for **[CLIENT]**

**Key Insight: Search and Analysis are Decoupled**
- Search query changes per run (flexible)
- Analysis spec is reusable (mix-and-match)
- Same search can use different analysis
- Same analysis can apply to different searches

**Configuration Approach:**
- **YAML run config**: What to search + which analysis to use
- **JSON analysis spec**: How to analyze (reusable across searches)
- **Complete CSV output**: All data + reasoning (user filters in Excel)

---

## 🎯 User Workflow

### **Step 1: Create Run Config**

```yaml
# /configs/runs/fuse_global_ranking.yaml

client: fuse

# What to search for
search:
  query: "neurology clinic in {city}"
  cities:
    - Boston, Massachusetts, United States
    - San Francisco, California, United States
    - Atlanta, Georgia, United States
  results_per_city: 3

# How to analyze results
analysis_spec: global_ranking_analysis
```

### **Step 2: Run Pipeline**

```bash
python3 run_pipeline.py --config configs/runs/fuse_global_ranking.yaml
```

### **Step 3: Get Complete CSV**

```csv
clinic_name,is_global_clinic,global_clinic_reasoning,estimated_global_rank,rank_reasoning,...
"Mayo Clinic",TRUE,"Internationally recognized, US News top ranked",Top 10,"Consistently ranked #1 in neurology",...
"Boston Neuro",FALSE,"Local practice, no global rankings found",Not globally ranked,"No evidence of international recognition",...
```

### **Step 4: Filter & Analyze in Excel**

Filter/sort by any column:
- Global clinics only: `is_global_clinic=TRUE`
- Top 10 ranked: `estimated_global_rank="Top 10"`
- Read reasoning for any classification

---

## 🔄 Mix-and-Match Examples

### **Same Search, Different Analysis:**

```yaml
# Run 1: Check global rankings
search:
  query: "neurology clinic in {city}"
  cities: [150 cities]
  results_per_city: 3
analysis_spec: global_ranking_analysis

# Run 2: Check hospital affiliations (same search!)
search:
  query: "neurology clinic in {city}"
  cities: [150 cities]
  results_per_city: 3
analysis_spec: hospital_affiliation_check
```

### **Different Search, Same Analysis:**

```yaml
# Run 1: Neurology clinics
search:
  query: "neurology clinic in {city}"
  cities: [50 cities]
  results_per_city: 100
analysis_spec: hospital_affiliation_check

# Run 2: Cardiology clinics (same analysis!)
search:
  query: "cardiology clinic in {city}"
  cities: [50 cities]
  results_per_city: 100
analysis_spec: hospital_affiliation_check
```

---

## 📁 Directory Structure

```
/search_system/

  # User edits these per run
  /configs/
    /runs/
      TEMPLATE.yaml                              ← Template to copy
      fuse_global_ranking.yaml                   ← Search + Analysis combo
      fuse_affiliation_check.yaml                ← Different combo
      fuse_telemedicine.yaml                     ← Another combo

    # Reusable analysis specs
    /specs/
      /analysis/
        TEMPLATE.json                            ← Template to copy
        global_ranking_analysis.json             ← Reusable analysis
        hospital_affiliation_check.json          ← Reusable analysis
        telemedicine_availability.json           ← Reusable analysis
        service_catalog.json                     ← Reusable analysis

  # Pipeline scripts
  /l1_serpapi_search/
    search_with_config.py                        ← Reads run config
  /l2_firecrawl_scrape/
    scrape_batch.py
  /l3_llm_classify/
    classify_with_spec.py                        ← Uses analysis spec
  /l4_csv_export/
    export_results.py
  /l5_domain_dedup/
    deduplicate.py

  # Client outputs (isolated per run)
  /outputs/
    /{client}/
      /run_{run_id}/
        # Final results
        final_results.csv

        # Progress tracking
        progress.json

        # Per-layer diagnostics
        diagnostics_l1_search.json
        diagnostics_l2_scrape.json
        diagnostics_l3_classify.json

        # Failure tracking (for re-runs)
        failures_l1_search.json
        failures_l2_scrape.json
        failures_l3_classify.json

        # Cost breakdown
        costs.json

        # Exhaustive logs
        run.log

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
client: fuse

#══════════════════════════════════════════════════════════════
# SEARCH CONFIGURATION (WHAT to search for)
#══════════════════════════════════════════════════════════════

search:
  # Search query (string)
  # Use {city} placeholder for city injection
  # Examples:
  #   "neurology clinic in {city}"
  #   "brain specialist in {city}"
  #   "stroke center in {city}"
  query: "neurology clinic in {city}"

  # Cities to search (array of strings)
  # Format: "City, State, Country" for precise geotargeting
  cities:
    - Boston, Massachusetts, United States
    - San Francisco, California, United States
    - Atlanta, Georgia, United States

  # Results per city (integer)
  # How many search results to fetch per city
  # Typical: 3 (top clinics) | 100 (comprehensive) | 200 (exhaustive)
  results_per_city: 100

#══════════════════════════════════════════════════════════════
# ANALYSIS CONFIGURATION (HOW to analyze results)
#══════════════════════════════════════════════════════════════

# Analysis spec name (string)
# References: /configs/specs/analysis/{analysis_spec}.json
# Examples:
#   global_ranking_analysis
#   hospital_affiliation_check
#   telemedicine_availability
analysis_spec: hospital_affiliation_check

#══════════════════════════════════════════════════════════════
# OPTIONAL OVERRIDES (Usually leave commented out)
#══════════════════════════════════════════════════════════════

# Test mode: Process only first N cities (integer or null)
# test_mode: 3

# Resume mode: Skip completed cities (boolean)
# resume: true

# Start from stage: Skip earlier stages (string)
# Options: search | scrape | classify | export | dedupe
# start_from: classify

# Max cost limit: Warn if exceeded (integer or null)
# max_cost_usd: 500

# Concurrency: Threads for scrape/classify (integer)
# concurrency: 30

# Dry run: Preview without executing (boolean)
# dry_run: true
```

---

## 📄 Analysis Spec Format (JSON)

### **Template:**

```json
// /configs/specs/analysis/TEMPLATE.json
{
  "spec_name": "hospital_affiliation_check",
  "description": "Identify hospital and university affiliations",

  // ────────────────────────────────────────────────────────────
  // CLASSIFICATION CATEGORIES
  // ────────────────────────────────────────────────────────────

  "categories": [
    {
      "id": "individual",
      "label": "Individual Clinic",
      "description": "Single practitioner or solo practice"
    },
    {
      "id": "group",
      "label": "Group Practice",
      "description": "Multiple practitioners, one or more locations"
    },
    {
      "id": "department",
      "label": "Hospital Department",
      "description": "Department or clinic within a hospital"
    },
    {
      "id": "directory",
      "label": "Directory/Aggregator",
      "description": "Listing site, not actual clinic"
    },
    {
      "id": "other",
      "label": "Other",
      "description": "Not a clinic"
    }
  ],

  // ────────────────────────────────────────────────────────────
  // EXTRACTION FIELDS
  // ────────────────────────────────────────────────────────────

  "extraction_fields": {
    "clinic_name": {
      "type": "string",
      "required": true,
      "description": "Official name of clinic or practice"
    },
    "phone": {
      "type": "string",
      "required": false,
      "description": "Primary contact phone number"
    },
    "website": {
      "type": "string",
      "required": false,
      "description": "Official website URL"
    },
    "address": {
      "type": "string",
      "required": false,
      "description": "Full street address"
    }
  },

  // ────────────────────────────────────────────────────────────
  // ANALYSIS QUESTIONS (Yes/No with reasoning)
  // ────────────────────────────────────────────────────────────

  "questions": [
    {
      "field": "hospital_affiliated",
      "question": "Is this a hospital or a department/clinic within a hospital?",
      "answer_type": "boolean",
      "reasoning_required": true,
      "reasoning_max_length": 200,
      "evidence_required": true
    },
    {
      "field": "university_affiliated",
      "question": "Is this affiliated with a university or medical school?",
      "answer_type": "boolean",
      "reasoning_required": true,
      "reasoning_max_length": 200,
      "evidence_required": true
    }
  ],

  // ────────────────────────────────────────────────────────────
  // LLM CONFIGURATION
  // ────────────────────────────────────────────────────────────

  "llm": {
    "model": "claude-sonnet-4-20250514",
    "max_tokens": 1500,
    "temperature": 0
  }
}
```

---

## 🔄 Data Flow

```
RUN CONFIG (user fills out)
  ├─ client: "fuse"
  ├─ search:
  │   ├─ query: "neurology clinic in {city}"
  │   ├─ cities: [Boston, SF, Atlanta]
  │   └─ results_per_city: 100
  └─ analysis_spec: "hospital_affiliation_check"
       ↓
SYSTEM LOADS ANALYSIS SPEC
  └─ /configs/specs/analysis/hospital_affiliation_check.json
       ↓
L1: SEARCH (Serper.dev)
  ├─ Query: "neurology clinic in Boston"
  └─ Output: 100 URLs per city
       ↓
L2: SCRAPE (Firecrawl)
  ├─ Check domain cache (skip if already scraped)
  ├─ Scrape 100 URLs per city (300 total)
  └─ Output: Markdown content per URL
       ↓
L3: CLASSIFY (Claude)
  ├─ Use analysis spec:
  │   - Categories
  │   - Extraction fields
  │   - Questions (hospital? university?)
  └─ Output: Structured JSON per page
       {
         "clinic_name": "Boston Neuro Associates",
         "phone": "617-555-0100",
         "hospital_affiliated": false,
         "hospital_reasoning": "Private practice, no hospital mention",
         "university_affiliated": false,
         "university_reasoning": "No university affiliation found"
       }
       ↓
L4: EXPORT (CSV)
  ├─ Combine all L3 results
  ├─ Include ALL results (no filtering)
  ├─ Include reasoning columns
  └─ Output: Complete CSV
       ↓
L5: DEDUPLICATE (Domain normalization)
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
  - clinic_name               (string)
  - clinic_type               (individual | group | department)
  - phone                     (string or null)
  - website                   (string or null)
  - address                   (string or null)
  - city                      (string)
  - state                     (string)

Analysis Results (depends on spec):
  - hospital_affiliated       (TRUE | FALSE)
  - hospital_reasoning        (text, max 200 chars)
  - hospital_evidence         (text)
  - university_affiliated     (TRUE | FALSE)
  - university_reasoning      (text, max 200 chars)
  - university_evidence       (text)
  - classification_confidence (high | medium | low)

Metadata:
  - source_url                (original URL)
  - classified_at             (ISO timestamp)
  - normalized_domain         (for deduplication)
  - tokens_input              (Claude usage)
  - tokens_output             (Claude usage)
```

---

## 🚀 Usage Examples

### **Example 1: Global Ranking Analysis**

```yaml
# configs/runs/fuse_global_ranking.yaml
client: fuse
search:
  query: "neurology clinic in {city}"
  cities:
    - Boston, Massachusetts, United States
    - New York, New York, United States
    # ... 148 more cities
  results_per_city: 3
analysis_spec: global_ranking_analysis
```

**Analysis spec defines:**
- Question: "Is this globally ranked?"
- Question: "What is estimated rank?"
- Extracts: name, website

---

### **Example 2: Hospital Affiliation Check**

```yaml
# configs/runs/fuse_affiliation_deep.yaml
client: fuse
search:
  query: "neurology clinic in {city}"
  cities:
    - Boston, Massachusetts, United States
    # ... 29 more cities
  results_per_city: 200
analysis_spec: hospital_affiliation_check
```

**Analysis spec defines:**
- Question: "Hospital affiliated?"
- Question: "University affiliated?"
- Extracts: name, phone, website, address

---

### **Example 3: Telemedicine Availability**

```yaml
# configs/runs/fuse_telemedicine.yaml
client: fuse
search:
  query: "neurology clinic in {city}"
  cities:
    - Boston, Massachusetts, United States
    # ... 49 more cities
  results_per_city: 100
analysis_spec: telemedicine_availability
```

**Analysis spec defines:**
- Question: "Offers telemedicine?"
- Question: "Accepts new patients remotely?"
- Extracts: name, phone, website, telemedicine_url

---

### **Example 4: Test Run (3 cities)**

```yaml
# configs/runs/fuse_test.yaml
client: fuse
search:
  query: "cardiology clinic in {city}"
  cities:
    - Boston, Massachusetts, United States
    - San Francisco, California, United States
    - Seattle, Washington, United States
  results_per_city: 50
analysis_spec: hospital_affiliation_check
test_mode: 3  # Only process first 3 cities
```

---

## 💰 Cost Model

### **Per City Breakdown:**

```
L1 Search:        $0.10     (100 results via Serper.dev)
L2 Scraping:      $2.50     (100 pages × $0.025 via Firecrawl)
L3 Classification: $4.50    (100 pages × $0.045 avg Claude Sonnet 4)
L4 Export:        $0        (local processing)
L5 Deduplication: $0        (local processing)
────────────────────────────
Total per city:   ~$7-9
```

### **Cost Varies by results_per_city:**

```
results_per_city: 3
  Cost per city: ~$0.50
  Use case: Top clinics only (global ranking)

results_per_city: 100
  Cost per city: ~$7-9
  Use case: Comprehensive coverage

results_per_city: 200
  Cost per city: ~$15-18
  Use case: Exhaustive search
```

### **L3 Cost Varies by Model:**

```
Claude Sonnet 4 (claude-sonnet-4-20250514):
  $3/1M input tokens, $15/1M output tokens
  Average per page: ~$0.045

Claude Opus 4 (claude-opus-4-20250514):
  $15/1M input tokens, $75/1M output tokens
  Average per page: ~$0.225 (5x more expensive)
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
  diagnostics_l1_search.json
  diagnostics_l2_scrape.json
  diagnostics_l3_classify.json

  # Re-run capability
  failures_l1_search.json
  failures_l2_scrape.json
  failures_l3_classify.json

  # Cost breakdown
  costs.json

  # Exhaustive logs
  run.log

  # Temporary cache (24hr)
  .cache_domains_24hr.json
```

---

### **📈 Progress Tracking (progress.json)**

**Real-time progress file updated throughout run:**

```json
{
  "run_id": "run_20251109_170000",
  "config_file": "configs/runs/fuse_neurology.yaml",
  "client": "fuse",
  "status": "running",
  "started_at": "2025-11-09T17:00:00Z",
  "updated_at": "2025-11-09T17:45:00Z",

  "cities": {
    "total": 50,
    "completed": 12,
    "remaining": 38,
    "current": "San Francisco, California, United States"
  },

  "layers": {
    "L1_search": {
      "status": "running",
      "cities_completed": 12,
      "urls_found": 1200,
      "failures": 0
    },
    "L2_scrape": {
      "status": "running",
      "pages_scraped": 1150,
      "failures": 50,
      "domains_cached": 1150
    },
    "L3_classify": {
      "status": "pending",
      "pages_classified": 0,
      "failures": 0
    }
  },

  "costs": {
    "total_usd": 88.50,
    "remaining_budget_usd": 411.50,
    "max_limit_usd": 500,
    "warnings": []
  },

  "elapsed_seconds": 2700,
  "estimated_completion": "2025-11-09T20:30:00Z"
}
```

---

### **🔬 Layer Diagnostics (diagnostics_l{N}.json)**

**Example: diagnostics_l1_search.json**

```json
{
  "layer": "L1_SEARCH",
  "run_id": "run_20251109_170000",
  "started_at": "2025-11-09T17:00:00Z",
  "completed_at": "2025-11-09T17:15:00Z",
  "duration_seconds": 900,

  "summary": {
    "cities_total": 50,
    "cities_completed": 48,
    "cities_failed": 2,

    "queries_total": 50,
    "queries_successful": 48,
    "queries_failed": 2,

    "urls_found": 4850,
    "urls_per_city_avg": 97,
    "urls_per_city_min": 0,
    "urls_per_city_max": 100,

    "retries_total": 15,
    "retries_successful": 13,
    "retries_exhausted": 2
  },

  "costs": {
    "api": "serper.dev",
    "total_usd": 5.00,
    "queries_billed": 50,
    "cost_per_query": 0.10
  },

  "failures": [
    {
      "city": "Rural Town, Wyoming, United States",
      "query": "neurology clinic in Rural Town, Wyoming, United States",
      "error_type": "timeout",
      "retries_attempted": 10,
      "last_error": "Request timeout after 10s",
      "timestamp": "2025-11-09T17:05:00Z",
      "can_retry": true
    },
    {
      "city": "Small City, Montana, United States",
      "query": "neurology clinic in Small City, Montana, United States",
      "error_type": "rate_limit",
      "retries_attempted": 10,
      "last_error": "429 Rate Limit Exceeded",
      "timestamp": "2025-11-09T17:10:00Z",
      "can_retry": true
    }
  ],

  "per_city_stats": [
    {
      "city": "Boston, Massachusetts, United States",
      "urls_found": 100,
      "duration_seconds": 12,
      "retries": 0,
      "cost_usd": 0.10,
      "status": "success"
    },
    {
      "city": "San Francisco, California, United States",
      "urls_found": 98,
      "duration_seconds": 15,
      "retries": 2,
      "cost_usd": 0.10,
      "status": "success"
    }
  ]
}
```

**Example: diagnostics_l2_scrape.json**

```json
{
  "layer": "L2_SCRAPE",
  "run_id": "run_20251109_170000",
  "started_at": "2025-11-09T17:15:00Z",
  "completed_at": "2025-11-09T19:00:00Z",
  "duration_seconds": 6300,

  "summary": {
    "urls_total": 4850,
    "urls_attempted": 4850,
    "urls_successful": 4700,
    "urls_failed": 150,
    "urls_skipped_domain_dedup": 200,

    "domains_unique": 4650,
    "domains_duplicate": 200,

    "retries_total": 500,
    "retries_successful": 450,
    "retries_exhausted": 50,

    "success_rate_percent": 96.9
  },

  "costs": {
    "api": "firecrawl",
    "total_usd": 117.50,
    "pages_billed": 4700,
    "cost_per_page": 0.025
  },

  "failure_breakdown": {
    "403_anti_scraping": 100,
    "timeout": 30,
    "500_server_error": 15,
    "connection_error": 5
  },

  "domain_dedup_stats": {
    "domains_seen": 4850,
    "domains_unique": 4650,
    "domains_skipped": 200,
    "top_duplicates": [
      {"domain": "mayoclinic.org", "count": 15, "first_city": "Boston"},
      {"domain": "clevelandclinic.org", "count": 12, "first_city": "NYC"},
      {"domain": "johnshopkins.edu", "count": 10, "first_city": "Baltimore"}
    ]
  },

  "failures": [
    {
      "url": "https://blocked-clinic.com/neurology",
      "domain": "blocked-clinic.com",
      "city": "Boston, Massachusetts, United States",
      "error_type": "403_anti_scraping",
      "error_message": "HTTP 403 Forbidden",
      "retries_attempted": 10,
      "last_attempt": "2025-11-09T17:45:00Z",
      "can_retry": false
    }
  ]
}
```

---

### **💰 Cost Tracking (costs.json)**

**Accurate cost breakdown per API and model:**

```json
{
  "run_id": "run_20251109_170000",
  "total_cost_usd": 367.50,
  "max_cost_limit_usd": 500,
  "remaining_budget_usd": 132.50,
  "warnings": [
    {
      "timestamp": "2025-11-09T18:30:00Z",
      "level": "warning",
      "message": "Cost exceeded 80% of limit: $410 / $500",
      "cost_at_warning": 410.00
    }
  ],

  "breakdown_by_layer": {
    "L1_search": {
      "api": "serper.dev",
      "cost_usd": 5.00,
      "queries": 50,
      "cost_per_query": 0.10
    },

    "L2_scrape": {
      "api": "firecrawl",
      "cost_usd": 117.50,
      "pages_scraped": 4700,
      "cost_per_page": 0.025
    },

    "L3_classify": {
      "api": "anthropic",
      "model": "claude-sonnet-4-20250514",
      "cost_usd": 245.00,
      "pages_classified": 4550,
      "tokens_input": 45000000,
      "tokens_output": 3000000,
      "pricing": {
        "cost_per_1m_input": 3.00,
        "cost_per_1m_output": 15.00
      },
      "breakdown": {
        "input_cost_usd": 135.00,
        "output_cost_usd": 110.00
      }
    }
  },

  "cost_by_city": [
    {
      "city": "Boston, Massachusetts, United States",
      "l1_cost": 0.10,
      "l2_cost": 2.50,
      "l3_cost": 4.75,
      "total": 7.35
    }
  ]
}
```

---

### **🔄 Retry Logic**

**L1 (Search): Up to 10 retries**
```python
L1_RETRY_CONFIG = {
  "max_attempts": 10,
  "backoff": "exponential",  # 2s, 4s, 8s, 16s, 32s, 64s, 128s...
  "retry_on": [
    "timeout",
    "429_rate_limit",
    "500_server_error",
    "503_service_unavailable",
    "connection_error"
  ],
  "skip_on": [
    "400_bad_request",
    "401_unauthorized",
    "403_forbidden"
  ]
}
```

**L2 (Scrape): Up to 10 retries**
```python
L2_RETRY_CONFIG = {
  "max_attempts": 10,
  "backoff": "exponential",  # 2s, 4s, 8s, 16s, 32s, 64s, 128s...
  "retry_on": [
    "timeout",
    "500_server_error",
    "502_bad_gateway",
    "503_service_unavailable",
    "connection_error",
    "dns_error"
  ],
  "skip_on": [
    "403_anti_scraping",  # Expected, don't retry
    "404_not_found",      # URL dead
    "401_unauthorized"
  ]
}
```

**L3 (Classify): Up to 3 retries**
```python
L3_RETRY_CONFIG = {
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
  "l1_search_per_query": 10,    # 10 seconds
  "l2_scrape_per_page": 30,     # 30 seconds
  "l3_classify_per_page": 60    # 60 seconds (varies by content)
}
```

---

### **❌ Error Handling & Failure Tracking**

**Failures per layer saved for re-runs:**

**Example: failures_l2_scrape.json**

```json
{
  "layer": "L2_SCRAPE",
  "run_id": "run_20251109_170000",
  "total_failures": 150,
  "can_retry_count": 50,
  "cannot_retry_count": 100,

  "failures": [
    {
      "city": "Boston, Massachusetts, United States",
      "url": "https://example-clinic.com/neurology",
      "domain": "example-clinic.com",
      "error_type": "timeout",
      "error_message": "Request timeout after 30s",
      "retries_attempted": 10,
      "last_attempt": "2025-11-09T17:45:00Z",
      "can_retry": true,
      "http_status": null
    },
    {
      "city": "NYC, New York, United States",
      "url": "https://blocked-site.com/doctors",
      "domain": "blocked-site.com",
      "error_type": "403_anti_scraping",
      "error_message": "HTTP 403 Forbidden",
      "retries_attempted": 10,
      "last_attempt": "2025-11-09T17:50:00Z",
      "can_retry": false,
      "http_status": 403
    }
  ]
}
```

---

### **🔁 Re-run Strategy**

**Command to re-run failures from previous run:**

```bash
python3 run_pipeline.py \
  --config configs/runs/fuse_neurology.yaml \
  --rerun-failures \
  --from-run run_20251109_170000
```

**Re-run Logic:**

```
Step 1: Load failure files from previous run
  - failures_l1_search.json
  - failures_l2_scrape.json
  - failures_l3_classify.json

Step 2: Re-run L1 failures (if any)
  - Only retry items with can_retry: true
  - Skip items that failed due to 403, 401, etc.
  - Update progress and diagnostics

Step 3: Re-run L2 failures (after L1 completes)
  - Load L1 results (both new and previous)
  - Retry L2 failures with can_retry: true
  - Check domain cache (skip if already scraped)

Step 4: Re-run L3 failures (after L2 completes)
  - Load L2 results (both new and previous)
  - Retry L3 failures with can_retry: true

Step 5: Generate new output
  - Combine previous successful results + new results
  - Export to new CSV
  - Update all diagnostics
```

**Re-run always starts from L1:**
- Check what completed successfully in previous run
- Skip completed items per layer
- Only process failures and new items

---

### **🗂️ Domain Deduplication Cache (24hr)**

**Purpose:** Don't scrape same domain twice in same run

**File: `.cache_domains_24hr.json`**

```json
{
  "created_at": "2025-11-09T17:00:00Z",
  "expires_at": "2025-11-10T17:00:00Z",

  "domains_seen": {
    "mayoclinic.org": {
      "first_seen_city": "Boston, Massachusetts, United States",
      "first_seen_url": "https://www.mayoclinic.org/neurology",
      "timestamp": "2025-11-09T17:05:00Z",
      "scraped": true,
      "scrape_success": true,
      "classified": true,
      "classify_success": true
    },
    "clevelandclinic.org": {
      "first_seen_city": "NYC, New York, United States",
      "first_seen_url": "https://my.clevelandclinic.org/departments/neurology",
      "timestamp": "2025-11-09T17:08:00Z",
      "scraped": true,
      "scrape_success": true,
      "classified": false,
      "classify_success": false
    }
  },

  "stats": {
    "domains_total": 4850,
    "domains_unique": 4650,
    "domains_duplicate": 200,
    "domains_skipped_l2": 200,
    "domains_skipped_l3": 200
  }
}
```

**Logic in L2:**
```python
# Before scraping URL
domain = extract_domain(url)
if domain in domain_cache and domain_cache[domain]['scraped']:
    log("Skipped: domain already scraped in this run")
    diagnostics.increment("urls_skipped_domain_dedup")
    return
```

**Benefits:**
- Reduces scraping costs (don't pay for duplicates)
- Reduces classification costs (don't classify duplicates)
- Faster pipeline execution
- Detailed dedup stats in diagnostics

---

### **📝 Exhaustive Logging (run.log)**

**Human-readable log with every decision:**

```
[2025-11-09 17:00:00] INFO: ═══════════════════════════════════════
[2025-11-09 17:00:00] INFO: PIPELINE START
[2025-11-09 17:00:00] INFO: ═══════════════════════════════════════
[2025-11-09 17:00:00] INFO: Run ID: run_20251109_170000
[2025-11-09 17:00:00] INFO: Config: configs/runs/fuse_neurology.yaml
[2025-11-09 17:00:00] INFO: Client: fuse
[2025-11-09 17:00:00] INFO: Cities: 50
[2025-11-09 17:00:00] INFO: Results per city: 100
[2025-11-09 17:00:00] INFO: Analysis spec: hospital_affiliation_check
[2025-11-09 17:00:00] INFO: Max cost limit: $500.00
[2025-11-09 17:00:00] INFO: Concurrency: 30 threads

[2025-11-09 17:00:01] INFO: ─────────────────────────────────────────
[2025-11-09 17:00:01] INFO: L1 SEARCH START
[2025-11-09 17:00:01] INFO: ─────────────────────────────────────────

[2025-11-09 17:00:01] INFO: [1/50] Boston, Massachusetts, United States
[2025-11-09 17:00:01] INFO: Query: "neurology clinic in Boston, Massachusetts, United States"
[2025-11-09 17:00:12] INFO: Search success: 100 results found
[2025-11-09 17:00:12] INFO: Cost: $0.10 | Total: $0.10 / $500.00 (0.02%)

[2025-11-09 17:00:13] INFO: [2/50] San Francisco, California, United States
[2025-11-09 17:00:13] INFO: Query: "neurology clinic in San Francisco, California, United States"
[2025-11-09 17:00:15] WARN: Search failed: timeout after 10s
[2025-11-09 17:00:15] INFO: Retry 1/10: Wait 2s (exponential backoff)
[2025-11-09 17:00:17] INFO: Retry 1 success: 98 results found
[2025-11-09 17:00:17] INFO: Cost: $0.10 | Total: $0.20 / $500.00 (0.04%)

[2025-11-09 17:00:18] INFO: [3/50] Atlanta, Georgia, United States
[2025-11-09 17:00:18] INFO: Query: "neurology clinic in Atlanta, Georgia, United States"
[2025-11-09 17:00:29] INFO: Search success: 100 results found
[2025-11-09 17:00:29] INFO: Cost: $0.10 | Total: $0.30 / $500.00 (0.06%)

...

[2025-11-09 17:15:00] INFO: ─────────────────────────────────────────
[2025-11-09 17:15:00] INFO: L1 SEARCH COMPLETE
[2025-11-09 17:15:00] INFO: ─────────────────────────────────────────
[2025-11-09 17:15:00] INFO: Duration: 15m 0s
[2025-11-09 17:15:00] INFO: Cities successful: 48/50
[2025-11-09 17:15:00] INFO: Cities failed: 2/50
[2025-11-09 17:15:00] INFO: URLs found: 4,850
[2025-11-09 17:15:00] INFO: Retries: 15 total, 13 successful, 2 exhausted
[2025-11-09 17:15:00] INFO: Cost: $5.00 | Total: $5.00 / $500.00 (1.0%)
[2025-11-09 17:15:00] WARN: Failures saved to: failures_l1_search.json

[2025-11-09 17:15:01] INFO: ─────────────────────────────────────────
[2025-11-09 17:15:01] INFO: L2 SCRAPE START
[2025-11-09 17:15:01] INFO: ─────────────────────────────────────────
[2025-11-09 17:15:01] INFO: URLs to scrape: 4,850
[2025-11-09 17:15:01] INFO: Concurrency: 50 threads
[2025-11-09 17:15:01] INFO: Checking domain cache...
[2025-11-09 17:15:02] INFO: Domain cache: 0 domains (new run)

[2025-11-09 17:15:05] INFO: [Thread-01] Scraping: https://mayoclinic.org/neurology
[2025-11-09 17:15:08] INFO: [Thread-01] Success: 15KB | mayoclinic.org → cache
[2025-11-09 17:15:08] INFO: Cost: $0.025 | Total: $5.03 / $500.00 (1.0%)

[2025-11-09 17:15:10] INFO: [Thread-12] Scraping: https://mayoclinic.org/neurology/boston
[2025-11-09 17:15:10] INFO: [Thread-12] SKIPPED: mayoclinic.org already in cache
[2025-11-09 17:15:10] INFO: Diagnostics: urls_skipped_domain_dedup += 1

[2025-11-09 17:18:30] WARN: [Thread-05] Failed: https://blocked.com/neuro | 403 Forbidden
[2025-11-09 17:18:30] INFO: [Thread-05] Retry 1/10: Wait 2s
[2025-11-09 17:18:32] WARN: [Thread-05] Retry 1 failed: 403 Forbidden
[2025-11-09 17:18:32] INFO: [Thread-05] Retry 2/10: Wait 4s
...
[2025-11-09 17:19:00] ERROR: [Thread-05] All retries exhausted (10/10)
[2025-11-09 17:19:00] INFO: [Thread-05] Added to failures_l2_scrape.json
[2025-11-09 17:19:00] INFO: [Thread-05] can_retry: false (403 anti-scraping)

...

[2025-11-09 19:00:00] INFO: ─────────────────────────────────────────
[2025-11-09 19:00:00] INFO: PIPELINE COMPLETE
[2025-11-09 19:00:00] INFO: ─────────────────────────────────────────
[2025-11-09 19:00:00] INFO: Duration: 2h 0m 0s
[2025-11-09 19:00:00] INFO: Total cost: $367.50 / $500.00 (73.5%)
[2025-11-09 19:00:00] INFO:
[2025-11-09 19:00:00] INFO: Results:
[2025-11-09 19:00:00] INFO:   - Final CSV: outputs/fuse/run_20251109_170000/final_results.csv
[2025-11-09 19:00:00] INFO:   - Clinics found: 4,550
[2025-11-09 19:00:00] INFO:   - After dedup: 4,350
[2025-11-09 19:00:00] INFO:
[2025-11-09 19:00:00] INFO: Diagnostics:
[2025-11-09 19:00:00] INFO:   - diagnostics_l1_search.json
[2025-11-09 19:00:00] INFO:   - diagnostics_l2_scrape.json
[2025-11-09 19:00:00] INFO:   - diagnostics_l3_classify.json
[2025-11-09 19:00:00] INFO:
[2025-11-09 19:00:00] WARN: Failures detected:
[2025-11-09 19:00:00] WARN:   - L1: 2 cities (see failures_l1_search.json)
[2025-11-09 19:00:00] WARN:   - L2: 150 pages (see failures_l2_scrape.json)
[2025-11-09 19:00:00] WARN:   - L3: 50 pages (see failures_l3_classify.json)
[2025-11-09 19:00:00] INFO:
[2025-11-09 19:00:00] INFO: To re-run failures:
[2025-11-09 19:00:00] INFO:   python3 run_pipeline.py \
[2025-11-09 19:00:00] INFO:     --config configs/runs/fuse_neurology.yaml \
[2025-11-09 19:00:00] INFO:     --rerun-failures \
[2025-11-09 19:00:00] INFO:     --from-run run_20251109_170000
```

---

### **🎯 Console Output (Real-time)**

```
╔══════════════════════════════════════════════════════════════╗
║  SEARCH SYSTEM - PRODUCTION PIPELINE                         ║
║  Run ID: run_20251109_170000                                 ║
╚══════════════════════════════════════════════════════════════╝

Config: configs/runs/fuse_neurology.yaml
Client: fuse
Cities: 50 | Results per city: 100
Analysis: hospital_affiliation_check
Max cost: $500.00

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
L1: SEARCH
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[1/50] Boston ━━━━━━━━━━━━━━━━━━━━ 100% | 100 URLs | $0.10
[2/50] San Francisco ━━━━━━━━━━━━ 100% | 98 URLs | $0.10 (1 retry)
[3/50] Atlanta ━━━━━━━━━━━━━━━━━━ 100% | 100 URLs | $0.10

...

✓ L1 Complete: 48/50 cities | 4,850 URLs | $5.00 | 15m 0s
⚠ Failures: 2 cities (see failures_l1_search.json)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
L2: SCRAPE (50 threads)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Progress: ━━━━━━━━━━━━━━━━░░░░░░ 70% | 3,395/4,850 pages
Success: 3,245 | Failed: 100 | Skipped (dedup): 50
Cost: $81.13 / $500.00 (16.2%)
ETA: 45m remaining

...

✓ L2 Complete: 4,700/4,850 pages | $117.50 | 1h 45m
⚠ Failures: 150 pages (see failures_l2_scrape.json)
ⓘ Domain dedup: 200 duplicate domains skipped

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
L3: CLASSIFY (30 threads)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Progress: ━━━━━━━━━━━━━━━━━━━━ 100% | 4,550/4,700 pages
Cost: $245.00 / $500.00 (49.0%)
Time: 35m

✓ L3 Complete: 4,550/4,700 pages | $245.00 | 35m
⚠ Failures: 50 pages (see failures_l3_classify.json)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
L4: EXPORT & L5: DEDUPLICATE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✓ Exported: 4,550 clinics → final_results.csv
✓ Deduplicated: 4,550 → 4,350 unique domains

╔══════════════════════════════════════════════════════════════╗
║  PIPELINE COMPLETE                                           ║
╚══════════════════════════════════════════════════════════════╝

Duration: 2h 0m 0s
Total cost: $367.50 / $500.00 (73.5%)

Results: outputs/fuse/run_20251109_170000/final_results.csv
Diagnostics: outputs/fuse/run_20251109_170000/diagnostics_*.json

⚠ Failures:
  L1: 2 cities | L2: 150 pages | L3: 50 pages

To re-run failures:
  python3 run_pipeline.py \
    --config configs/runs/fuse_neurology.yaml \
    --rerun-failures \
    --from-run run_20251109_170000
```

---

## ✅ Design Principles

### **1. Search & Analysis Decoupled**

```
Search (run config) ≠ Analysis (spec)
Mix and match freely
Reuse analysis across different searches
```

### **2. Complete Transparency**

```
CSV includes reasoning for every classification
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
Per-model pricing (Claude Sonnet vs Opus)
Real-time budget monitoring
Cost warnings at 80% threshold
```

### **5. Domain Deduplication**

```
Don't scrape same domain twice
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

### **L1 (Search)**
- [ ] Refactor to use run config `search` section
- [ ] Retry logic (up to 10 retries, exponential backoff)
- [ ] Per-city result saving
- [ ] Cost tracking (Serper.dev pricing)
- [ ] Diagnostics integration
- [ ] Failure tracking

### **L2 (Scrape)**
- [ ] Retry logic (up to 10 retries, exponential backoff)
- [ ] Skip logic (403, 404 don't retry)
- [ ] Domain deduplication cache integration
- [ ] Per-city result saving
- [ ] Cost tracking (Firecrawl pricing)
- [ ] Diagnostics integration
- [ ] Failure tracking

### **L3 (Classify)**
- [ ] Load analysis spec dynamically
- [ ] Retry logic (up to 3 retries, exponential backoff)
- [ ] JSON response cleaning (strip markdown)
- [ ] Per-city result saving
- [ ] Cost tracking (per-model pricing: Sonnet vs Opus)
- [ ] Diagnostics integration
- [ ] Failure tracking

### **L4 (Export)**
- [ ] Export ALL results (no filtering)
- [ ] Include reasoning columns
- [ ] Include evidence columns
- [ ] CSV generation

### **L5 (Dedupe)**
- [ ] Domain normalization
- [ ] Keep first occurrence per domain
- [ ] Dedup statistics

### **Re-run Capability**
- [ ] `--rerun-failures` flag implementation
- [ ] Load previous failures
- [ ] Skip completed items per layer
- [ ] Combine previous + new results

### **Documentation**
- [ ] Update README.md with new workflow
- [ ] Create 5-10 analysis spec examples
- [ ] Create 10+ run config examples
- [ ] Re-run failures guide

---

**Status**: 🚧 Design Complete - Ready for Implementation
**Confidence**: 97%
**Next Step**: Implement core infrastructure (config loaders, orchestrator, diagnostics)
