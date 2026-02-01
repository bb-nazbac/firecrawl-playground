# Round 01: Map and Homepage Qualification - Learnings

**Date**: 2025-12-14
**Status**: 🚧 In Progress
**Overall Confidence**: 92% (PRE-TEST)

═══════════════════════════════════════════════════════════════

## Non-Negotiable Statement

We have business requirements that demand 95% confidence in data
pipeline robustness. This round achieves confidence through:
1. Systematic validation of iterative qualification approach
2. Per-question confidence tracking for intelligent page selection
3. Cost-efficient scraping with early-stop optimization

═══════════════════════════════════════════════════════════════

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  QUALIFYING AGENTIC SYSTEM - ITERATIVE FLOW                 │
└─────────────────────────────────────────────────────────────┘

For each company domain:

┌─────────────────────────────────────────────────────────────┐
│  L1: MAP                                                    │
│  ─────────────────────────────────────────────────────────  │
│  Firecrawl /v2/map → Get all site URLs                      │
│  Cost: 1 credit | Output: site_map.json                     │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  L2: ITERATIVE QUALIFICATION                                │
│  ─────────────────────────────────────────────────────────  │
│                                                             │
│  ROUND 0: Homepage                                          │
│  ├─ Scrape homepage (1 credit)                              │
│  ├─ Claude: Answer questions + confidence per question      │
│  ├─ Output: answers, confidence{HIGH|MEDIUM|LOW|INSUFF}     │
│  └─ Decision: needs_more_pages? → Continue or Stop          │
│                                                             │
│  ROUND 1: First Expansion (if needed)                       │
│  ├─ Claude: Select 5 URLs from map (target LOW conf Qs)     │
│  ├─ Scrape 5 pages (5 credits)                              │
│  ├─ Claude: Re-evaluate LOW confidence questions only       │
│  │          Keep HIGH confidence answers locked             │
│  └─ Decision: needs_more_pages? → Continue or Stop          │
│                                                             │
│  ROUND 2: Final Expansion (if needed)                       │
│  ├─ Same as Round 1                                         │
│  └─ Force final classification regardless of confidence     │
│                                                             │
│  MAX: 1 map + 1 homepage + 10 additional = 12 credits       │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  L3: EXPORT                                                 │
│  ─────────────────────────────────────────────────────────  │
│  Output: JSON with classification + evidence + confidence   │
└─────────────────────────────────────────────────────────────┘
```

═══════════════════════════════════════════════════════════════

## Key Innovation: Per-Question Confidence Tracking

### Problem Solved
Traditional single-pass classification either:
- Scrapes too little (homepage only) → Low accuracy
- Scrapes too much (full crawl) → High cost, noise

### Solution
Track confidence per question. Only scrape more if needed, and target
pages specifically for LOW confidence questions.

### Output Schema
```json
{
  "answers": {
    "sells_products": "YES",
    "is_b2b": "YES",
    "has_inventory_or_manufacturing": "UNKNOWN",
    "product_type": "UNKNOWN",
    "primary_category": "NOT_APPLICABLE"
  },
  "confidence": {
    "sells_products": "HIGH",           // ✓ Locked - don't re-ask
    "is_b2b": "HIGH",                   // ✓ Locked - don't re-ask
    "has_inventory_or_manufacturing": "LOW",  // ← Need more info
    "product_type": "LOW",              // ← Need more info
    "primary_category": "INSUFFICIENT"  // ← Need more info
  },
  "needs_more_pages": true,
  "suggested_page_types": ["products", "about", "manufacturing"]
}
```

### Page Selection Strategy
When Claude needs more info, it:
1. Looks at which questions have LOW/INSUFFICIENT confidence
2. Maps those questions to page types:
   - sells_products, product_type → /products, /solutions, /catalog
   - is_b2b → /about, /industries, /customers
   - has_inventory_or_manufacturing → /facilities, /manufacturing
3. Selects 5 URLs from site map matching those page types
4. Avoids: already-scraped, login, legal, blog, docs pages

═══════════════════════════════════════════════════════════════

## Experiment 1: Single Domain Qualification

### 1. What We're Testing

**Endpoints/Collections**:
- Firecrawl `/v2/map` - Site mapping
- Firecrawl `/v2/scrape` - Page content extraction
- Anthropic Claude API - Classification

**Expected Learning Outcome**:
- Validate iterative flow works end-to-end
- Measure confidence improvement across iterations
- Baseline cost per domain

**Techniques Used**:
- Iterative prompting with state preservation
- Per-question confidence tracking
- Intelligent page selection from site map

**Hypothesis**:
- 30-50% of domains can be classified from homepage alone (HIGH confidence)
- 1-2 additional iterations will bring 80%+ to HIGH confidence
- Average cost: 3-6 credits per domain (not max 12)

### 2. Why We're Running This

**Current Project Status**:
- Spec v2.1 complete with confidence tracking
- Prompts designed for iterative refinement
- Orchestrator built, ready for testing

**Current Knowledge Gaps**:
- Real-world homepage sufficiency rate?
- How well does page selection work?
- Token usage per iteration?

**Why This Test Unblocks Progress**:
- Must validate approach before batch processing 100k domains
- Need to tune confidence thresholds
- Need to validate cost model

### 3. Results

**What We Discovered**:
- PENDING - Awaiting test execution with user domains

**Data Quality/Completeness**:
- PENDING

**Confidence Level**: PENDING
- PENDING

**Unexpected Findings**:
- PENDING

### 4. Conclusions & Next Steps

**How Results Clarify Constraints**:
- PENDING

**How Results Expand Possibilities**:
- PENDING

**Validated Assumptions**:
- PENDING

**Invalidated Assumptions**:
- PENDING

**Next Experiment Required**:
- PENDING

═══════════════════════════════════════════════════════════════

## File Structure

```
round_01_map_and_homepage_qualification/
├── README.md                           # Round overview
├── learnings.md                        # This file
│
├── inputs/
│   ├── INPUTS_MANIFEST.md              # Dependency documentation
│   └── test_domains.csv                # User-provided test domains
│
├── outputs/
│   ├── map_results/                    # L1 map outputs
│   └── qualification_results/          # L2 qualification outputs
│
├── logs/
│   ├── l1_map/
│   └── l2_iterative_qualify/
│
├── l1_map/
│   ├── map_domain.py                   # Map single/batch domains
│   └── README.md
│
└── l2_iterative_qualify/
    ├── orchestrator.py                 # Main qualification flow
    ├── prompts.py                      # All prompt templates
    └── README.md
```

═══════════════════════════════════════════════════════════════

## Cost Model

### Per-Domain Breakdown

| Scenario | Map | Homepage | Round 1 | Round 2 | Total Credits |
|----------|-----|----------|---------|---------|---------------|
| Best (homepage enough) | 1 | 1 | 0 | 0 | 2 |
| Average (1 iteration) | 1 | 1 | 5 | 0 | 7 |
| Worst (max iterations) | 1 | 1 | 5 | 5 | 12 |

### Claude Token Estimates

| Step | Input Tokens | Output Tokens | Cost (Sonnet) |
|------|--------------|---------------|---------------|
| Initial qualification | ~3,000 | ~500 | ~$0.01 |
| Page selection | ~2,000 | ~200 | ~$0.007 |
| Re-qualification | ~8,000 | ~500 | ~$0.03 |

### For 100,000 Domains

| Scenario | Credits | Firecrawl Cost | Claude Cost | Total |
|----------|---------|----------------|-------------|-------|
| Best case | 200k | ~$200 | ~$1,000 | ~$1,200 |
| Average | 700k | ~$700 | ~$3,000 | ~$3,700 |
| Worst case | 1.2M | ~$1,200 | ~$5,000 | ~$6,200 |

═══════════════════════════════════════════════════════════════

## Confidence Assessment

| Component | Confidence | Status | Notes |
|-----------|------------|--------|-------|
| Spec Design | 95% | ✅ | Per-question confidence + iteration logic |
| Prompt Engineering | 90% | ⚠️ | Needs validation with real data |
| Orchestrator Logic | 92% | ⚠️ | Built, needs testing |
| Cost Model | 85% | ⚠️ | Estimates, need actuals |

**Overall Round Confidence: 90%** ⚠️

**Confidence Boosters**:
- Proven /map endpoint from qualifying_agents_prod (95% reliability)
- Clear classification logic with evidence requirements
- Iterative approach limits wasted API calls

**Confidence Blockers**:
- No real test data yet
- Token usage estimates may be off
- Edge cases (SPAs, blocked sites) not tested

**Path to 95%+**:
- Run tests with 5-10 user-provided domains
- Validate confidence improvement across iterations
- Measure actual costs vs estimates

═══════════════════════════════════════════════════════════════
