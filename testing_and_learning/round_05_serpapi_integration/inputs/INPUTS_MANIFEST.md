# Round 05 - Input Dependencies

**Round**: 05 - SerpAPI Integration (Documentation)
**Layer**: L1 (Independent - no dependencies on prior rounds)
**Status**: Documentation only (no code dependencies)

═══════════════════════════════════════════════════════════════

## External Dependencies

### API Services Required

**1. SerpAPI Account**
- **Service**: https://serpapi.com/
- **Purpose**: Google Search API with pagination support
- **Authentication**: API key
- **Environment Variable**: `SERPAPI_API_KEY`
- **Pricing**: Free tier (100 searches) or Starter ($75/month for 5,000)
- **Setup**:
  ```bash
  # Sign up at https://serpapi.com/
  # Get API key from dashboard
  # Add to .env file:
  echo "SERPAPI_API_KEY=your_key_here" >> .env
  ```

**2. Firecrawl Account** (Existing)
- **Service**: https://firecrawl.dev/
- **Purpose**: Scrape URLs returned by SerpAPI
- **Authentication**: API key
- **Environment Variable**: `FIRECRAWL_API_KEY`
- **Pricing**: ~$0.0002 per page scraped
- **Status**: ✅ Already configured from previous rounds

**3. Anthropic Claude** (Existing)
- **Service**: https://anthropic.com/
- **Purpose**: LLM classification of scraped pages
- **Authentication**: API key
- **Environment Variable**: `ANTHROPIC_API_KEY`
- **Pricing**: ~$0.003 per page classified
- **Status**: ✅ Already configured from crawl_system

### Python Dependencies
```bash
# Install SerpAPI client
pip install serpapi
# OR
pip install google-search-results

# Existing dependencies (already installed)
# - requests (for Firecrawl API)
# - anthropic (for Claude API)
# - python-dotenv (for environment variables)
```

═══════════════════════════════════════════════════════════════

## Input Files

**No input files required for this round.**

This is an L1 (independent) layer that:
- Queries external APIs directly (SerpAPI)
- Does not depend on outputs from previous rounds
- Produces output that L2 (scrape) and L3 (classify) will consume

═══════════════════════════════════════════════════════════════

## Environment Variables Required

Create or update `.env` file in project root:

```bash
# New for Round 05
SERPAPI_API_KEY=your_serpapi_key_here

# Existing (from previous rounds)
FIRECRAWL_API_KEY=fc-xxxxxxxxxxxxxxxxxxxxxxxx
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxxxxxx
```

### Validation
```bash
# Check environment variables are set
source .env
echo "SerpAPI: ${SERPAPI_API_KEY:0:10}..."
echo "Firecrawl: ${FIRECRAWL_API_KEY:0:10}..."
echo "Anthropic: ${ANTHROPIC_API_KEY:0:10}..."
```

═══════════════════════════════════════════════════════════════

## Configuration Files

**No static configuration files required.**

All configuration is documented in:
- `API_REFERENCE.md` - SerpAPI parameter reference
- `MIGRATION_GUIDE.md` - Integration instructions
- `COST_MODEL.md` - Cost planning

═══════════════════════════════════════════════════════════════

## Knowledge Dependencies

### Prior Rounds Referenced
1. **Round 02**: API Parameter Diagnosis
   - Source: `../round_02_api_parameter_diagnosis/learnings.md`
   - Key Finding: Firecrawl /search limited to 100 results, NO pagination
   - Relevance: Justifies need for SerpAPI migration

2. **Round 03**: Maximum Limits Testing
   - Source: `../round_02_api_parameter_diagnosis/learnings.md` (combined)
   - Key Finding: Firecrawl API max `limit=100` (HTTP 400 if higher)
   - Relevance: Confirms hard limit, validates SerpAPI as solution

3. **Round 04**: Production Batch Script
   - Source: `../round_04_batch_implementation/l1_batch_script/discover_batch.py`
   - Key Pattern: Batch processing with structured file naming
   - Relevance: Template for Round 06 implementation

### External Research
- **User-provided SerpAPI research summary** (provided via chat)
- **SerpAPI official documentation**: https://serpapi.com/docs
- **SerpAPI pricing**: https://serpapi.com/pricing

═══════════════════════════════════════════════════════════════

## Validation Steps

### Before Round 06 Implementation

1. **Verify SerpAPI Account**
   ```bash
   curl "https://serpapi.com/search.json?q=test&api_key=$SERPAPI_API_KEY"
   # Should return: {"search_metadata": {"status": "Success"}, ...}
   ```

2. **Verify Firecrawl Account**
   ```bash
   curl -X POST https://api.firecrawl.dev/v2/scrape \
     -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"url": "https://www.google.com", "formats": ["markdown"]}'
   # Should return: {"success": true, "data": {...}}
   ```

3. **Verify Python Environment**
   ```bash
   python3 -c "from serpapi import GoogleSearch; print('✅ SerpAPI client installed')"
   python3 -c "import requests; print('✅ Requests installed')"
   python3 -c "from dotenv import load_dotenv; print('✅ Dotenv installed')"
   ```

4. **Read Documentation**
   - [ ] Read `README.md` (round overview)
   - [ ] Read `API_REFERENCE.md` (complete SerpAPI docs)
   - [ ] Read `MIGRATION_GUIDE.md` (implementation steps)
   - [ ] Read `COST_MODEL.md` (cost planning)
   - [ ] Read `learnings.md` (findings and recommendations)

═══════════════════════════════════════════════════════════════

## Next Round (06) Will Require

**Input from Round 05**:
- ✅ Complete API documentation (`API_REFERENCE.md`)
- ✅ Migration guide (`MIGRATION_GUIDE.md`)
- ✅ Cost model (`COST_MODEL.md`)
- ✅ Learnings and recommendations (`learnings.md`)

**Input from External Sources**:
- 🔑 SerpAPI API key (new - to be created)
- 🔑 Firecrawl API key (existing)
- 🔑 Anthropic API key (existing)
- 📋 Cities list (user to provide - 250 Spanish cities)

═══════════════════════════════════════════════════════════════

**Status**: All dependencies documented. Ready for Round 06 implementation.
