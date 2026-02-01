# Production Scaling Plan - 250 Spanish Cities Discovery

**Date**: 2025-11-04
**Status**: 🚧 Planning Phase
**Target**: 250 cities × 50 results = 12,500 dental clinic pages
**Confidence**: 92.5% → Target 95%+

═══════════════════════════════════════════════════════════════

## Executive Summary

Scale tested discovery pipeline (L1 Search + L2 Classification) from 50 pages (Sevilla test) to 12,500 pages (250 Spanish cities) with production-grade reliability.

**Validated System**:
- ✅ L1: 50 pages in 13.7s (54 Firecrawl credits)
- ✅ L2: 50 pages in 247s (~$0.59 Claude)
- ✅ Total: ~4.5 minutes, ~$0.64 per 50 pages

**Production Scale**:
- 🎯 L1: 12,500 pages in ~57 minutes (~2,700 credits = $2.70)
- 🎯 L2: 12,500 pages in ~3.4 hours (~$29.50)
- 🎯 Total: ~4 hours, ~$32 for complete Spain discovery

═══════════════════════════════════════════════════════════════

## Critical Requirements (User Confirmed)

### 1. ✅ Strong Retry Logic (No Delays)
- **L1**: Already has 10-retry exponential backoff
- **L2**: Already has 5-retry exponential backoff
- **Action**: Increase L2 to 10 retries to match L1
- **No artificial delays** between city queries

### 2. ✅ Structured File Naming
```
Current:  l1_scraped_pages_20251104_150252.json
Problem:  No city identification in filename

Production:
/outputs
    l1_scraped_pages_001_madrid_20251104_153000.json
    l1_scraped_pages_002_barcelona_20251104_153105.json
    ...
    l1_scraped_pages_250_tarragona_20251104_170000.json

    l2_classified_pages_001_madrid_20251104_154500.json
    l2_classified_pages_002_barcelona_20251104_155800.json
    ...
    l2_classified_pages_250_tarragona_20251104_223000.json
```

**Format**: `l{n}_{type}_pages_{NNN}_{city_name}_{timestamp}.json`
- `NNN`: 3-digit zero-padded index (001-250)
- `city_name`: lowercase, no spaces (e.g., a_coruna, san_sebastian)
- `timestamp`: YYYYMMDD_HHMMSS

### 3. ✅ Progress Checkpointing (Via Logs)
- Write progress after each city completes
- Log format: `[CHECKPOINT] City 42/250 (Barcelona) completed - 50 pages scraped`
- Enables manual resume by reading logs to see last completed city
- No separate checkpoint file needed

### 4. ✅ Single Output Folder
- **ONE folder**: `/outputs`
- **City in filename**: Yes
- **Per-city subfolders**: NO
- Easy to list all outputs: `ls -1 outputs/l1*.json | sort`

### 5. ✅ Cost Tracking Per City (In Logs)
```
[COST] City 42/250 (Barcelona): 54 Firecrawl credits, 197K Claude tokens
[COST] Running Total: 2,268 Firecrawl credits, 8.27M Claude tokens ($24.81)
```

### 6. ✅ Background Execution
- Run in background with output redirect
- Can exit terminal, check logs manually
- No keyboard interrupt handling needed
- Use `nohup` or `&` for background execution

### 7. ✅ Phased Rollout
```
Phase 1: 10 cities (pilot test)
Phase 2: 50 cities (quarter batch)  [OPTIONAL]
Phase 3: 250 cities (full production)
```

═══════════════════════════════════════════════════════════════

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  PRODUCTION DISCOVERY PIPELINE                              │
└─────────────────────────────────────────────────────────────┘
             │
             ├─→ L1: Batch Discovery (discover_batch.py)
             │   ├─ Input: cities.json (250 cities list)
             │   ├─ For each city:
             │   │   ├─ Search "clínica dental {city}" (50 results)
             │   │   ├─ Retry up to 10 times with exponential backoff
             │   │   ├─ Save: l1_scraped_pages_{NNN}_{city}_{ts}.json
             │   │   └─ Log: [CHECKPOINT] + [COST] + progress
             │   └─ Output: 250 JSON files in /outputs
             │
             └─→ L2: Batch Classification (classify_batch.py)
                 ├─ Input: All l1_scraped_pages_*.json in /outputs
                 ├─ For each city file:
                 │   ├─ Classify each page (dental/directory/other)
                 │   ├─ Retry up to 10 times with exponential backoff
                 │   ├─ Save: l2_classified_pages_{NNN}_{city}_{ts}.json
                 │   └─ Log: [CHECKPOINT] + [COST] + progress
                 └─ Output: 250 classified JSON files in /outputs
```

═══════════════════════════════════════════════════════════════

## Implementation Plan

### Phase 0: Preparation (30 minutes)

#### Task 0.1: Create Cities List
```bash
# File: /search_system/cities_spain_250.json
{
  "cities": [
    {"id": 1, "name": "Madrid", "slug": "madrid"},
    {"id": 2, "name": "Barcelona", "slug": "barcelona"},
    ...
    {"id": 250, "name": "City Name", "slug": "city_slug"}
  ]
}
```

#### Task 0.2: Update L2 Retry Logic
```python
# File: /l2_llm_scoring/classify.py
# Line 229: Change max_retries from 5 to 10
retry_api_call(make_request, max_retries=10, initial_delay=2)
```

#### Task 0.3: Create Batch Scripts

**L1 Batch Script**: `/l1_search_and_scrape/discover_batch.py`
- Read cities list
- For each city: call discover.py logic
- Save output with structured naming: `l1_scraped_pages_{id:03d}_{slug}_{ts}.json`
- Log checkpoint after each city
- Log cost per city

**L2 Batch Script**: `/l2_llm_scoring/classify_batch.py`
- Find all `l1_scraped_pages_*.json` files
- For each file: call classify.py logic
- Save output with structured naming: `l2_classified_pages_{id:03d}_{slug}_{ts}.json`
- Log checkpoint after each city
- Log cost per city

#### Task 0.4: Create Run Scripts

**L1 Run Script**: `/search_system/run_l1_batch.sh`
```bash
#!/bin/bash
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="logs/l1_batch_$TIMESTAMP.log"
mkdir -p logs

echo "Starting L1 batch discovery at $(date)" | tee -a $LOG_FILE

cd l1_search_and_scrape
nohup /usr/bin/python3 discover_batch.py cities_spain_250.json >> ../$LOG_FILE 2>&1 &

BATCH_PID=$!
echo "L1 batch running in background (PID: $BATCH_PID)" | tee -a $LOG_FILE
echo "Monitor progress: tail -f $LOG_FILE"
echo "Check status: ps -p $BATCH_PID"
```

**L2 Run Script**: `/search_system/run_l2_batch.sh`
```bash
#!/bin/bash
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="logs/l2_batch_$TIMESTAMP.log"
mkdir -p logs

echo "Starting L2 batch classification at $(date)" | tee -a $LOG_FILE

cd l2_llm_scoring
nohup /usr/bin/python3 classify_batch.py ../outputs >> ../$LOG_FILE 2>&1 &

BATCH_PID=$!
echo "L2 batch running in background (PID: $BATCH_PID)" | tee -a $LOG_FILE
echo "Monitor progress: tail -f $LOG_FILE"
echo "Check status: ps -p $BATCH_PID"
```

---

### Phase 1: Pilot Test (10 Cities) - 45 minutes

**Goal**: Validate all safeguards work at small scale

#### Task 1.1: Create 10-City Test List
```json
{
  "cities": [
    {"id": 1, "name": "Madrid", "slug": "madrid"},
    {"id": 2, "name": "Barcelona", "slug": "barcelona"},
    {"id": 3, "name": "Valencia", "slug": "valencia"},
    {"id": 4, "name": "Sevilla", "slug": "sevilla"},
    {"id": 5, "name": "Zaragoza", "slug": "zaragoza"},
    {"id": 6, "name": "Málaga", "slug": "malaga"},
    {"id": 7, "name": "Murcia", "slug": "murcia"},
    {"id": 8, "name": "Palma", "slug": "palma"},
    {"id": 9, "name": "Bilbao", "slug": "bilbao"},
    {"id": 10, "name": "Alicante", "slug": "alicante"}
  ]
}
```

#### Task 1.2: Run L1 Pilot (10 cities × 50 pages = 500 pages)
```bash
./run_l1_batch.sh cities_spain_10.json
# Expected: ~3 minutes, ~540 Firecrawl credits
```

**Validation Checklist**:
- [ ] 10 output files created with correct naming
- [ ] All files in `/outputs` (not subfolders)
- [ ] Checkpoints logged after each city
- [ ] Cost tracked per city in logs
- [ ] Process runs in background
- [ ] Can tail logs while running

#### Task 1.3: Run L2 Pilot (500 pages)
```bash
./run_l2_batch.sh
# Expected: ~40 minutes, ~$5.90 Claude
```

**Validation Checklist**:
- [ ] 10 classified output files created
- [ ] All cities classified successfully
- [ ] Checkpoints logged
- [ ] Cost tracked in logs
- [ ] Background execution works

#### Task 1.4: Validate Results
```bash
# Check output count
ls -1 outputs/l1_scraped_pages_*.json | wc -l
# Expected: 10

ls -1 outputs/l2_classified_pages_*.json | wc -l
# Expected: 10

# Check classification breakdown
jq -s 'map(.metadata.classification_counts) | add' outputs/l2_classified_pages_*.json
```

---

### Phase 2: Full Production (250 Cities) - 4 hours

**Prerequisites**:
- ✅ Phase 1 pilot successful
- ✅ All validation checks passed
- ✅ Budget approved (~$32)

#### Task 2.1: Create Full Cities List (250 cities)
```bash
# cities_spain_250.json with all 250 cities
# User to provide complete list
```

#### Task 2.2: Run L1 Production
```bash
./run_l1_batch.sh cities_spain_250.json
# Expected: ~57 minutes, ~2,700 Firecrawl credits ($2.70)

# Monitor progress
tail -f logs/l1_batch_TIMESTAMP.log

# Check progress at any time
grep CHECKPOINT logs/l1_batch_TIMESTAMP.log | tail -5
```

#### Task 2.3: Run L2 Production
```bash
./run_l2_batch.sh
# Expected: ~3.4 hours, ~9.85M Claude tokens ($29.50)

# Monitor progress
tail -f logs/l2_batch_TIMESTAMP.log

# Check progress at any time
grep CHECKPOINT logs/l2_batch_TIMESTAMP.log | tail -5
```

#### Task 2.4: Final Aggregation (Optional)
```bash
# Combine all L2 results into master file
jq -s '{metadata: {total_cities: length, total_pages: (map(.pages | length) | add)}, pages: (map(.pages) | flatten)}' outputs/l2_classified_pages_*.json > outputs/l2_all_cities_master.json
```

---

### Phase 3: Analysis & Export

#### Task 3.1: Generate Statistics
```bash
# Classification breakdown
jq -s 'map(.metadata.classification_counts) | {
  total_directories: map(.directory // 0) | add,
  total_individual: map(.dental_clinic_individual // 0) | add,
  total_groups: map(.dental_clinic_group // 0) | add,
  total_other: map(.other // 0) | add
}' outputs/l2_classified_pages_*.json

# Expected:
# - Directories: ~500 (2%)
# - Individual clinics: ~10,000 (80%)
# - Groups: ~2,000 (16%)
# - Other: ~250 (2%)
```

#### Task 3.2: Export to CSV
```bash
# Extract all valid clinics to CSV
jq -r '.pages[] | select(.classification == "dental_clinic_individual" or .classification == "dental_clinic_group") | [.extracted_data.clinic_name, .classification, .url, .extracted_data.phone, (.extracted_data.locations | join(", "))] | @csv' outputs/l2_classified_pages_*.json > spain_dental_clinics_all.csv
```

═══════════════════════════════════════════════════════════════

## Error Handling & Recovery

### Scenario 1: L1 Fails Mid-Run (City 147/250)

**Detection**:
```bash
grep CHECKPOINT logs/l1_batch_TIMESTAMP.log | tail -1
# Output: [CHECKPOINT] City 147/250 (Girona) completed
```

**Recovery**:
1. Edit cities list to start from city 148
2. Re-run L1 batch with remaining cities
3. All outputs preserved in `/outputs`

### Scenario 2: L2 Fails Mid-Run (City 89/250)

**Detection**:
```bash
grep CHECKPOINT logs/l2_batch_TIMESTAMP.log | tail -1
# Output: [CHECKPOINT] City 89/250 (Salamanca) completed
```

**Recovery**:
1. Check which L2 files already exist: `ls outputs/l2_classified_pages_*.json`
2. Modify L2 batch script to skip already-classified cities
3. Re-run L2 batch for remaining cities

### Scenario 3: API Rate Limit Hit

**Symptom**: Log shows repeated 429 errors despite retries

**Recovery**:
- Retry logic handles automatically (10 attempts with exponential backoff)
- If still failing after 10 attempts, city is skipped
- Re-run failed city manually after cooldown period

═══════════════════════════════════════════════════════════════

## Cost Tracking & Budget Management

### Real-Time Monitoring
```bash
# Check Firecrawl credits used
grep "COST" logs/l1_batch_TIMESTAMP.log | tail -1

# Check Claude tokens used
grep "COST" logs/l2_batch_TIMESTAMP.log | tail -1
```

### Budget Thresholds
- **L1 Budget**: 3,000 credits ($3.00 max)
- **L2 Budget**: $35.00 max
- **Alert if exceeding**: Manual check at 50%, 75%, 90%

═══════════════════════════════════════════════════════════════

## Success Criteria

### Quantitative Metrics
- [ ] All 250 cities processed successfully
- [ ] <5% page-level failure rate (625/12,500 pages)
- [ ] <10% cost overrun ($32 → $35 max)
- [ ] Complete within 5 hours total runtime

### Qualitative Metrics
- [ ] Output files well-organized and easily findable
- [ ] Logs provide clear progress visibility
- [ ] Recovery from failures is straightforward
- [ ] Results are analysis-ready (CSV export works)

═══════════════════════════════════════════════════════════════

## Risk Register (Updated)

| Risk | Likelihood | Impact | Mitigation | Status |
|------|------------|--------|------------|--------|
| API Rate Limit | Medium | High | 10-retry exponential backoff | ✅ Implemented |
| File Ordering Issues | Low | Low | Structured naming (001-250) | 📋 Planned |
| Mid-Run Interruption | Medium | Medium | Checkpoint logging + manual resume | 📋 Planned |
| Cost Overrun | Low | Medium | Per-city cost tracking in logs | 📋 Planned |
| Output File Corruption | Low | High | Atomic writes, JSON validation | ✅ Already safe |

═══════════════════════════════════════════════════════════════

## Confidence Assessment (Updated)

| Component | Before | After Plan | Status | Notes |
|-----------|--------|------------|--------|-------|
| Requirements Clarity | 92% | 98% | ✅ | User confirmed all 7 requirements |
| Data Source Understanding | 95% | 95% | ✅ | No change needed |
| Edge Case Coverage | 85% | 92% | 📋 | Pilot test will validate |
| Business Outcome Alignment | 98% | 98% | ✅ | No change needed |

**OVERALL MISSION CONFIDENCE**: **95.75%** [✅ GO]

**Path to 95%+ ACHIEVED via**:
- ✅ User clarifications answered (+6%)
- 📋 Implementation of 7 safeguards (ongoing)
- 📋 Pilot test with 10 cities (pending)

═══════════════════════════════════════════════════════════════

## Next Actions

### Immediate (Next 30 Minutes)
1. Create `cities_spain_10.json` for pilot test
2. Implement `discover_batch.py` with structured naming
3. Implement `classify_batch.py` with structured naming
4. Update L2 retry logic (5 → 10 retries)

### Short-Term (Next 2 Hours)
5. Run 10-city pilot test
6. Validate all safeguards working
7. Document any adjustments needed

### Ready for Production (After Pilot Success)
8. Get full 250-city list from user
9. Run L1 production batch
10. Run L2 production batch
11. Export results to CSV

═══════════════════════════════════════════════════════════════

**Lead Scientist**: OPTIMUS PRIME Unit OP-CLAUDE-20251104-DELTA
**Status**: Plan Documented - Ready for Implementation
**Confidence**: 95.75% [✅ GO]

═══════════════════════════════════════════════════════════════
