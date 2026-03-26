# M&A Pipeline — CHANGELOG

## 2026-02-05 (v2)

### Changed
- **Pivoted from AI classification to TECH classification** (wide net)
  - AI identification is too ambiguous from name + SIC alone (29% false positive rate in 10K test)
  - Tech classification is a more reliable first filter; AI identification deferred to research phase
- Replaced `l1_classify_ai_deals/` with `l1_classify_tech_deals/`
- Switched model from `gpt-4o-mini` to `gpt-5-mini` (better quality)
- New prompt classifies as "technology company" (software, hardware, biotech, fintech, etc.)
- Output columns: `is_tech`, `tech_category`, `tech_confidence` (was `is_ai`, `ai_category`, `ai_confidence`)
- Output file: `tech_deals_only.csv` (was `ai_deals_only.csv`)

### Context
- 10K AI classification test found 14 deals (0.14%) but 29% were clear false positives
- "Is this tech?" is a much easier, more reliable question from name + SIC data
- AI/ML identification will happen in L2+ via the research pipeline with richer data
- gpt-5-mini cost: ~$0.50/10K, ~$20 for full 411K

## 2025-02-05 (v1)

### Added
- `l1_classify_ai_deals/classify_deals.py` — LLM-based AI/ML deal classifier (SUPERSEDED)
  - Batches 10 rows per gpt-4o-mini call
  - Async with configurable concurrency (default 15)
  - Checkpoint/resume support (JSONL)
  - `--test N` flag for limited test runs
  - `--merge-only` for re-merging without API calls
  - Outputs: `all_deals_classified.csv`, `ai_deals_only.csv`, `classify_stats.json`
- Directory structure per COMMANDMENTS.yml (inputs/, outputs/, logs/, l1_classify_ai_deals/)
- `inputs/INPUTS_MANIFEST.md` — documents full_data.csv dependency
- `learnings.md` — experimental findings template
- `README.md` — pipeline overview

### Context
- Source data: 411,768 M&A deals from SDC/Refinitiv (62 columns)
- No SIC/NAIC code identifies AI companies — LLM classification required
- Progressive filter analysis: industry + SIC + NAIC + name keywords catches 111K/411K
  but misses cross-industry AI companies (healthcare AI, autonomous vehicles, etc.)
- 10K test results: 14 AI deals found, 29% false positive rate, $0.19 cost
- Conclusion: AI classification from name+SIC too ambiguous — pivot to tech classification
