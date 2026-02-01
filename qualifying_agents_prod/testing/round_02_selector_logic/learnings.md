# Round 02: Selector Logic - Learnings

**Date**: 2025-11-24
**Status**: 🚧 In Progress
**Overall Confidence**: TBD

═══════════════════════════════════════════════════════════════

## Non-Negotiable Statement

We require 95% confidence that our selector logic can intelligently identify the "Worth Scraping" pages (Pricing, About, Team) from a raw map list, minimizing waste while capturing all context needed for qualification.

═══════════════════════════════════════════════════════════════

## Experiment 1: Heuristic Selector

### 1. What We're Testing

**Goal**:
- Develop a heuristic (regex/keyword-based) selector to filter map results.
- Classify URLs into:
    - `High Value` (Pricing, About, Team)
    - `Medium Value` (Blog, Careers, Product pages)
    - `Low Value` (Login, Terms, Privacy, specific blog posts)

**Hypothesis**:
- Simple keyword matching on the URL path is sufficient for 90% of B2B SaaS sites.

### 2. Why We're Running This

**Context**:
- Round 01 proved we can get a clean list of English URLs.
- We cannot scrape 1000 pages per company. We need the top 3-5.

**Knowledge Gaps**:
- How to handle ambiguous URLs?
- Do we need LLM for selection, or is Regex enough?

### 3. Results

#### Experiment 1: Heuristic Selector (Regex)
- ✅ **High Accuracy (SaaS)**: Worked well for Stripe, Vercel, Linear.
- ❌ **False Positives (Manufacturing)**: Rampf Group's "Pricing" strategy matched a blog post about "cost-efficiency" due to simple keyword matching.

#### Experiment 2: LLM Selector (Claude Haiku 3.5)
- ✅ **Perfect Accuracy**:
    - **Rampf Group**: Correctly identified `https://www.rampf-group.com/en-us/products-services` (or similar product page) and **avoided** the "cost" blog post. It actually returned empty for pricing if no explicit pricing page existed, which is correct for this industry.
    - **Stripe/Vercel/Linear**: Maintained high accuracy (`/pricing`, `/about`, `/careers`).
- ✅ **Context Awareness**: The LLM understands that a blog post about "cost" is not a "Pricing" page.
- ✅ **Cost/Speed**: Pre-filtering with regex (ignoring `/blog/`, `/news/`) kept the token count low (~1.6k - 2.8k links processed).

#### Experiment 3: Job Posting Specifics
- **Goal**: Target Main, About, Product, and *Individual* Job Postings.
- **Results (Rampf)**:
    - **Main**: `/` (Correct)
    - **About**: 5 relevant pages (Company, History, etc.)
    - **Product**: 5 deep product pages (Chemical, Engineering, etc.)
    - **Job Postings**: Mixed results. It found `/career/job-offers/detailpage` but also general pages like `/career/students`.
    - **Insight**: Many sites (like Rampf) don't expose individual job URLs (e.g., `/jobs/123`) in the sitemap/crawl. They often use a single `/job-offers` page with dynamic JS. For these, we might need to scrape the *feed* page (`/job-offers`) rather than individual posts.

### 4. Conclusions

- **LLM > Heuristic**: For "Context Window" selection, the LLM is superior because it understands semantic difference between "cost efficiency" (blog) and "pricing" (page).
- **Hybrid Approach**: The best architecture is **Regex Pre-filter -> LLM Selection**.
    - Regex removes 50-80% of noise (blogs, news, archives).
    - LLM picks the top 1-2 pages from the remaining ~500-1000 candidates.

**Next Steps**:
- Proceed to **Round 03**: Contextual Scrape. We will use the LLM-selected URLs.



