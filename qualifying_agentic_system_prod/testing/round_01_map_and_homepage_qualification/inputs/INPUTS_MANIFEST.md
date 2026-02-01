# Round 01 - Input Dependencies

## Test Domains

**Source**: User-provided list of company domains
**Status**: AWAITING INPUT

### Expected Format

```json
[
  {
    "domain": "example-chemicals.com",
    "company_name": "Example Chemicals Inc"
  }
]
```

Or simple list:
```
example-chemicals.com
acme-wholesale.com
bigcorp-distributors.net
```

## Qualification Questions (To Be Defined)

The user will provide specific qualification questions such as:
- "Is this a chemical distributor?"
- "Is this a wholesale distributor?"
- "What products do they distribute?"
- etc.

## External Dependencies

### API Endpoints

**Firecrawl API**:
- Map endpoint: `POST https://api.firecrawl.dev/v2/map`
- Scrape endpoint: `POST https://api.firecrawl.dev/v2/scrape`
- Auth: Environment variable `FIRECRAWL_API_KEY`

**Anthropic API**:
- Messages endpoint: `POST https://api.anthropic.com/v1/messages`
- Auth: Environment variable `ANTHROPIC_API_KEY`

### Environment Variables Required

```bash
FIRECRAWL_API_KEY=fc-xxxxx
ANTHROPIC_API_KEY=sk-ant-xxxxx
```

## Validation

```bash
# Check Firecrawl API key
curl -s https://api.firecrawl.dev/v2/scrape \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}' | head -c 200

# Check Anthropic API key
curl -s https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{"model": "claude-3-5-haiku-20241022", "max_tokens": 10, "messages": [{"role": "user", "content": "Hi"}]}' | head -c 200
```
