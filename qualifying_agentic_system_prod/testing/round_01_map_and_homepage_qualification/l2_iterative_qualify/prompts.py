#!/usr/bin/env python3
"""
L2 Iterative Qualification - Prompt Templates

Three prompt types:
1. INITIAL_QUALIFICATION - First pass with homepage content
2. PAGE_SELECTION - Select pages from map based on low-confidence questions
3. REQUALIFICATION - Re-evaluate with additional page content

Following OPTIMUS PRIME Protocol v2.0
"""

import json
from typing import Optional

# ═══════════════════════════════════════════════════════════════
# PROMPT 1: INITIAL QUALIFICATION (Homepage)
# ═══════════════════════════════════════════════════════════════

INITIAL_QUALIFICATION_PROMPT = """You are a chemical industry analyst classifying companies for B2B sales outreach.

<client_context>
We target: B2B sellers of chemical and technical products (manufacturers and distributors), especially where quoting requires specs/variants/docs (e.g., SDS/TDS), and product knowledge.
</client_context>

<company>
Domain: {domain}
</company>

<page_content>
{page_content}
</page_content>

<task>
Analyze this company's homepage and classify them. Answer each question with a confidence level.

Confidence levels:
- HIGH: Clear, direct evidence on the page
- MEDIUM: Reasonable inference from available information
- LOW: Weak signals, uncertain
- INSUFFICIENT: No relevant information found
</task>

<categories>
QUALIFIED CATEGORIES (assign if criteria met):
- CHEMICAL: Adhesives, coatings, resins, solvents, surfactants, polymers, catalysts, additives, paints, inks, pigments, lubricants, industrial fluids, specialty ingredients
- PHARMA: Lab chemicals/reagents, bioprocess supplies, diagnostic materials, research chemicals, pharma intermediates
- ENGINEERED_MATERIALS: Graphite, carbon materials, engineered plastics, composites, technical ceramics, abrasives, specialty alloys
- OTHER_TECHNICAL: Water treatment, electronic chemicals, construction chemicals, oilfield/mining chemicals, personal care ingredients, industrial gases

DISQUALIFIED (with reason):
- COMMODITY_ONLY: Only bulk chemicals with public price indexes (methanol, benzene, HDPE, acetone, etc.)
- NOT_PRODUCT_SELLER: Services-only, consulting, logistics, equipment, software, testing labs
- RETAIL_ONLY: Consumer/DTC brand with no B2B arm
- BROKER_ONLY: Pure trader/agent with no inventory or manufacturing

INSUFFICIENT_INFO: Cannot determine from available content
</categories>

<output_format>
Return ONLY valid JSON (no markdown, no explanation):
{{
  "company_name": "<string>",
  "final_classification": "<CHEMICAL|PHARMA|ENGINEERED_MATERIALS|OTHER_TECHNICAL|DISQUALIFIED|INSUFFICIENT_INFO>",
  "disqualification_reason": "<COMMODITY_ONLY|NOT_PRODUCT_SELLER|RETAIL_ONLY|BROKER_ONLY|null>",
  "answers": {{
    "sells_products": "<YES|NO|UNKNOWN>",
    "is_b2b": "<YES|NO|UNKNOWN>",
    "has_inventory_or_manufacturing": "<YES|NO|UNKNOWN>",
    "product_type": "<SPECIALTY|COMMODITY|MIXED|NOT_CHEMICAL_PRODUCTS|UNKNOWN>",
    "primary_category": "<PHARMA|ENGINEERED_MATERIALS|CHEMICAL|OTHER_TECHNICAL|NOT_APPLICABLE>"
  }},
  "confidence": {{
    "sells_products": "<HIGH|MEDIUM|LOW|INSUFFICIENT>",
    "is_b2b": "<HIGH|MEDIUM|LOW|INSUFFICIENT>",
    "has_inventory_or_manufacturing": "<HIGH|MEDIUM|LOW|INSUFFICIENT>",
    "product_type": "<HIGH|MEDIUM|LOW|INSUFFICIENT>",
    "primary_category": "<HIGH|MEDIUM|LOW|INSUFFICIENT>"
  }},
  "products_found": ["<product1>", "<product2>", ...],
  "needs_more_pages": <true|false>,
  "suggested_page_types": ["<page_type1>", "<page_type2>", ...],
  "pages_reviewed": ["{url}"],
  "evidence": [
    {{"url": "<url>", "excerpt": "<max 240 chars>", "supports_question": "<question_field>"}}
  ]
}}
</output_format>"""


# ═══════════════════════════════════════════════════════════════
# PROMPT 2: PAGE SELECTION (From Map)
# ═══════════════════════════════════════════════════════════════

PAGE_SELECTION_PROMPT = """You are selecting pages to scrape for company qualification.

<context>
We previously analyzed this company's homepage but need more information.
Your task: Select up to {max_pages} URLs from the site map that are most likely to help answer the LOW confidence questions.
</context>

<company>
Domain: {domain}
</company>

<previous_analysis>
Questions with HIGH confidence (DO NOT investigate further):
{high_confidence_questions}

Questions with LOW/INSUFFICIENT confidence (PRIORITIZE these):
{low_confidence_questions}

Suggested page types from previous analysis: {suggested_page_types}
</previous_analysis>

<already_scraped>
{already_scraped_urls}
</already_scraped>

<site_map>
{site_map_urls}
</site_map>

<selection_guidance>
Prioritize URLs based on what information is needed:
- For sells_products/product_type/primary_category: /products, /solutions, /catalog, /offerings, /brands
- For is_b2b: /about, /industries, /customers, /markets-served
- For has_inventory_or_manufacturing: /about, /facilities, /manufacturing, /capabilities, /locations

AVOID:
- Already scraped URLs
- Login/account pages (/login, /signin, /my-account)
- Legal pages (/privacy, /terms, /legal, /cookie)
- Blog posts and news (/blog/*, /news/*, /press/*)
- Documentation/API pages (/docs, /api, /developers)
- Career pages unless checking for manufacturing signals (/careers, /jobs)
- Pagination pages (/page/2, ?page=3)
- Language variants if English available (/de/, /fr/, /es/)
</selection_guidance>

<output_format>
Return ONLY valid JSON (no markdown, no explanation):
{{
  "selected_urls": [
    {{"url": "<full_url>", "reason": "<why this page helps answer which question>", "target_question": "<question_field>"}},
    ...
  ],
  "selection_summary": "<brief explanation of selection strategy>"
}}
</output_format>"""


# ═══════════════════════════════════════════════════════════════
# PROMPT 3: REQUALIFICATION (With Additional Pages)
# ═══════════════════════════════════════════════════════════════

REQUALIFICATION_PROMPT = """You are re-evaluating a company classification with additional page content.

<client_context>
We target: B2B sellers of chemical and technical products (manufacturers and distributors), especially where quoting requires specs/variants/docs (e.g., SDS/TDS), and product knowledge.
</client_context>

<company>
Domain: {domain}
</company>

<previous_analysis>
KEEP THESE ANSWERS (HIGH confidence - do not change):
{locked_answers}

RE-EVALUATE THESE (had LOW/INSUFFICIENT confidence):
{questions_to_reevaluate}
</previous_analysis>

<all_page_content>
{all_page_content}
</all_page_content>

<task>
Re-evaluate ONLY the questions marked for re-evaluation. Keep the HIGH confidence answers from previous analysis.
Update confidence levels based on new evidence.
</task>

<categories>
QUALIFIED CATEGORIES:
- CHEMICAL: Adhesives, coatings, resins, solvents, surfactants, polymers, catalysts, additives, paints, inks, pigments, lubricants, industrial fluids, specialty ingredients
- PHARMA: Lab chemicals/reagents, bioprocess supplies, diagnostic materials, research chemicals, pharma intermediates
- ENGINEERED_MATERIALS: Graphite, carbon materials, engineered plastics, composites, technical ceramics, abrasives, specialty alloys
- OTHER_TECHNICAL: Water treatment, electronic chemicals, construction chemicals, oilfield/mining chemicals, personal care ingredients, industrial gases

DISQUALIFIED (with reason):
- COMMODITY_ONLY: Only bulk chemicals with public price indexes
- NOT_PRODUCT_SELLER: Services-only, consulting, logistics, equipment
- RETAIL_ONLY: Consumer/DTC brand with no B2B arm
- BROKER_ONLY: Pure trader/agent with no inventory

INSUFFICIENT_INFO: Cannot determine from available content
</categories>

<output_format>
Return ONLY valid JSON (no markdown, no explanation):
{{
  "company_name": "<string>",
  "final_classification": "<CHEMICAL|PHARMA|ENGINEERED_MATERIALS|OTHER_TECHNICAL|DISQUALIFIED|INSUFFICIENT_INFO>",
  "disqualification_reason": "<COMMODITY_ONLY|NOT_PRODUCT_SELLER|RETAIL_ONLY|BROKER_ONLY|null>",
  "answers": {{
    "sells_products": "<YES|NO|UNKNOWN>",
    "is_b2b": "<YES|NO|UNKNOWN>",
    "has_inventory_or_manufacturing": "<YES|NO|UNKNOWN>",
    "product_type": "<SPECIALTY|COMMODITY|MIXED|NOT_CHEMICAL_PRODUCTS|UNKNOWN>",
    "primary_category": "<PHARMA|ENGINEERED_MATERIALS|CHEMICAL|OTHER_TECHNICAL|NOT_APPLICABLE>"
  }},
  "confidence": {{
    "sells_products": "<HIGH|MEDIUM|LOW|INSUFFICIENT>",
    "is_b2b": "<HIGH|MEDIUM|LOW|INSUFFICIENT>",
    "has_inventory_or_manufacturing": "<HIGH|MEDIUM|LOW|INSUFFICIENT>",
    "product_type": "<HIGH|MEDIUM|LOW|INSUFFICIENT>",
    "primary_category": "<HIGH|MEDIUM|LOW|INSUFFICIENT>"
  }},
  "products_found": ["<product1>", "<product2>", ...],
  "needs_more_pages": <true|false>,
  "suggested_page_types": ["<page_type1>", "<page_type2>", ...],
  "pages_reviewed": ["<url1>", "<url2>", ...],
  "evidence": [
    {{"url": "<url>", "excerpt": "<max 240 chars>", "supports_question": "<question_field>"}}
  ]
}}
</output_format>"""


# ═══════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def build_initial_qualification_prompt(
    domain: str,
    page_content: str,
    url: str,
    max_content_length: int = 50000
) -> str:
    """Build prompt for initial homepage qualification."""
    # Truncate content if too long
    if len(page_content) > max_content_length:
        page_content = page_content[:max_content_length] + "\n\n[CONTENT TRUNCATED]"

    return INITIAL_QUALIFICATION_PROMPT.format(
        domain=domain,
        page_content=page_content,
        url=url
    )


def build_page_selection_prompt(
    domain: str,
    high_confidence_questions: dict,
    low_confidence_questions: dict,
    suggested_page_types: list,
    already_scraped_urls: list,
    site_map_urls: list,
    max_pages: int = 5,
    max_urls_in_prompt: int = 500
) -> str:
    """Build prompt for page selection from map."""

    # Format high confidence questions
    high_conf_str = ""
    for q, data in high_confidence_questions.items():
        high_conf_str += f"- {q}: {data['answer']} (HIGH confidence)\n"
    if not high_conf_str:
        high_conf_str = "- None (all questions need more information)\n"

    # Format low confidence questions with hints
    low_conf_str = ""
    page_hints = {
        "sells_products": "Look for: /products, /solutions, /catalog",
        "is_b2b": "Look for: /about, /industries, /customers",
        "has_inventory_or_manufacturing": "Look for: /facilities, /manufacturing, /capabilities",
        "product_type": "Look for: /products with specs, grades, TDS/SDS",
        "primary_category": "Look for: /products, /solutions, /applications"
    }
    for q, data in low_confidence_questions.items():
        hint = page_hints.get(q, "")
        low_conf_str += f"- {q}: {data['answer']} ({data['confidence']} confidence) - {hint}\n"

    # Format already scraped
    already_scraped_str = "\n".join(f"- {url}" for url in already_scraped_urls) or "- None yet"

    # Truncate site map if too long
    if len(site_map_urls) > max_urls_in_prompt:
        site_map_urls = site_map_urls[:max_urls_in_prompt]
    site_map_str = "\n".join(site_map_urls)

    return PAGE_SELECTION_PROMPT.format(
        domain=domain,
        max_pages=max_pages,
        high_confidence_questions=high_conf_str,
        low_confidence_questions=low_conf_str,
        suggested_page_types=json.dumps(suggested_page_types),
        already_scraped_urls=already_scraped_str,
        site_map_urls=site_map_str
    )


def build_requalification_prompt(
    domain: str,
    locked_answers: dict,
    questions_to_reevaluate: list,
    all_page_content: str,
    max_content_length: int = 80000
) -> str:
    """Build prompt for re-qualification with additional pages."""

    # Format locked answers
    locked_str = ""
    for q, data in locked_answers.items():
        locked_str += f"- {q}: {data['answer']} (HIGH confidence - DO NOT CHANGE)\n"
    if not locked_str:
        locked_str = "- None (all questions open for re-evaluation)\n"

    # Format questions to re-evaluate
    reevaluate_str = "\n".join(f"- {q}" for q in questions_to_reevaluate)

    # Truncate content if too long
    if len(all_page_content) > max_content_length:
        all_page_content = all_page_content[:max_content_length] + "\n\n[CONTENT TRUNCATED]"

    return REQUALIFICATION_PROMPT.format(
        domain=domain,
        locked_answers=locked_str,
        questions_to_reevaluate=reevaluate_str,
        all_page_content=all_page_content
    )


def parse_qualification_response(response_text: str) -> Optional[dict]:
    """Parse JSON response from qualification prompt."""
    try:
        # Clean up response - remove markdown code blocks if present
        cleaned = response_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"JSON parse error: {e}")
        return None


def parse_page_selection_response(response_text: str) -> Optional[dict]:
    """Parse JSON response from page selection prompt."""
    return parse_qualification_response(response_text)  # Same logic


# ═══════════════════════════════════════════════════════════════
# CONFIDENCE UTILITIES
# ═══════════════════════════════════════════════════════════════

CONFIDENCE_ORDER = ["INSUFFICIENT", "LOW", "MEDIUM", "HIGH"]

def is_high_confidence(confidence: str) -> bool:
    """Check if confidence is HIGH."""
    return confidence == "HIGH"

def is_low_confidence(confidence: str) -> bool:
    """Check if confidence is LOW or INSUFFICIENT."""
    return confidence in ["LOW", "INSUFFICIENT"]

def get_low_confidence_questions(confidence_dict: dict) -> dict:
    """Get questions with LOW or INSUFFICIENT confidence."""
    return {
        q: {"confidence": c, "answer": None}
        for q, c in confidence_dict.items()
        if is_low_confidence(c)
    }

def get_high_confidence_questions(confidence_dict: dict, answers_dict: dict) -> dict:
    """Get questions with HIGH confidence and their answers."""
    return {
        q: {"confidence": c, "answer": answers_dict.get(q)}
        for q, c in confidence_dict.items()
        if is_high_confidence(c)
    }

def should_continue_iteration(
    confidence_dict: dict,
    needs_more_pages: bool,
    current_iteration: int,
    max_iterations: int,
    critical_questions: list = None
) -> bool:
    """Determine if we should continue to next iteration."""
    if critical_questions is None:
        critical_questions = ["sells_products", "product_type", "primary_category"]

    # Stop if max iterations reached
    if current_iteration >= max_iterations:
        return False

    # Stop if Claude says no more pages needed
    if not needs_more_pages:
        return False

    # Continue if any critical question has low confidence
    for q in critical_questions:
        if q in confidence_dict and is_low_confidence(confidence_dict[q]):
            return True

    return False
