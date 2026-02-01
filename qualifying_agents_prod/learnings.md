# Qualifying Agents Prod - Master Plan & Learnings

**Status**: 🚧 Planning Phase
**Date**: 2025-11-23
**Objective**: Utilize `/map` endpoint to qualify companies based on multiple pages (contextual qualification) rather than single landing pages.

---

## 1. Review of Existing Systems

### A. `search_system_prod` (Active)
*   **Architecture**: L1 Search -> L2 Scrape -> L3 Classify.
*   **L2 Scrape (`layer_scrape.py`)**:
    *   Uses `/v2/scrape` on the *single* URL returned by L1.
    *   **Limitation**: Only sees the landing page. If pricing or specific qualification criteria are on `/pricing` or `/about`, the LLM misses it.
*   **L3 Classify (`layer_classify.py`)**:
    *   Uses Claude (Haiku/Sonnet) to classify based on that single page's markdown.
    *   **Pros**: Fast, simple.
    *   **Cons**: Low confidence for complex qualification (e.g., "Do they have enterprise pricing?" might not be on home page).

### B. `crawl_system_prod` (Design Only)
*   **Status**: Design document exists (`PRODUCTION_DESIGN.md`), but no implementation code found.
*   **Architecture**: Config-driven Crawl + Extraction Spec.
*   **Concept**:
    *   Decouples "What to crawl" from "How to extract".
    *   Supports `max_depth` and link following.
    *   **Limitation**: Traditional crawling (following links) can be noisy and expensive (crawling 50 pages to find 1 relevant one).

---

## 2. The New Approach: `qualifying_agents_prod`

### Core Philosophy: "Map-then-Qualify"
Instead of scraping just the home page (too little info) or crawling everything (too expensive/noisy), we use the `/map` endpoint to intelligently select the *right* pages to form a "Context Window" for the company.

### Proposed Architecture

#### **Step 1: Map (`/v2/map`)**
*   **Input**: Company Domain (e.g., `example.com`).
*   **Action**: Call Firecrawl `/map` endpoint.
*   **Output**: List of all URLs on the site (e.g., `/about`, `/pricing`, `/team`, `/blog/post-1`).

#### **Step 2: Select High-Value Pages (Heuristic/LLM)**
*   **Problem**: We can't scrape 1000 pages. We need the *best* 3-5 pages for qualification.
*   **Logic**: Filter the map results for keywords:
    *   `about`, `company`, `mission` -> **Identity**
    *   `pricing`, `plans`, `cost` -> **Budget/Tier**
    *   `team`, `people`, `careers` -> **Size/Growth**
    *   `contact`, `demo`, `book` -> **Intent**
*   **Output**: List of 3-5 Priority URLs.

#### **Step 3: Contextual Scrape (`/v2/scrape`)**
*   **Action**: Scrape the selected Priority URLs.
*   **Output**: Markdown for Home + Pricing + About + Team.

#### **Step 4: Multi-Page Qualification (LLM)**
*   **Input**: Aggregated Markdown from all selected pages.
*   **Prompt**: "Based on the Home page, Pricing page, and About page, does this company meet criteria X?"
*   **Result**: High-confidence qualification based on holistic view.

---

## 3. Implementation Plan

### Phase 1: Foundation
*   [ ] Create `core/layer_map.py`: Implementation of `/v2/map`.
*   [ ] Create `core/selector.py`: Logic to filter map results into "Context Sets".

### Phase 2: Pipeline Integration
*   [ ] Integrate with existing L1 (Search) or accept direct domain input.
*   [ ] Build `layer_context_scrape.py`: Scrape the selected list.

### Phase 3: Qualification Agent
*   [ ] Build `layer_qualify.py`: LLM agent that accepts multi-page context.

---

## 4. Key Hypotheses to Test
1.  **Map Quality**: Does `/map` reliably find `/pricing` pages?
2.  **Cost vs. Value**: Is the cost of 3-5 scrapes per lead worth the increased qualification accuracy? (Likely yes for high-ticket B2B).
3.  **Context Window**: Can we fit 5 pages of markdown into Haiku/Sonnet context window efficiently? (May need summarization or smart truncation).
