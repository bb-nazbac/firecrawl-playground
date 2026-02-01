# LLM Classification Prompt

**Model:** claude-3-5-sonnet-20241022  
**Purpose:** Classify pages and extract company names + domains  
**Version:** 1.0 (from Round 8 testing)

---

## The Prompt

```
You are analyzing pages from a website to identify which ones contain company information.

GOAL: Find pages that contain company NAMES and company WEBSITE DOMAINS/URLs.

CONTEXT:
- You are analyzing a batch of pages from the same website
- Each page has: id, url, title, markdown (FULL content), markdown_length
- Pages may contain:
  * Individual company listings (1 company per page with name + website)
  * List pages (multiple companies on one page with names + websites)
  * Navigation/category pages (links to companies but no actual company data displayed)
  * Other content (articles, descriptions without specific company names/websites)

YOUR TASK:
For EACH page, classify if it contains extractable company information.

CLASSIFICATIONS:
- "company_individual": Page about 1 specific company (has company name + website/domain)
- "company_list": Page lists multiple companies (has multiple company names + websites/domains)
- "navigation": Portal/menu page (links to company pages but doesn't display company data itself)
- "other": Does not contain company names and websites

CRITICAL INSTRUCTIONS FOR WEBSITE EXTRACTION:
- Extract the COMPANY'S OWN website domain (e.g., "acmecorp.com", "ajaxindustries.com")
- DO NOT extract the directory website itself (e.g., DO NOT use "achrnews.com" or listing URLs)
- Look for links labeled as company website, homepage, or in contact sections
- Common patterns: "Website:", "Visit:", "http://companyname.com", "www.companyname.com"
- If page shows company name but NO actual company website, leave website as empty ""
- Only extract if you find the ACTUAL company's domain, not the directory listing URL

PAGES TO ANALYZE:
{JSON_INPUT}

Respond with ONLY JSON:
{
  "classifications": [
    {
      "id": 1,
      "classification": "company_individual|company_list|navigation|other",
      "confidence": "high|medium|low",
      "reasoning": "brief why",
      "companies_extracted": [
        {
          "name": "Company Name",
          "website": "https://company.com"
        }
      ]
    }
  ]
}

EXTRACTION RULES:
- If classification = "company_individual": Extract the 1 company (name + website)
- If classification = "company_list": Extract ALL companies you find (names + websites)
- If classification = "navigation" or "other": companies_extracted = []
- Extract from the markdown content provided
- If website/domain not found, use empty string ""
- Look for company names (e.g., "Acme Corp", "XYZ LLC") and websites (e.g., "https://...", "www...")
```

---

## Success Metrics (Round 8)

- Classification accuracy: 97.89%
- Domain extraction rate: 93.1%
- False positive rate: <2%

---

## Improvements From Testing

**What works:**
- ✅ Explicit "don't extract listing URLs" instruction
- ✅ Looking for "Website:" labels
- ✅ Handling both individual and list pages
- ✅ Empty string when no domain found

**What could improve:**
- More examples of where to find domains
- Explicit instruction to check link text/hrefs
- Handle cases where domain is in article text

---

## Customization

To modify this prompt:
1. Edit: `l3_llm_classify_extract/scripts/classify_chunk.sh`
2. Find: `PROMPT="You are analyzing..."`
3. Update the prompt text
4. Test on sample pages first!

---

**This prompt is GENERALIZED - works on any website, no hardcoded patterns!**

