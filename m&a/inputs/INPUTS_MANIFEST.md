# M&A Pipeline - Input Dependencies

## Dependency 1: full_data.csv

- **Source Path**: `../full_data.csv` (m&a/ root)
- **Original Source**: `full data download.xlsx` (SDC/Refinitiv export)
- **Size**: 768 MB (CSV), 159 MB (XLSX)
- **Records**: 411,768 M&A deals
- **Columns**: 62
- **Date Created**: 2025-02-04
- **Schema** (key columns used by L1):
  ```
  Target Full Name          - string, target company name
  Target Primary SIC        - string, e.g. "7372 Prepackaged Software"
  Target Mid Industry       - string, e.g. "Internet Software/Services"
  Target Macro Industry     - string, e.g. "High Technology"
  ```
- **Full column list**: Target Full Name, Acquiror Full Name, Target Macro Industry, Target Mid Industry, Target SIC, Target Primary SIC, Target NAIC 2022, Target Primary NAIC 2022, Acquiror SIC, Acquiror Primary SIC, Acquiror NAIC 2022, Acquiror Primary NAIC 2022, Acquiror Ultimate Parent SIC, Target Ultimate Parent SIC, Deal Value (USD Millions), Date Announced, Form of the Deal, SDC Deal No, + 44 more
- **Why Needed**: Source data for AI/ML deal classification. Contains all M&A transactions to be classified.
- **Used By**: `l1_classify_tech_deals/classify_deals.py`
- **Validation**:
  - Check file exists: `test -f ../full_data.csv`
  - Verify record count: Should be 411,768 rows (excl. header)

## External Dependencies

**API Endpoints**:
- OpenAI API: `https://api.openai.com/v1/chat/completions`
- Model: `gpt-4o-mini`
- Auth: Environment variable `OPENAI_API_KEY`

**Environment Variables Required**:
- `OPENAI_API_KEY` — OpenAI API key (in `.env` at repo root)
