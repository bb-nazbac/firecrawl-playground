# L4: CSV Export - Independent Clinics Filter

**Layer**: L4 (Final Export)
**Dependencies**: L3 classified outputs only
**Purpose**: Filter and export independent neurology clinics (neither hospital nor university affiliated) to CSV format for client delivery

---

## Business Objective

Export actionable list of independent neurology clinics for direct outreach, filtering out hospital departments and university-affiliated practices.

---

## Input

**Source**: L3 classified outputs from `l3_llm_classify/outputs/`
- 6 JSON files containing 446 total classified clinics
- Each clinic has `is_hospital_or_dept` and `university_affiliated` fields

**Filter Criteria**:
```python
is_hospital_or_dept.answer == "no" AND
university_affiliated.answer == "no"
```

---

## Output

**File**: `outputs/independent_clinics_filtered.csv` (25.7 KB)

**Columns**:
1. `clinic_name` - Name of the clinic/practice
2. `clinic_type` - Individual or Group practice
3. `phone` - Contact phone number (may be empty)
4. `website` - Official website URL (may be empty)
5. `locations` - Comma-separated list of cities served
6. `source_url` - Original scraped URL for validation
7. `confidence` - Claude classification confidence (high/medium/low)

**Record Count**: 164 independent clinics
- 79 Individual practices (48.2%)
- 85 Group practices (51.8%)

---

## Script

**File**: `export_independent_clinics.py`

**Execution**:
```bash
cd l4_csv_export
python3 export_independent_clinics.py
```

**Features**:
- Thread-safe logging with unbuffered writes
- Automatic L3 file discovery (latest versions only)
- Detailed statistics and sample preview
- COMMANDMENTS #7 compliant (layer-specific outputs)

---

## Log Files

**Location**: `../logs/l4_csv_export/`

**Format**: `export_independent_clinics_{YYYY-MM-DD_HH-mm-ss}.log`

**Contents**:
- Input file discovery
- Filtering statistics
- Export confirmation
- Sample record preview
- Performance metrics

---

## Results Summary

**Filter Rate**: 36.8% of total clinics (164 out of 446)

**Breakdown by Affiliation**:
- Hospital/Dept ONLY: 91 clinics (20.4%) - EXCLUDED
- University ONLY: 24 clinics (5.4%) - EXCLUDED
- BOTH Hospital & University: 167 clinics (37.4%) - EXCLUDED
- INDEPENDENT (NEITHER): 164 clinics (36.8%) - ✅ EXPORTED

**Coverage by City**:
- New York area
- Los Angeles area
- Chicago area

---

## Quality Assurance

**Data Validation**:
- ✅ All 164 records have clinic_name
- ✅ All records have source_url for verification
- ✅ Classification confidence documented (all "high")
- ✅ Phone/website may be empty (field-level validation)

**COMMANDMENTS Compliance**:
- ✅ Layer-based architecture (L4 depends on L3 only)
- ✅ Logs vs Outputs separation (CSV in /outputs, logs in /logs/l4_csv_export/)
- ✅ Proper naming conventions
- ✅ Unbuffered logging with timestamps

---

## Next Steps

1. **Deduplication**: Some clinics may appear multiple times (same clinic from different URLs)
2. **Validation**: Spot-check sample clinics for accuracy
3. **Enrichment**: Add additional contact fields if needed (email, address)
4. **Delivery**: Export to client deliverables folder

---

**Created**: 2025-11-06
**Status**: ✅ Complete
**Confidence**: 95%
