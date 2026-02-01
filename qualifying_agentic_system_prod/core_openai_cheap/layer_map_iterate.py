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

from core_openai.markdown_cleaner import strip_markdown

SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent

# Import from layer_homepage for shared utilities
from core_openai.layer_homepage import (
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

    return f"""Re-qualify {domain} for: {spec.client_description}

CURRENT ASSESSMENT:
{json.dumps(previous_answers)} | Confidence: {json.dumps(previous_confidence)}

CONTEXT:
{content_section}

Update answers based on new evidence. Classify as: {classification_options}.
{categories_text}
DISQUALIFY if evidence clearly disqualifies (reasons: {disq_reasons_text})

CRITICAL: Set "sufficient":true ONLY when ALL critical questions have HIGH confidence with definitive answers (YES or NO). If ANY critical question has UNKNOWN as the answer, you MUST set "sufficient":false to continue scraping more pages. UNKNOWN means we need more information.

JSON response:
{{"sufficient":bool,"company_name":"...","final_classification":"...","disqualification_reason":"{disq_reasons_text}","answers":{json.dumps(answer_fields)},"confidence":{json.dumps(confidence_fields)},"needs_more_pages":bool,"current_page_summary":"1 sentence"}}
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
    max_pages: int = 10,
    openai_model: str = "gpt-5-mini",
    firecrawl_semaphore: threading.Semaphore = None,
    openai_semaphore: threading.Semaphore = None,
    log_callback=None,
    analytics=None  # Optional PipelineAnalytics for tracking
) -> IterativeResult:
    """
    L2: Map site and SEQUENTIALLY scrape pages until confident.

    Only called when L1 (homepage) was insufficient.

    NEW APPROACH (Sequential Single-Page):
    - Selects ONE page at a time based on strict priority order
    - Scrapes it and re-qualifies with accumulated context
    - Stops as soon as we have sufficient confidence
    - More efficient than batch mode - often needs only 1-2 pages

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
        max_pages: Maximum additional pages to scrape (default 10)
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
        if not filtered_map:
            log(f"\n   ⚠️ No more pages available in site map")
            break

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
        sel_success, sel_response, sel_in, sel_out, sel_error, sel_stats = call_openai(
            selection_prompt, semaphore=openai_semaphore, model=openai_model, max_tokens=1500, log_callback=log, analytics=analytics
        )
        result.tokens_used += sel_in + sel_out
        result.input_tokens += sel_in
        result.output_tokens += sel_out
        retry_stats["openai"] += sel_stats.get("retries", 0)

        if not sel_success:
            log(f"   ⚠️ Page selection failed: {sel_error}")
            break

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
            log(f"   ⚠️ No page selected")
            break

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

        req_success, req_response, req_in, req_out, req_error, req_stats = call_openai(
            requalify_prompt, semaphore=openai_semaphore, model=openai_model, max_tokens=1500, log_callback=log, analytics=analytics
        )
        result.tokens_used += req_in + req_out
        result.input_tokens += req_in
        result.output_tokens += req_out
        retry_stats["openai"] += req_stats.get("retries", 0)

        if not req_success:
            log(f"   ⚠️ Re-qualification failed: {req_error}")
            break

        qualification = parse_json_response(req_response)
        if not qualification:
            log(f"   ⚠️ Failed to parse response")
            break

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

        # Check if we're now sufficient
        if qualification.get('sufficient', False):
            log(f"   ✅ Now sufficient - stopping iteration")
            break

        # Update low confidence questions for next selection
        current_low_conf = [
            q for q, c in current_confidence.items()
            if c in ['LOW', 'MEDIUM', 'INSUFFICIENT']
        ]

        if not current_low_conf:
            log(f"   ✅ All questions now have HIGH confidence")
            break

        if not qualification.get('needs_more_pages', True):
            log(f"   ✅ No more pages needed")
            break

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
