#!/usr/bin/env python3
"""
L2: Map + Iterative Qualification Layer (OpenAI Version)

This layer is ONLY called when L1 (homepage) was insufficient.
It:
1. Maps the site structure using /v2/map
2. Uses GPT to select relevant pages based on low-confidence questions
3. Scrapes selected pages and re-qualifies
4. Iterates until confident or max pages reached

Following OPTIMUS PRIME Protocol v2.0
"""

import os
import sys
import json
import time
import requests
import threading
from pathlib import Path
from typing import Optional, Tuple, Dict, List
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed

from core_openai_deep.markdown_cleaner import strip_markdown

SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent

# Import from layer_homepage for shared utilities
from core_openai_deep.layer_homepage import (
    call_openai,
    calculate_retry_delay,
    classify_error,
    load_env,
    AnalysisSpec,
    FIRECRAWL_API_KEY,
    OPENAI_API_KEY,
    MAX_RETRIES,
)

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════

# Default semaphores - can be overridden
MAP_SEMAPHORE = threading.Semaphore(50)
SCRAPE_SEMAPHORE = threading.Semaphore(50)

# ═══════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════

@dataclass
class IterativeResult:
    """Result from L2 iterative qualification"""
    domain: str
    success: bool

    # Final classification
    classification: Optional[str] = None
    disqualification_reason: Optional[str] = None
    answers: Optional[Dict] = None
    confidence: Optional[Dict] = None
    products_found: Optional[List] = None
    evidence: Optional[List] = None

    # Metrics
    pages_scraped: int = 0
    iterations: int = 0
    site_map_size: int = 0
    credits_used: int = 0
    tokens_used: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0
    error: Optional[str] = None
    retry_stats: Dict = field(default_factory=dict)

    # Scraped content for reference
    scraped_urls: List[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════
# URL FILTERING
# ═══════════════════════════════════════════════════════════════

IGNORE_PATTERNS = [
    '/login', '/signin', '/signup', '/register', '/my-account', '/account',
    '/privacy', '/terms', '/legal', '/cookie', '/gdpr', '/disclaimer',
    '/blog/', '/news/', '/press/', '/media/',
    '/docs/', '/api/', '/developers/', '/documentation/',
    '/careers/', '/jobs/', '/job/',
    '/page/', '?page=', '&page=',
    '/de/', '/fr/', '/es/', '/it/', '/ja/', '/zh/', '/ko/', '/ru/', '/pt/',
    '/cart', '/checkout', '/wishlist',
    '.pdf', '.jpg', '.png', '.gif', '.svg', '.webp',
    '/search', '/tag/', '/category/',
    '/wp-content/', '/wp-admin/',
]


def filter_map_urls(urls: list, already_scraped: list = None) -> list:
    """Filter map URLs to remove noise"""
    if already_scraped is None:
        already_scraped = []

    already_scraped_set = set(already_scraped)
    filtered = []

    for url in urls:
        if isinstance(url, dict):
            url = url.get('url', '')
        url_lower = url.lower()

        if url in already_scraped_set:
            continue
        if any(pattern in url_lower for pattern in IGNORE_PATTERNS):
            continue

        filtered.append(url)

    return filtered


# ═══════════════════════════════════════════════════════════════
# FIRECRAWL MAP
# ═══════════════════════════════════════════════════════════════

def firecrawl_map(
    domain: str,
    semaphore: threading.Semaphore = None,
    limit: int = 100,
    timeout: int = 60,
    log_callback=None,
    analytics=None  # Optional PipelineAnalytics for tracking
) -> Tuple[bool, list, str, Dict]:
    """
    Map a domain using Firecrawl /v2/map endpoint.

    Returns:
        Tuple of (success, urls_list, error_message, stats)
    """
    url = f"https://{domain}" if not domain.startswith("http") else domain
    stats = {"attempts": 0, "retries": 0, "duration_seconds": 0}
    start_time = time.time()

    sem = semaphore or MAP_SEMAPHORE

    def log(msg):
        if log_callback:
            log_callback(msg)

    # Track analytics
    if analytics:
        analytics.firecrawl_start()

    with sem:
        for attempt in range(MAX_RETRIES):
            stats["attempts"] = attempt + 1

            try:
                response = requests.post(
                    'https://api.firecrawl.dev/v2/map',
                    headers={
                        'Authorization': f'Bearer {FIRECRAWL_API_KEY}',
                        'Content-Type': 'application/json'
                    },
                    json={'url': url, 'limit': limit},
                    timeout=timeout
                )

                if response.status_code == 429:
                    delay = calculate_retry_delay(attempt)
                    log(f"   ⏳ Rate limited, waiting {delay:.1f}s (attempt {attempt + 1}/{MAX_RETRIES})")
                    stats["retries"] += 1
                    time.sleep(delay)
                    continue

                data = response.json()

                if data.get('success'):
                    links = data.get('links', [])
                    if links and isinstance(links[0], dict):
                        links = [link.get('url', '') for link in links]
                    stats["duration_seconds"] = time.time() - start_time
                    if analytics:
                        analytics.firecrawl_end(stats["duration_seconds"] * 1000)
                    return True, links, None, stats
                else:
                    error = data.get('error', 'Unknown API error')
                    error_type, can_retry = classify_error(Exception(error), response)

                    if can_retry and attempt < MAX_RETRIES - 1:
                        delay = calculate_retry_delay(attempt)
                        log(f"   ⏳ {error_type}: {error}, retrying in {delay:.1f}s")
                        stats["retries"] += 1
                        time.sleep(delay)
                        continue

                    stats["duration_seconds"] = time.time() - start_time
                    if analytics:
                        analytics.firecrawl_end(stats["duration_seconds"] * 1000, error=True)
                    return False, [], error, stats

            except requests.exceptions.Timeout:
                if attempt < MAX_RETRIES - 1:
                    delay = calculate_retry_delay(attempt)
                    log(f"   ⏳ Timeout, retrying in {delay:.1f}s")
                    stats["retries"] += 1
                    time.sleep(delay)
                    continue

                stats["duration_seconds"] = time.time() - start_time
                if analytics:
                    analytics.firecrawl_end(stats["duration_seconds"] * 1000, error=True)
                return False, [], f"Timeout after {MAX_RETRIES} attempts", stats

            except Exception as e:
                error_type, can_retry = classify_error(e)

                if can_retry and attempt < MAX_RETRIES - 1:
                    delay = calculate_retry_delay(attempt)
                    log(f"   ⏳ {error_type}: {e}, retrying in {delay:.1f}s")
                    stats["retries"] += 1
                    time.sleep(delay)
                    continue

                stats["duration_seconds"] = time.time() - start_time
                if analytics:
                    analytics.firecrawl_end(stats["duration_seconds"] * 1000, error=True)
                return False, [], str(e), stats

    stats["duration_seconds"] = time.time() - start_time
    if analytics:
        analytics.firecrawl_end(stats["duration_seconds"] * 1000, error=True)
    return False, [], "Max retries exceeded", stats


# ═══════════════════════════════════════════════════════════════
# FIRECRAWL SCRAPE
# ═══════════════════════════════════════════════════════════════

def firecrawl_scrape(
    url: str,
    semaphore: threading.Semaphore = None,
    timeout: int = 30000,
    request_timeout: int = 60,
    log_callback=None,
    analytics=None  # Optional PipelineAnalytics for tracking
) -> Tuple[bool, str, str, Dict]:
    """
    Scrape a URL using Firecrawl /v2/scrape endpoint.

    Returns:
        Tuple of (success, markdown_content, error_message, stats)
    """
    stats = {"attempts": 0, "retries": 0, "duration_seconds": 0}
    start_time = time.time()

    sem = semaphore or SCRAPE_SEMAPHORE

    def log(msg):
        if log_callback:
            log_callback(msg)

    # Track analytics
    if analytics:
        analytics.firecrawl_start()

    with sem:
        for attempt in range(MAX_RETRIES):
            stats["attempts"] = attempt + 1

            try:
                response = requests.post(
                    'https://api.firecrawl.dev/v2/scrape',
                    headers={
                        'Authorization': f'Bearer {FIRECRAWL_API_KEY}',
                        'Content-Type': 'application/json'
                    },
                    json={
                        'url': url,
                        'formats': ['markdown'],
                        'onlyMainContent': True,
                        'timeout': timeout
                    },
                    timeout=request_timeout
                )

                if response.status_code == 429:
                    delay = calculate_retry_delay(attempt)
                    log(f"   ⏳ Rate limited, waiting {delay:.1f}s")
                    stats["retries"] += 1
                    time.sleep(delay)
                    continue

                data = response.json()

                if data.get('success'):
                    raw_markdown = data.get('data', {}).get('markdown', '')
                    # Strip useless content (images, SVGs, social links, etc.)
                    markdown = strip_markdown(raw_markdown)
                    stats["duration_seconds"] = time.time() - start_time
                    if analytics:
                        analytics.firecrawl_end(stats["duration_seconds"] * 1000)
                    return True, markdown, None, stats
                else:
                    error = data.get('error', 'Unknown API error')
                    error_type, can_retry = classify_error(Exception(error), response)

                    if can_retry and attempt < MAX_RETRIES - 1:
                        delay = calculate_retry_delay(attempt)
                        stats["retries"] += 1
                        time.sleep(delay)
                        continue

                    stats["duration_seconds"] = time.time() - start_time
                    if analytics:
                        analytics.firecrawl_end(stats["duration_seconds"] * 1000, error=True)
                    return False, '', error, stats

            except requests.exceptions.Timeout:
                if attempt < MAX_RETRIES - 1:
                    delay = calculate_retry_delay(attempt)
                    stats["retries"] += 1
                    time.sleep(delay)
                    continue

                stats["duration_seconds"] = time.time() - start_time
                if analytics:
                    analytics.firecrawl_end(stats["duration_seconds"] * 1000, error=True)
                return False, '', f"Timeout after {MAX_RETRIES} attempts", stats

            except Exception as e:
                error_type, can_retry = classify_error(e)

                if can_retry and attempt < MAX_RETRIES - 1:
                    delay = calculate_retry_delay(attempt)
                    stats["retries"] += 1
                    time.sleep(delay)
                    continue

                stats["duration_seconds"] = time.time() - start_time
                if analytics:
                    analytics.firecrawl_end(stats["duration_seconds"] * 1000, error=True)
                return False, '', str(e), stats

    stats["duration_seconds"] = time.time() - start_time
    if analytics:
        analytics.firecrawl_end(stats["duration_seconds"] * 1000, error=True)
    return False, '', "Max retries exceeded", stats


# ═══════════════════════════════════════════════════════════════
# PROMPTS (SPEC-DRIVEN)
# ═══════════════════════════════════════════════════════════════

def build_page_selection_prompt(
    domain: str,
    spec: AnalysisSpec,
    low_confidence_questions: List[str],
    suggested_page_types: List[str],
    site_map_urls: List[str],
    already_scraped: List[str],
    max_pages: int = 1
) -> str:
    """Build COMPACT prompt for page selection - ONE page at a time."""
    scraped_list = ', '.join([u.split('/')[-1][:20] for u in already_scraped]) if already_scraped else 'homepage only'

    return f"""Select ONE page from {domain} to determine: {', '.join(low_confidence_questions)}

SCRAPED: {scraped_list}

URLS:
{chr(10).join(site_map_urls[:50])}

PRIORITY: Products/Catalog > About > Solutions > Manufacturing > Capabilities > Services
AVOID: Blog, News, Careers, Legal, Contact

JSON: {{"selected_url":{{"url":"...","reason":"...","page_type":"Products|About|Solutions|Manufacturing|Capabilities|Services"}}}}
"""


def build_requalification_prompt(
    domain: str,
    spec: AnalysisSpec,
    homepage_summary: str,  # Now a summary, not full content
    current_page_url: str,
    current_page_content: str,
    previous_page_summaries: Dict[str, str],  # url -> summary (not full content)
    previous_answers: Dict,
    previous_confidence: Dict
) -> str:
    """
    Build COMPACT prompt for re-qualification.

    Token optimization:
    - Homepage summary (~100 tokens) instead of full content
    - Page summaries (~100 tokens each) for previous pages
    - Full content ONLY for current page (5000 chars max)
    - NO spec repetition (categories, questions, logic already known from L1)
    """
    # Build content section: Homepage summary + Previous summaries + Current page (full)
    content_section = f"[HOMEPAGE]: {homepage_summary}\n"

    # Add summaries of previously scraped pages
    if previous_page_summaries:
        for url, summary in previous_page_summaries.items():
            content_section += f"[{url.split('/')[-1][:30]}]: {summary}\n"

    # Add current page in full - this is the ONLY full content we send
    content_section += f"\n=== NEW PAGE: {current_page_url} ===\n{current_page_content[:5000]}\n"

    # Build dynamic category descriptions from spec
    categories_text = ""
    category_names = []
    for cat in spec.categories:
        category_names.append(cat['name'])
        categories_text += f"- {cat['name']}: {cat.get('description', '')}\n"

    classification_options = '/'.join(category_names) + '/DISQUALIFIED'

    # Build dynamic answer fields from spec.questions
    # Match L1's logic: use answer_options if present, otherwise determine by answer_type
    answer_fields = {}
    confidence_fields = {}
    for q in spec.questions:
        field = q['field']
        if q.get('answer_options'):
            answer_fields[field] = f"one of: {', '.join(q.get('answer_options'))}"
        elif q.get('answer_type') == 'array':
            answer_fields[field] = "array of strings"
        elif q.get('answer_type') == 'boolean':
            answer_fields[field] = "true/false"
        else:
            answer_fields[field] = "string"
        confidence_fields[field] = "HIGH/MEDIUM/LOW/INSUFFICIENT"

    # Build disqualification reasons from spec
    disqualification_reasons = [rule.get('reason') for rule in spec.disqualification_rules if rule.get('reason')]
    disq_reasons_text = '/'.join(disqualification_reasons) + ' or null' if disqualification_reasons else 'null'

    # Build question guidance (CRITICAL for industry inference)
    question_guidance = "\n".join([
        f"- {q['field']}: {q.get('guidance', 'No guidance.')}"
        for q in spec.questions if q.get('guidance')
    ])

    return f"""Re-qualify {domain} for: {spec.client_description}

CURRENT ASSESSMENT:
{json.dumps(previous_answers)} | Confidence: {json.dumps(previous_confidence)}

CONTEXT:
{content_section}

QUESTION GUIDANCE:
{question_guidance}

MANDATORY INDUSTRY INFERENCE (CRITICAL - YOU MUST APPLY THESE RULES):
For "likely_imports_to_us" - If company sells products in these categories AND NO explicit "Made in USA/handcrafted in [US state]" claim:
- Formal dresses/gowns/prom dresses/wedding dresses → MUST answer TRUE (almost all imported)
- Apparel/fashion/clothing brands → MUST answer TRUE (almost all imported)
- Footwear/shoes → MUST answer TRUE (almost all imported)
- Electronics/consumer electronics → MUST answer TRUE (almost all imported)
- German/Japanese/European specialty tools → MUST answer TRUE (imported)
- Beauty/cosmetics → MUST answer TRUE (ingredients imported)
- Jewelry → MUST answer TRUE (materials imported)
DO NOT require explicit "Made in China" statements - the industry itself implies imports!

For "is_brand_owner_or_direct_importer" - Answer TRUE if:
- Company name appears as a brand on products (e.g., "Alyce Paris" dresses = brand owner)
- They design/sell their own product line
- ALSO TRUE for multi-brand retailers: if they stock international/niche brands (Korean beauty, Japanese tools, European fashion), they are likely direct importers
Only answer FALSE if they explicitly source from US distributors, or only stock mainstream US-distributed brands (Nike, Adidas, etc).

For "sells_physical_products" - Answer TRUE if:
- Product catalogs, shop pages, add-to-cart buttons, product images showing physical goods
- ALSO TRUE: Shipbuilders (build ships/vessels/boats), heavy machinery manufacturers, industrial equipment makers - these are physical products even without e-commerce
Answer FALSE only for: pure services (consulting, software), digital-only products

For "ships_internationally" - INDUSTRY INFERENCE FOR EXPORTS (answer TRUE if no explicit US-only shipping):
- Fashion/apparel/formal dress brands with confirmed imports → MUST answer TRUE (fashion brands almost always ship globally)
- Shipbuilders/vessel manufacturers → MUST answer TRUE (ships are exported globally)
- Specialty tool importers (German/Japanese tools) → MUST answer TRUE (specialty markets ship worldwide)
- E-commerce sites with Shopify/standard platforms and confirmed imports → LEAN YES (most enable international shipping)
Do NOT require explicit "ships worldwide" - if they import goods AND are in a globally-traded industry, assume they export too!

CRITICAL - EXHAUSTIVE SEARCH REQUIRED:
If "likely_imports_to_us" is still FALSE, you MUST set: sufficient=false, needs_more_pages=true
If "ships_internationally" is still FALSE, you MUST set: sufficient=false, needs_more_pages=true
Do NOT mark sufficient=true until you have found POSITIVE evidence for BOTH import AND export signals, or exhausted all available pages.

Update answers based on new evidence. Classify as: {classification_options}.
{categories_text}
DISQUALIFY if evidence clearly disqualifies (reasons: {disq_reasons_text})

JSON response:
{{"sufficient":bool,"company_name":"...","final_classification":"...","disqualification_reason":"{disq_reasons_text}","answers":{json.dumps(answer_fields, indent=8)},"confidence":{json.dumps(confidence_fields, indent=8)},"products_found":["..."],"needs_more_pages":bool,"current_page_summary":"1-2 sentence summary of this page"}}
"""


def parse_json_response(response_text: str) -> Optional[Dict]:
    """Parse JSON from OpenAI response."""
    import re

    try:
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            return json.loads(json_match.group())
    except json.JSONDecodeError:
        pass

    return None


# ═══════════════════════════════════════════════════════════════
# MAIN L2 FUNCTION
# ═══════════════════════════════════════════════════════════════

def process_iterative(
    domain: str,
    spec: AnalysisSpec,
    homepage_content: str,
    homepage_url: str,
    homepage_summary: str,  # NEW: Summary of homepage for re-qualification prompts
    previous_answers: Dict,
    previous_confidence: Dict,
    low_confidence_questions: List[str],
    suggested_page_types: List[str],
    max_pages: int = 20,
    min_pages: int = 10,  # NEW: Minimum pages to scrape before allowing early stop
    openai_model: str = "gpt-5-mini",
    firecrawl_semaphore: threading.Semaphore = None,
    openai_semaphore: threading.Semaphore = None,
    log_callback=None,
    analytics=None  # Optional PipelineAnalytics for tracking
) -> IterativeResult:
    """
    L2: Map site and SEQUENTIALLY scrape pages until confident.

    Only called when L1 (homepage) was insufficient.

    DEEP MODE APPROACH (Sequential Single-Page with Minimum):
    - Selects ONE page at a time based on strict priority order
    - Scrapes it and re-qualifies with accumulated context
    - ENFORCES minimum pages before allowing early stop
    - Only stops early after min_pages if high confidence achieved

    Priority Order for Page Selection:
    1. Products/Catalog - HIGHEST
    2. About Us
    3. Solutions
    4. Manufacturing
    5. Capabilities
    6. Services - LOWEST

    Args:
        domain: Company domain
        spec: Analysis specification
        homepage_content: Already-scraped homepage content from L1
        homepage_url: Homepage URL
        previous_answers: Answers from L1
        previous_confidence: Confidence from L1
        low_confidence_questions: Questions needing more info
        suggested_page_types: Page types to look for (deprecated, not used)
        max_pages: Maximum additional pages to scrape (default 20)
        min_pages: Minimum pages to scrape before allowing early stop (default 10)
        openai_model: OpenAI model to use
        firecrawl_semaphore: Semaphore for Firecrawl rate limiting
        openai_semaphore: Semaphore for OpenAI rate limiting
        log_callback: Optional callback for logging

    Returns:
        IterativeResult with final qualification
    """
    def log(msg):
        if log_callback:
            log_callback(msg)
        print(msg)

    start_time = time.time()
    result = IterativeResult(domain=domain, success=False)
    retry_stats = {"map": 0, "scrape": 0, "openai": 0}

    # Track scraped content
    scraped_urls = [homepage_url]
    scraped_content = {homepage_url: homepage_content}  # Full content only for current page
    page_summaries = {}  # url -> summary (for previous pages, ~100 tokens each)

    log(f"\n{'='*60}")
    log(f"🗺️  L2: MAP + ITERATIVE QUALIFICATION - {domain}")
    log(f"{'='*60}")
    log(f"Low confidence questions: {low_confidence_questions}")

    # ─────────────────────────────────────────────────────────
    # STEP 1: MAP THE SITE
    # ─────────────────────────────────────────────────────────
    log(f"\n📍 Step 1: Mapping site structure...")

    map_success, site_map, map_error, map_stats = firecrawl_map(
        domain, semaphore=firecrawl_semaphore, limit=100, log_callback=log, analytics=analytics
    )
    result.credits_used += 1
    retry_stats["map"] = map_stats.get("retries", 0)

    if not map_success:
        result.error = f"Map failed: {map_error}"
        result.duration_ms = int((time.time() - start_time) * 1000)
        result.retry_stats = retry_stats
        log(f"❌ Map failed: {map_error}")
        return result

    result.site_map_size = len(site_map)
    filtered_map = filter_map_urls(site_map, scraped_urls)
    log(f"✅ Found {len(site_map)} URLs, {len(filtered_map)} after filtering")

    # ─────────────────────────────────────────────────────────
    # STEP 2: SEQUENTIAL SINGLE-PAGE SCRAPING
    # ─────────────────────────────────────────────────────────
    # New approach: Select and scrape ONE page at a time, re-qualify after each
    # This is more efficient as we may only need 1-2 pages instead of always 5

    current_answers = previous_answers.copy() if previous_answers else {}
    current_confidence = previous_confidence.copy() if previous_confidence else {}
    current_low_conf = low_confidence_questions.copy() if low_confidence_questions else []
    qualification = None

    # Track pages scraped beyond homepage
    pages_scraped_count = 0

    while pages_scraped_count < max_pages:
        result.iterations = pages_scraped_count + 1

        # Check if we have pages left to try
        total_pages = pages_scraped_count + 1  # +1 for homepage
        if not filtered_map:
            if total_pages >= min_pages:
                log(f"\n   ⚠️ No more pages available in site map (reached {total_pages} pages)")
                break
            else:
                log(f"\n   ⚠️ Site map exhausted at {total_pages}/{min_pages} pages - cannot reach minimum")
                break  # Can't continue without URLs, but log the issue

        log(f"\n📍 Page {pages_scraped_count + 1}/{max_pages}: Selecting next best page...")

        # ─────────────────────────────────────────────────────
        # 2a: SELECT SINGLE BEST PAGE
        # ─────────────────────────────────────────────────────
        selection_prompt = build_page_selection_prompt(
            domain=domain,
            spec=spec,
            low_confidence_questions=current_low_conf,
            suggested_page_types=[],  # Not used in new prompt
            site_map_urls=filtered_map,
            already_scraped=scraped_urls,
            max_pages=1  # Always 1 now
        )

        # GPT-5-mini is a reasoning model - needs higher token limits for reasoning phase
        # GPT-5-nano is more verbose - increased from 1500 to 3000
        sel_success, sel_response, sel_in, sel_out, sel_error, sel_stats = call_openai(
            selection_prompt, semaphore=openai_semaphore, model=openai_model, max_tokens=3000, log_callback=log, analytics=analytics
        )
        result.tokens_used += sel_in + sel_out
        result.input_tokens += sel_in
        result.output_tokens += sel_out
        retry_stats["openai"] += sel_stats.get("retries", 0)

        if not sel_success:
            log(f"   ⚠️ Page selection failed: {sel_error}")
            total_pages = pages_scraped_count + 1
            if total_pages >= min_pages:
                break
            else:
                log(f"   🔄 Continuing despite selection error ({total_pages}/{min_pages} min pages)")
                # Use fallback selection below

        selection = parse_json_response(sel_response)

        # Handle new single-page format
        selected_url = None
        page_type = "unknown"
        if selection:
            if selection.get('selected_url'):
                # New format: {"selected_url": {"url": "...", "reason": "...", "page_type": "..."}}
                selected_url = selection['selected_url'].get('url')
                page_type = selection['selected_url'].get('page_type', 'unknown')
            elif selection.get('selected_urls'):
                # Fallback to old format if LLM uses it
                selected_url = selection['selected_urls'][0].get('url')

        if not selected_url:
            # DEEP MODE: Fallback - select page based on URL patterns
            priority_patterns = [
                ('shipping', 'Shipping'), ('delivery', 'Shipping'), ('faq', 'FAQ'),
                ('about', 'About'), ('about-us', 'About'), ('our-story', 'About'),
                ('products', 'Products'), ('shop', 'Products'), ('collections', 'Products'),
                ('contact', 'Contact'), ('help', 'Help'), ('support', 'Support'),
                ('policy', 'Policy'), ('terms', 'Terms'), ('returns', 'Returns')
            ]
            for pattern, ptype in priority_patterns:
                for url in filtered_map:
                    if pattern in url.lower():
                        selected_url = url
                        page_type = f"Fallback-{ptype}"
                        break
                if selected_url:
                    break

            # Last resort: just take the first available URL
            if not selected_url and filtered_map:
                selected_url = filtered_map[0]
                page_type = "Fallback-First"

            if not selected_url:
                log(f"   ⚠️ No pages available to select")
                break

            log(f"   🔄 Fallback selection: {selected_url}")

        log(f"   → Selected [{page_type}]: {selected_url}")

        # ─────────────────────────────────────────────────────
        # 2b: SCRAPE THE SINGLE PAGE
        # ─────────────────────────────────────────────────────
        scrape_ok, content, scrape_err, s_stats = firecrawl_scrape(
            selected_url, semaphore=firecrawl_semaphore, log_callback=log, analytics=analytics
        )
        result.credits_used += 1
        retry_stats["scrape"] += s_stats.get("retries", 0)
        pages_scraped_count += 1

        if scrape_ok and content:
            scraped_urls.append(selected_url)
            scraped_content[selected_url] = content
            log(f"   ✅ Scraped ({len(content)} chars)")
        else:
            log(f"   ⚠️ Scrape failed: {scrape_err}")
            # Remove from filtered_map so we don't try again
            filtered_map = [u for u in filtered_map if u != selected_url]
            continue  # Try next page

        # Update filtered map to exclude scraped URLs
        filtered_map = filter_map_urls(filtered_map, scraped_urls)

        # ─────────────────────────────────────────────────────
        # 2c: RE-QUALIFY WITH CURRENT PAGE + SUMMARIES
        # ─────────────────────────────────────────────────────
        log(f"   Re-qualifying with homepage + {len(page_summaries)} summaries + current page...")

        requalify_prompt = build_requalification_prompt(
            domain=domain,
            spec=spec,
            homepage_summary=homepage_summary,  # Using summary, not full homepage content!
            current_page_url=selected_url,
            current_page_content=content,
            previous_page_summaries=page_summaries,  # Summaries, not full content!
            previous_answers=current_answers,
            previous_confidence=current_confidence
        )

        # GPT-5-nano is more verbose - increased from 2000 to 4000
        req_success, req_response, req_in, req_out, req_error, req_stats = call_openai(
            requalify_prompt, semaphore=openai_semaphore, model=openai_model, max_tokens=4000, log_callback=log, analytics=analytics
        )
        result.tokens_used += req_in + req_out
        result.input_tokens += req_in
        result.output_tokens += req_out
        retry_stats["openai"] += req_stats.get("retries", 0)

        if not req_success:
            log(f"   ⚠️ Re-qualification failed: {req_error}")
            total_pages = pages_scraped_count + 1
            if total_pages >= min_pages:
                break
            else:
                log(f"   🔄 Continuing despite error ({total_pages}/{min_pages} min pages)")
                continue

        qualification = parse_json_response(req_response)
        if not qualification:
            log(f"   ⚠️ Failed to parse response")
            total_pages = pages_scraped_count + 1
            if total_pages >= min_pages:
                break
            else:
                log(f"   🔄 Continuing despite parse error ({total_pages}/{min_pages} min pages)")
                continue

        # Extract and store the page summary for next iteration
        current_page_summary = qualification.get('current_page_summary', '')
        if current_page_summary:
            page_summaries[selected_url] = current_page_summary
            log(f"   📝 Stored summary ({len(current_page_summary)} chars)")
        else:
            # Fallback: use first 200 chars of content if no summary provided
            page_summaries[selected_url] = content[:200] + "..."
            log(f"   📝 No summary in response, using content excerpt")

        # Update state for next iteration
        current_answers = qualification.get('answers', current_answers)
        current_confidence = qualification.get('confidence', current_confidence)

        # Update low confidence questions for next selection
        current_low_conf = [
            q for q, c in current_confidence.items()
            if c in ['LOW', 'MEDIUM', 'INSUFFICIENT']
        ]

        # DEEP MODE: Only allow early exit AFTER min_pages have been scraped
        # Total pages = homepage (1) + pages_scraped_count
        total_pages = pages_scraped_count + 1  # +1 for homepage

        # CRITICAL SIGNAL CHECK: Force continued searching if critical answers are FALSE
        # These questions require exhaustive search before giving up
        critical_questions_needing_positive = ['likely_imports_to_us', 'ships_internationally']
        critical_missing = [
            q for q in critical_questions_needing_positive
            if current_answers.get(q) is False or current_answers.get(q) is None
        ]

        if critical_missing:
            log(f"   🔍 CRITICAL SIGNALS MISSING: {', '.join(critical_missing)} - must continue searching")
            if total_pages < min_pages:
                log(f"   🔄 Continuing deep scan ({total_pages}/{min_pages} min pages)")
            else:
                log(f"   🔄 Continuing exhaustive search ({total_pages}/{max_pages} max pages)")
            continue  # Force continue - don't allow early exit

        if total_pages >= min_pages:
            # Now we can check early exit conditions (only if no critical signals missing)
            if qualification.get('sufficient', False):
                log(f"   ✅ Now sufficient (after {total_pages} pages) - stopping iteration")
                break

            if not current_low_conf:
                log(f"   ✅ All questions now have HIGH confidence (after {total_pages} pages)")
                break

            if not qualification.get('needs_more_pages', True):
                log(f"   ✅ No more pages needed (after {total_pages} pages)")
                break
        else:
            # Below min_pages - continue regardless of LLM opinion
            log(f"   🔄 Continuing deep scan ({total_pages}/{min_pages} min pages)")

        if current_low_conf:
            log(f"   → Still need info on: {', '.join(current_low_conf)}")

    # ─────────────────────────────────────────────────────────
    # FINAL RESULT
    # ─────────────────────────────────────────────────────────
    result.success = True
    # GPT-5-mini sometimes puts classification in answers.primary_category instead of final_classification
    result.classification = (
        (qualification.get('final_classification') if qualification else None) or
        current_answers.get('primary_category')
    )
    result.disqualification_reason = qualification.get('disqualification_reason') if qualification else None
    result.answers = current_answers
    result.confidence = current_confidence
    result.products_found = qualification.get('products_found') if qualification else None
    result.evidence = qualification.get('evidence') if qualification else None
    result.pages_scraped = len(scraped_urls)
    result.scraped_urls = scraped_urls
    result.duration_ms = int((time.time() - start_time) * 1000)
    result.retry_stats = retry_stats

    log(f"\n{'='*60}")
    log(f"🏁 L2 COMPLETE")
    log(f"{'='*60}")
    log(f"   Classification: {result.classification}")
    log(f"   Pages Scraped: {result.pages_scraped}")
    log(f"   Iterations: {result.iterations}")
    log(f"   Credits Used: {result.credits_used}")
    log(f"   Duration: {result.duration_ms}ms")

    return result


# ═══════════════════════════════════════════════════════════════
# CLI ENTRY POINT
# ═══════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("L2 is designed to be called from the main pipeline after L1.")
    print("Use pipeline.py for the full flow.")
