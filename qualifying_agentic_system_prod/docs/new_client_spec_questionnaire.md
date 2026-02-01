# New Client Spec Questionnaire

Use this questionnaire to gather all the information needed to create a qualification spec for a new client. The spec defines how the pipeline will scrape and classify company websites.

---

## 1. Client & Product Context

### 1.1 Client Information
- **Client name (internal)**: What should we call this client in our system?
  - Example: "poka_labs", "layerup", "acme_corp"
  - Used for: folder names, spec file naming, output organization

### 1.2 Product/Service Description
- **What does the client sell?** (2-3 sentences)
  - What is the core product or service?
  - What problem does it solve?
  - Example: "Poka Labs sells connected worker software for manufacturing facilities. Their platform digitizes SOPs, enables real-time collaboration, and tracks training compliance."

### 1.3 Ideal Customer Profile (ICP)
- **Who is the ideal customer?**
  - What type of company buys this product?
  - What industry are they in?
  - What size company (employees, revenue)?
  - Example: "Mid-to-large chemical manufacturers in the US with 200+ employees who handle hazardous materials and need compliance tracking."

---

## 2. Domain Input

### 2.1 Source Data
- **Where is the list of domains coming from?**
  - [ ] CSV file (provide path or sample)
  - [ ] Database export
  - [ ] Scraped/purchased list
  - [ ] Other: _______________

### 2.2 Volume
- **Approximately how many domains need to be processed?**
  - [ ] < 500 (small batch, good for testing)
  - [ ] 500 - 2,000 (medium batch)
  - [ ] 2,000 - 10,000 (large batch)
  - [ ] 10,000+ (enterprise scale)

### 2.3 Data Quality
- **How clean/filtered is the input data?**
  - [ ] Pre-filtered B2B companies (high quality)
  - [ ] Industry-specific list (medium quality)
  - [ ] Raw scraped websites (needs heavy filtering)
  - [ ] Unknown quality

### 2.4 Sample Domains
- **Provide 5-10 example domains from your list:**
  1. _______________
  2. _______________
  3. _______________
  4. _______________
  5. _______________

---

## 3. Early Disqualification (Waterfall Filter)

The waterfall filter quickly eliminates obvious non-fits BEFORE expensive LLM analysis. This saves cost and time.

### 3.1 Business Type Exclusions
- **What types of businesses should be immediately disqualified?** (check all that apply)
  - [ ] News/media sites
  - [ ] Job boards / recruiting sites
  - [ ] E-commerce marketplaces (Amazon, eBay sellers)
  - [ ] Government agencies (.gov)
  - [ ] Educational institutions (.edu)
  - [ ] Non-profit organizations
  - [ ] Personal blogs / portfolio sites
  - [ ] Parked domains / domain sellers
  - [ ] Other: _______________

### 3.2 Geographic Restrictions
- **Should we filter by geography?**
  - [ ] No geographic restrictions
  - [ ] US only
  - [ ] North America only
  - [ ] Specific countries: _______________
  - [ ] Exclude specific countries: _______________

### 3.3 Company Size Floor
- **Minimum company size to consider?**
  - [ ] No minimum
  - [ ] 10+ employees
  - [ ] 50+ employees
  - [ ] 100+ employees
  - [ ] 200+ employees
  - [ ] 500+ employees
  - [ ] Custom: _______________

### 3.4 Domain Blocklist
- **Any specific domains or patterns to always skip?**
  - Example: "linkedin.com", "facebook.com", "*.gov", "*.edu"
  - List domains: _______________

### 3.5 Keyword-Based Quick Disqualification
- **Any keywords in the homepage that should trigger immediate disqualification?**
  - Example: "coming soon", "under construction", "domain for sale"
  - List keywords: _______________

---

## 4. Classification Categories

### 4.1 Category Structure
- **How should qualified companies be categorized?** (choose one)

**Option A: Tiers (priority-based)**
```
TIER_1_PRIME      → Best fit, highest priority targets
TIER_2_STRONG     → Good fit, strong potential
TIER_3_POTENTIAL  → Possible fit, worth exploring
TIER_4_SMALL      → Fits criteria but smaller/lower priority
```

**Option B: Types (business model-based)**
```
MANUFACTURER      → Makes the products
DISTRIBUTOR       → Sells/distributes products
RETAILER          → Sells to end consumers
SERVICE_PROVIDER  → Provides related services
```

**Option C: Industry Segments**
```
SEGMENT_A         → First industry segment
SEGMENT_B         → Second industry segment
SEGMENT_C         → Third industry segment
```

**Option D: Custom Categories**
- Define your own categories below

### 4.2 Define Each Category
For each category you want, provide:

**Category 1:**
- Name: _______________
- Description: _______________
- What qualifies a company for this category? _______________

**Category 2:**
- Name: _______________
- Description: _______________
- What qualifies a company for this category? _______________

**Category 3:**
- Name: _______________
- Description: _______________
- What qualifies a company for this category? _______________

**Category 4:**
- Name: _______________
- Description: _______________
- What qualifies a company for this category? _______________

(Add more as needed)

### 4.3 Disqualification Reasons
- **What are the specific reasons a company would be disqualified after analysis?**
  - [ ] No relevant products/services
  - [ ] Wrong industry entirely
  - [ ] Too small (below size threshold)
  - [ ] Too large (above size threshold)
  - [ ] Wrong business model (e.g., B2C instead of B2B)
  - [ ] Geographic mismatch
  - [ ] Insufficient information on website
  - [ ] Other: _______________

### 4.4 Priority Order
- **If a company could fit multiple categories, which takes precedence?**
  - List in order of priority (first match wins):
    1. _______________
    2. _______________
    3. _______________
    4. _______________

---

## 5. Qualification Signals

### 5.1 Positive Signals (What Makes Them Qualified)

**Products/Services Indicators:**
- What products or services should they offer?
  - _______________
- What keywords indicate relevant products?
  - _______________

**Industry Indicators:**
- What industries should they serve?
  - _______________
- What industry keywords to look for?
  - _______________

**Business Model Indicators:**
- [ ] Must be B2B (sells to businesses)
- [ ] Must be manufacturer (makes products)
- [ ] Must be distributor
- [ ] Must have physical locations
- [ ] Must have e-commerce/online ordering
- [ ] Other: _______________

**Size/Scale Indicators:**
- What indicates appropriate company size?
  - [ ] Multiple locations
  - [ ] Employee count mentions
  - [ ] Revenue mentions
  - [ ] "Enterprise" or "Fortune 500" customers
  - [ ] International presence
  - [ ] Other: _______________

**Capability Indicators:**
- What specific capabilities should they have?
  - _______________

### 5.2 Negative Signals (Red Flags)

**Disqualifying Products/Services:**
- What products/services indicate they're NOT a fit?
  - _______________

**Disqualifying Business Models:**
- [ ] Pure B2C (consumer-only)
- [ ] Consulting-only (no products)
- [ ] Marketplace/platform (doesn't make/sell products)
- [ ] Other: _______________

**Disqualifying Industries:**
- What industries should be excluded?
  - _______________

**Other Red Flags:**
- _______________

---

## 6. Website Analysis Depth

### 6.1 Pages to Analyze
- **Which pages should the LLM look at?** (check all that apply)
  - [ ] Homepage (always included)
  - [ ] About Us / Company page
  - [ ] Products / Services page
  - [ ] Industries / Markets page
  - [ ] Contact / Locations page
  - [ ] Careers page (for size signals)
  - [ ] Investors / Press page
  - [ ] Other: _______________

### 6.2 Iteration Logic
- **When should the pipeline dig deeper (scrape more pages)?**
  - [ ] Always scrape homepage only (fastest, cheapest)
  - [ ] Scrape additional pages if homepage is unclear
  - [ ] Always scrape 2-3 pages for thorough analysis
  - [ ] Custom logic: _______________

### 6.3 Information Priority
- **What's most important to find?** (rank 1-5, 1 = most important)
  - [ ] ___ Products/services offered
  - [ ] ___ Industries served
  - [ ] ___ Company size
  - [ ] ___ Geographic presence
  - [ ] ___ Business model (B2B vs B2C)
  - [ ] ___ Other: _______________

---

## 7. Questions to Answer

For each domain, what specific questions should be answered? These become fields in your output.

### 7.1 Core Questions (Required)
List the must-have questions:

1. **Question:** _______________
   - **Answer format:** [ ] Free text [ ] Yes/No [ ] List [ ] Enum (specific options)
   - **Critical for classification?** [ ] Yes [ ] No

2. **Question:** _______________
   - **Answer format:** [ ] Free text [ ] Yes/No [ ] List [ ] Enum
   - **Critical for classification?** [ ] Yes [ ] No

3. **Question:** _______________
   - **Answer format:** [ ] Free text [ ] Yes/No [ ] List [ ] Enum
   - **Critical for classification?** [ ] Yes [ ] No

(Add more as needed)

### 7.2 Example Questions (for reference)
Common questions used in other specs:
- "What products or services does this company offer?"
- "What industries do they serve?"
- "Do they have manufacturing capabilities?"
- "What is their geographic footprint?"
- "Do they sell B2B or B2C?"
- "What is their approximate company size?"
- "Do they have an online catalog or product listings?"
- "What is their primary business model?"

---

## 8. Classification Rules

### 8.1 Rule Logic
Describe how answers should map to categories. Use IF-THEN logic:

**Rule 1 (highest priority):**
```
IF [condition] AND [condition] THEN → [CATEGORY]
```
Example: "IF has_manufacturing AND employee_count > 500 AND serves_chemical_industry THEN → TIER_1_PRIME"

**Rule 2:**
```
IF [condition] AND [condition] THEN → [CATEGORY]
```

**Rule 3:**
```
IF [condition] AND [condition] THEN → [CATEGORY]
```

**Rule 4:**
```
IF [condition] THEN → [CATEGORY]
```

**Default Rule (if no other rules match):**
```
ELSE → [CATEGORY or INSUFFICIENT_INFO]
```

### 8.2 Confidence Handling
- **What should happen with low-confidence results?**
  - [ ] Classify anyway with best guess
  - [ ] Mark as "NEEDS_REVIEW"
  - [ ] Mark as "INSUFFICIENT_INFO"
  - [ ] Other: _______________

---

## 9. Examples

### 9.1 Qualified Examples
Provide 2-3 example companies that SHOULD be qualified:

**Example 1:**
- Domain: _______________
- Why they qualify: _______________
- Expected category: _______________

**Example 2:**
- Domain: _______________
- Why they qualify: _______________
- Expected category: _______________

**Example 3:**
- Domain: _______________
- Why they qualify: _______________
- Expected category: _______________

### 9.2 Disqualified Examples
Provide 2-3 example companies that should NOT be qualified:

**Example 1:**
- Domain: _______________
- Why they're disqualified: _______________

**Example 2:**
- Domain: _______________
- Why they're disqualified: _______________

### 9.3 Edge Cases
Any tricky scenarios and how they should be handled:

**Edge Case 1:**
- Scenario: _______________
- How to handle: _______________

**Edge Case 2:**
- Scenario: _______________
- How to handle: _______________

---

## 10. Output Requirements

### 10.1 Required Output Fields
- **What fields do you need in the final CSV/JSON output?** (check all that apply)
  - [ ] domain
  - [ ] classification (the category)
  - [ ] confidence_score
  - [ ] company_name
  - [ ] headquarters_location
  - [ ] employee_count_estimate
  - [ ] industry
  - [ ] products_services (list)
  - [ ] business_model
  - [ ] reasoning (why this classification)
  - [ ] Other: _______________

### 10.2 Output Format
- **Preferred output format?**
  - [ ] CSV (spreadsheet-friendly)
  - [ ] JSON (programmatic access)
  - [ ] Both

---

## 11. Technical Preferences

### 11.1 Model Selection
- **Which LLM model to use?**
  - [ ] gpt-5-mini (faster, cheaper: ~$0.01/domain)
  - [ ] gpt-5 (more accurate, expensive: ~$0.10/domain)
  - [ ] Let the system decide based on complexity

### 11.2 Iteration Depth
- **How many pages should we scrape per domain?**
  - [ ] 1 (homepage only) - fastest, cheapest
  - [ ] 2-3 (homepage + key pages) - balanced
  - [ ] 4-5 (thorough analysis) - most accurate, expensive

### 11.3 Concurrency
- **How fast should we process?**
  - [ ] Conservative (25 concurrent) - safer for rate limits
  - [ ] Standard (50 concurrent) - balanced
  - [ ] Aggressive (100 concurrent) - fastest, may hit rate limits

### 11.4 Error Handling
- **What to do with failed domains?**
  - [ ] Retry once, then mark as failed
  - [ ] Retry up to 3 times
  - [ ] Skip and continue
  - [ ] Other: _______________

---

## 12. Budget & Timeline

### 12.1 Budget Estimate
Based on your inputs:
- **Estimated cost per domain:** $0.01 - $0.03 (depends on depth)
- **Total domains:** _______________
- **Estimated total cost:** _______________

### 12.2 Timeline
- **When do you need results?**
  - [ ] ASAP (rush)
  - [ ] Within 24 hours
  - [ ] Within 1 week
  - [ ] No rush

---

## Notes & Additional Context

Use this space for any additional information that might help build the spec:

_______________________________________________________________________________
_______________________________________________________________________________
_______________________________________________________________________________
_______________________________________________________________________________

---

## Submission Checklist

Before submitting, ensure you've provided:
- [ ] Client name and product description
- [ ] Input domain source and count
- [ ] At least 3 disqualification criteria
- [ ] At least 2 classification categories with definitions
- [ ] At least 3 qualification signals
- [ ] At least 2 questions to answer per domain
- [ ] At least 1 qualified example domain
- [ ] At least 1 disqualified example domain
- [ ] Preferred output fields

---

*Once completed, this questionnaire will be used to generate a JSON spec file for the qualification pipeline.*
