# Configuration Files

This directory contains all configuration files for the search system.

---

## 📁 Directory Structure

```
/configs/
  /runs/
    TEMPLATE.yaml                      ← Template for run configs
    fuse_neurology_test.yaml           ← Example: test run
    fuse_neurology_nov2025.yaml        ← Example: production run

  /specs/
    /business_types/
      TEMPLATE.json                    ← Template for business type specs
      neurology_clinic.json            ← Working spec
      cardiology_clinic.json           ← (future)
      orthopedics_clinic.json          ← (future)
```

---

## 📄 Run Config (YAML)

**What it is:** Configuration for a specific pipeline run

**When to create:** Every time you want to run the pipeline

**Location:** `/configs/runs/{client}_{business_type}_{date}.yaml`

**Template:** `TEMPLATE.yaml`

**Example:**
```yaml
business_type: neurology clinic
cities:
  - Boston, Massachusetts, United States
  - San Francisco, California, United States
client: fuse
```

**Usage:**
```bash
python3 run_pipeline.py --config configs/runs/fuse_neurology_nov2025.yaml
```

---

## 📄 Business Type Spec (JSON)

**What it is:** Classification rules for a business type (e.g., neurology clinics)

**When to create:** Once per business type (rarely changes)

**Location:** `/configs/specs/business_types/{business_type}.json`

**Template:** `TEMPLATE.json`

**Defines:**
- Search query template
- Classification categories
- Extraction fields
- Classification questions
- LLM settings

**Example:**
```json
{
  "business_type": "neurology clinic",
  "search": {
    "query_template": "{business_type} in {city}",
    "results_per_city": 100
  },
  "categories": [...],
  "extraction_fields": {...},
  "questions": [...]
}
```

---

## 🚀 Quick Start

### 1. Create Run Config

```bash
# Copy template
cp configs/runs/TEMPLATE.yaml configs/runs/my_run.yaml

# Edit with your values:
# - business_type
# - cities
# - client
```

### 2. Create Business Type Spec (if new)

```bash
# Copy template
cp configs/specs/business_types/TEMPLATE.json \
   configs/specs/business_types/my_business_type.json

# Edit with classification rules
```

### 3. Run Pipeline

```bash
python3 run_pipeline.py --config configs/runs/my_run.yaml
```

---

## 📋 Examples

### Test Run (3 cities)
```yaml
# configs/runs/test.yaml
business_type: neurology clinic
cities:
  - Boston, Massachusetts, United States
  - NYC, New York, United States
  - SF, California, United States
client: fuse
test_mode: 3
```

### Production Run (50 cities)
```yaml
# configs/runs/production.yaml
business_type: neurology clinic
cities:
  - Boston, Massachusetts, United States
  # ... 47 more cities
client: fuse
```

### Resume After Crash
```yaml
# configs/runs/resume.yaml
business_type: neurology clinic
cities: [...]
client: fuse
resume: true
start_from: classify
```

---

## 🔗 References

- **Main Design Doc:** `../PRODUCTION_DESIGN.md`
- **Usage Guide:** `../README.md`
