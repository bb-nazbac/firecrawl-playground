# Site Stripper Chrome Extension - How It Works

## Overview
**Site Stripper** is an AI-powered Chrome extension that lets you chat with Claude 4 Sonnet to intelligently scrape websites. It automatically intercepts all network requests and gives Claude tools to analyze, extract, and export data.

## Core Architecture

### 1. **Request Interception** (Content Script)
**File:** `src/contents/monkey-patch.ts`

**What it does:**
- Runs at `document_start` (earliest possible moment)
- Monkey-patches `window.fetch` and `XMLHttpRequest` using JavaScript Proxies
- Captures EVERY network request automatically:
  - Full request: URL, method, headers, body
  - Full response: status, headers, body (JSON/text/binary)
  - Duration and timing
- Sends all data to background via relay for caching
- **Transparent**: Original requests work normally, interception is invisible

**Key Insight:** By injecting into the MAIN world, it catches requests made by the actual page JavaScript, not just extension requests.

### 2. **Background Service Worker**
**File:** `src/background/streaming-conversation-manager.ts`

**What it does:**
- Manages conversations with Claude via Anthropic's streaming API
- Provides Claude with powerful tools to interact with the page
- Handles session management (saves/restores conversations)
- Manages CSV exports and enrichment

### 3. **Claude Tools Available**

The extension gives Claude these capabilities:

#### **Request Analysis Tools:**
- `list_cached_requests` - See all intercepted API calls
- `search_requests` - Fuzzy search requests by URL/content
- `get_request_details` - Get full request/response details
- `expose_request_data` - Inject API responses into page as `window.__request_data`

#### **JavaScript Execution Tools:**
- `execute_javascript` - Run JS in page context to extract data
- `create_function` - Save reusable helper functions
- `list_functions` / `delete_function` - Manage saved functions

#### **Element Selection Tools:**
- `get_selected_elements` - User can visually pick elements
- Extension stores selected elements for analysis

#### **Data Export Tools:**
- `list_csv_exports` - See all extracted CSVs
- `enrich_csv_with_zenrows` - Scrape URLs from CSV to add emails, phones, etc.

### 4. **Side Panel UI**
**File:** `src/sidepanel/`

- Chat interface with Claude
- Real-time streaming responses
- Shows CSV exports inline
- Element picker toggle

## How a Typical Workflow Works

### Example: Scraping a Directory Site

1. **User opens side panel** and visits directory site
2. **Extension automatically intercepts** all API calls (e.g., `GET /api/companies?page=1`)
3. **User asks Claude:** "Extract all companies from this page"
4. **Claude uses tools:**
   ```
   1. list_cached_requests → Sees the API call that loaded companies
   2. get_request_details → Examines the JSON structure
   3. expose_request_data → Injects API response into page as window.__request_data
   4. execute_javascript → Runs code to transform data:
      ```js
      const companies = window.__request_data[0].body.results.map(c => ({
        name: c.company_name,
        domain: c.website,
        location: c.city
      }));
      window.__site_stripper.exportCsv('companies.csv', companies);
      ```
   ```
5. **Extension creates CSV export** automatically
6. **User downloads** from side panel

## Key Advantages Over Traditional Scraping

### 1. **Works with Dynamic Sites**
- Doesn't parse HTML - uses actual API calls the site makes
- No need to understand React/Vue rendering
- Gets clean JSON data directly

### 2. **No Re-fetching Needed**
- All requests already cached automatically
- Claude works with existing intercepted data
- Instant analysis, no rate limiting

### 3. **Pagination Made Easy**
- Claude can detect pagination patterns in API calls
- Can generate scripts to replay requests with different page numbers
- Or guide user to click through pages while caching all requests

### 4. **AI-Powered Extraction**
- Claude understands data structures intelligently
- Can handle inconsistent formats
- Suggests optimal extraction strategies

### 5. **Enrichment with Zenrows**
- After extracting a CSV with domains/URLs
- Claude can use `enrich_csv_with_zenrows` to:
  - Scrape each URL
  - Extract emails, phones using autoparse
  - Add columns to CSV automatically

## Technical Details

### Request Caching
```typescript
// Each request cached with this structure:
{
  request: {
    id: "fetch-123",
    timestamp: 1234567890,
    url: "https://api.example.com/data",
    method: "GET",
    headers: { ... },
    body: "...",
    request_type: "fetch" | "xhr"
  },
  response: {
    status: 200,
    statusText: "OK",
    headers: { "content-type": "application/json" },
    body: '{"results": [...]}',
    body_type: "json" | "text" | "blob"
  },
  duration: 234 // milliseconds
}
```

### JavaScript Execution
- Runs in MAIN world (page context, not isolated)
- Has access to `window.__site_stripper` global:
  - `.exportCsv(filename, data)` - Export to CSV
  - `.elements` - Array of user-selected DOM elements
  - `.functions` - Saved helper functions
- Auto-injects saved functions on every execution

### CSV Export
```typescript
window.__site_stripper.exportCsv('output.csv', [
  { name: 'Company 1', domain: 'example.com' },
  { name: 'Company 2', domain: 'test.com' }
]);
```
- Automatically saved to session
- Available for download in UI
- Can be enriched with Zenrows

## Permissions Required
```json
{
  "permissions": [
    "sidePanel",      // Chat UI
    "activeTab",      // Access current tab
    "scripting",      // Execute JS
    "storage"         // Save sessions
  ],
  "host_permissions": ["<all_urls>"]  // Intercept on any site
}
```

## Comparison to Firecrawl

| Feature | Site Stripper | Firecrawl |
|---------|---------------|-----------|
| **Approach** | Intercepts browser requests | Server-side crawling |
| **Speed** | Instant (uses cached requests) | Requires crawl/scrape |
| **Dynamic Content** | Perfect (real API calls) | Good (JS rendering) |
| **Scale** | Limited to pages you visit | Can crawl 20k pages |
| **Authentication** | Works if you're logged in | Requires cookies/headers |
| **Cost** | Only enrichment costs | Per-page crawl costs |
| **AI Guidance** | Interactive Claude chat | Needs external script |

## Best Use Cases

### ✅ **Perfect For:**
- Authenticated/logged-in sites (LinkedIn, internal tools)
- Sites with paginated APIs
- Sites with complex JS frameworks
- Iterative exploration ("show me X, now extract Y")
- Small to medium datasets (100s-1000s of records)
- Learning/understanding site structure

### ❌ **Not Ideal For:**
- Bulk crawling entire domains (use Firecrawl)
- Sites requiring many page visits (tedious clicking)
- When you need historical data (only sees requests you trigger)
- Scraping 10k+ pages (too manual)

## Example Commands to Try

```
"What API calls is this page making?"
"Show me the request that loads the company list"
"Extract all companies with their names and websites"
"Find requests containing 'email'"
"Export the data from the /api/users endpoint to CSV"
"Enrich this CSV with emails using zenrows (test 3 rows first)"
```

## Summary

**Site Stripper** turns your browser into an AI-powered scraping assistant by:
1. Automatically intercepting all network traffic
2. Giving Claude tools to analyze and extract data
3. Executing JavaScript to transform data
4. Exporting to CSV with enrichment options

It's like having a senior developer watching network requests and writing extraction scripts for you in real-time.
