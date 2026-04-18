# Round 01: Map and Homepage Qualification

**Date**: 2025-12-14
**Status**: IN PROGRESS
**Confidence Target**: 95%

## Objective

Validate the foundational layers of the Qualifying Agentic System:
1. L1 Map Layer - Firecrawl `/v2/map` endpoint integration
2. L2 Initial Qualification - Homepage scrape + Claude analysis

## Hypothesis

We can reliably:
1. Map any company website to discover all available pages
2. Scrape the homepage and extract enough context for initial qualification
3. Use Claude to determine if qualification questions can be answered
4. If not, Claude can intelligently select which pages to scrape next

## Test Plan

### Phase 1: Map Endpoint Validation
- Test `/v2/map` on sample company domains
- Validate response structure and URL discovery
- Measure: speed, URL count, reliability

### Phase 2: Homepage Qualification
- Scrape homepage using `/v2/scrape`
- Feed markdown to Claude with qualification questions
- Measure: answer completeness, confidence levels

### Phase 3: Page Selection Logic
- When homepage insufficient, test Claude's page selection
- Validate selected pages are relevant to qualification questions

## Success Criteria

- [ ] Map endpoint returns valid URLs for 95%+ of domains
- [ ] Homepage scrape succeeds for 95%+ of domains
- [ ] Claude can assess "sufficient information" reliably
- [ ] Page selection targets relevant pages (about, products, services)

## Directory Structure

```
round_01_map_and_homepage_qualification/
├── inputs/
│   └── INPUTS_MANIFEST.md          # Test company domains
├── outputs/
│   ├── map_results/                # L1 map outputs
│   └── qualification_results/      # L2 qualification outputs
├── logs/
│   ├── l1_map/                     # Map layer logs
│   └── l2_iterative_qualify/       # Qualification logs
├── l1_map/
│   ├── map_domain.py               # Map single domain
│   └── README.md
├── l2_iterative_qualify/
│   ├── qualify_domain.py           # Qualify with iteration
│   └── README.md
├── learnings.md                    # Experimental findings
└── README.md                       # This file
```

## Dependencies

From earlier R&D rounds:
- Map endpoint integration patterns
- Language filtering logic
- Cost tracking
- Progress tracking
- Spec loader patterns
