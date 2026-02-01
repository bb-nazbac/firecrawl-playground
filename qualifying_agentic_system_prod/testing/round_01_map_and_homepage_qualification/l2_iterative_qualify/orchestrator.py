#!/usr/bin/env python3
"""
L2 Iterative Qualification - Orchestrator

Main orchestration logic for qualifying a single company domain.
Implements the iterative flow with comprehensive retry logic and diagnostics.

Following OPTIMUS PRIME Protocol v2.0
"""

import os
import sys
import json
import time
import requests
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List
from dataclasses import dataclass, field, asdict

# Add parent paths for imports
SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent.parent.parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(ROOT_DIR))

from prompts import (
    build_initial_qualification_prompt,
    build_page_selection_prompt,
    build_requalification_prompt,
    parse_qualification_response,
    parse_page_selection_response,
    get_low_confidence_questions,
    get_high_confidence_questions,
    should_continue_iteration,
    is_low_confidence
)

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════

OUTPUT_DIR = SCRIPT_DIR.parent / "outputs" / "qualification_results"
LOG_DIR = SCRIPT_DIR.parent / "logs" / "l2_iterative_qualify"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Retry configuration
MAX_RETRIES = 7  # Balanced for production
INITIAL_RETRY_DELAY = 1.0  # seconds
MAX_RETRY_DELAY = 30.0  # seconds
RETRY_BACKOFF_FACTOR = 2.0

# Rate limiting for Firecrawl API
import threading
MAP_SEMAPHORE = threading.Semaphore(5)   # Very low for /v2/map - very strict rate limits
SCRAPE_SEMAPHORE = threading.Semaphore(50)  # Higher for /v2/scrape - generous limits

# ═══════════════════════════════════════════════════════════════
# ENVIRONMENT
# ═══════════════════════════════════════════════════════════════

def load_env():
    """Load environment variables from .env file"""
    for env_path in [ROOT_DIR / ".env", ROOT_DIR.parent / ".env"]:
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        os.environ.setdefault(key.strip(), value.strip())
            break

load_env()

FIRECRAWL_API_KEY = os.environ.get('FIRECRAWL_API_KEY')
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')

# ═══════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════

@dataclass
class QualificationConfig:
    """Configuration for qualification run"""
    max_pages: int = 11
    pages_per_round: int = 5
    max_iterations: int = 2
    map_limit: int = 5000
    claude_model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 2000
    scrape_timeout: int = 30000
    request_timeout: int = 60  # Restored to 60 with semaphore protection
    critical_questions: list = field(default_factory=lambda: [
        "sells_products", "product_type", "primary_category"
    ])


@dataclass
class QualificationResult:
    """Result of qualifying a single domain"""
    domain: str
    success: bool
    final_classification: Optional[str] = None
    disqualification_reason: Optional[str] = None
    answers: Optional[dict] = None
    confidence: Optional[dict] = None
    products_found: Optional[list] = None
    evidence: Optional[list] = None
    pages_scraped: int = 0
    iterations: int = 0
    total_cost_credits: float = 0
    total_tokens: int = 0
    duration_ms: int = 0
    error: Optional[str] = None
    # New: detailed step logs
    step_log: Optional[List[Dict]] = None
    retry_stats: Optional[Dict] = None


# ═══════════════════════════════════════════════════════════════
# ERROR CLASSIFICATION
# ═══════════════════════════════════════════════════════════════

def classify_error(error: Exception, response: Optional[requests.Response] = None) -> Tuple[str, bool]:
    """
    Classify an error and determine if it's retryable.

    Returns:
        Tuple of (error_type, can_retry)
    """
    error_str = str(error).lower()

    # Timeout errors - retryable
    if 'timeout' in error_str or 'timed out' in error_str:
        return 'timeout', True

    # Connection errors - retryable
    if 'connection' in error_str or 'connectionerror' in error_str:
        return 'connection_error', True

    # Rate limiting - retryable
    if response and response.status_code == 429:
        return 'rate_limit', True
    if '429' in error_str or 'rate limit' in error_str:
        return 'rate_limit', True

    # Server errors - retryable
    if response and 500 <= response.status_code < 600:
        return f'http_{response.status_code}', True

    # Client errors - not retryable
    if response and 400 <= response.status_code < 500:
        return f'http_{response.status_code}', False

    # Parse errors - not retryable
    if 'json' in error_str or 'parse' in error_str or 'decode' in error_str:
        return 'parse_error', False

    # Default - attempt retry
    return 'unknown', True


def calculate_retry_delay(attempt: int) -> float:
    """Calculate delay for retry with exponential backoff."""
    delay = INITIAL_RETRY_DELAY * (RETRY_BACKOFF_FACTOR ** attempt)
    return min(delay, MAX_RETRY_DELAY)


# ═══════════════════════════════════════════════════════════════
# FIRECRAWL API WITH RETRY
# ═══════════════════════════════════════════════════════════════

def firecrawl_map(
    domain: str,
    limit: int = 100,  # Reduced from 5000 to minimize API load
    timeout: int = 60,
    log_callback=None
) -> Tuple[bool, list, str, Dict]:
    """
    Map a domain using Firecrawl /v2/map endpoint with retry logic.
    Uses semaphore to limit concurrent MAP calls (stricter rate limit than scrape).

    Returns:
        Tuple of (success, urls_list, error_message, stats)
    """
    url = f"https://{domain}" if not domain.startswith("http") else domain
    stats = {"attempts": 0, "retries": 0, "duration_seconds": 0}
    start_time = time.time()

    # Acquire semaphore to limit concurrent MAP calls
    with MAP_SEMAPHORE:
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
                    # Rate limited - retry with backoff
                    delay = calculate_retry_delay(attempt)
                    if log_callback:
                        log_callback(f"   ⏳ Rate limited, waiting {delay:.1f}s (attempt {attempt + 1}/{MAX_RETRIES})")
                    stats["retries"] += 1
                    time.sleep(delay)
                    continue

                data = response.json()

                if data.get('success'):
                    links = data.get('links', [])
                    if links and isinstance(links[0], dict):
                        links = [link.get('url', '') for link in links]
                    stats["duration_seconds"] = time.time() - start_time
                    return True, links, None, stats
                else:
                    error = data.get('error', 'Unknown API error')
                    error_type, can_retry = classify_error(Exception(error), response)

                    if can_retry and attempt < MAX_RETRIES - 1:
                        delay = calculate_retry_delay(attempt)
                        if log_callback:
                            log_callback(f"   ⏳ {error_type}: {error}, retrying in {delay:.1f}s")
                        stats["retries"] += 1
                        time.sleep(delay)
                        continue

                    stats["duration_seconds"] = time.time() - start_time
                    return False, [], error, stats

            except requests.exceptions.Timeout:
                if attempt < MAX_RETRIES - 1:
                    delay = calculate_retry_delay(attempt)
                    if log_callback:
                        log_callback(f"   ⏳ Timeout, retrying in {delay:.1f}s (attempt {attempt + 1}/{MAX_RETRIES})")
                    stats["retries"] += 1
                    time.sleep(delay)
                    continue

                stats["duration_seconds"] = time.time() - start_time
                return False, [], f"Timeout after {MAX_RETRIES} attempts", stats

            except Exception as e:
                error_type, can_retry = classify_error(e)

                if can_retry and attempt < MAX_RETRIES - 1:
                    delay = calculate_retry_delay(attempt)
                    if log_callback:
                        log_callback(f"   ⏳ {error_type}: {e}, retrying in {delay:.1f}s")
                    stats["retries"] += 1
                    time.sleep(delay)
                    continue

                stats["duration_seconds"] = time.time() - start_time
                return False, [], str(e), stats

        stats["duration_seconds"] = time.time() - start_time
        return False, [], "Max retries exceeded", stats


def firecrawl_scrape(
    url: str,
    timeout: int = 30000,
    request_timeout: int = 60,
    log_callback=None
) -> Tuple[bool, str, str, Dict]:
    """
    Scrape a URL using Firecrawl /v2/scrape endpoint with retry logic.
    Uses semaphore to limit concurrent SCRAPE calls (can handle 50 concurrent).

    Returns:
        Tuple of (success, markdown_content, error_message, stats)
    """
    stats = {"attempts": 0, "retries": 0, "duration_seconds": 0}
    start_time = time.time()

    with SCRAPE_SEMAPHORE:
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
                    if log_callback:
                        log_callback(f"   ⏳ Rate limited, waiting {delay:.1f}s")
                    stats["retries"] += 1
                    time.sleep(delay)
                    continue

                data = response.json()

                if data.get('success'):
                    markdown = data.get('data', {}).get('markdown', '')
                    stats["duration_seconds"] = time.time() - start_time
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
                    return False, '', error, stats

            except requests.exceptions.Timeout:
                if attempt < MAX_RETRIES - 1:
                    delay = calculate_retry_delay(attempt)
                    if log_callback:
                        log_callback(f"   ⏳ Timeout, retrying in {delay:.1f}s")
                    stats["retries"] += 1
                    time.sleep(delay)
                    continue

                stats["duration_seconds"] = time.time() - start_time
                return False, '', f"Timeout after {MAX_RETRIES} attempts", stats

            except Exception as e:
                error_type, can_retry = classify_error(e)

                if can_retry and attempt < MAX_RETRIES - 1:
                    delay = calculate_retry_delay(attempt)
                    stats["retries"] += 1
                    time.sleep(delay)
                    continue

                stats["duration_seconds"] = time.time() - start_time
                return False, '', str(e), stats

        stats["duration_seconds"] = time.time() - start_time
        return False, '', "Max retries exceeded", stats


# ═══════════════════════════════════════════════════════════════
# CLAUDE API WITH RETRY
# ═══════════════════════════════════════════════════════════════

def call_claude(
    prompt: str,
    model: str = "claude-sonnet-4-20250514",
    max_tokens: int = 2000,
    timeout: int = 120,
    log_callback=None
) -> Tuple[bool, str, int, int, str, Dict]:
    """
    Call Claude API with retry logic.

    Returns:
        Tuple of (success, response_text, input_tokens, output_tokens, error_message, stats)
    """
    stats = {"attempts": 0, "retries": 0, "duration_seconds": 0}
    start_time = time.time()

    for attempt in range(MAX_RETRIES):
        stats["attempts"] = attempt + 1

        try:
            response = requests.post(
                'https://api.anthropic.com/v1/messages',
                headers={
                    'x-api-key': ANTHROPIC_API_KEY,
                    'anthropic-version': '2023-06-01',
                    'content-type': 'application/json'
                },
                json={
                    'model': model,
                    'max_tokens': max_tokens,
                    'temperature': 0,
                    'messages': [{'role': 'user', 'content': prompt}]
                },
                timeout=timeout
            )

            if response.status_code == 429:
                delay = calculate_retry_delay(attempt)
                if log_callback:
                    log_callback(f"   ⏳ Claude rate limited, waiting {delay:.1f}s")
                stats["retries"] += 1
                time.sleep(delay)
                continue

            if response.status_code == 529:  # Overloaded
                delay = calculate_retry_delay(attempt)
                if log_callback:
                    log_callback(f"   ⏳ Claude overloaded, waiting {delay:.1f}s")
                stats["retries"] += 1
                time.sleep(delay)
                continue

            data = response.json()

            if 'content' in data:
                text = data['content'][0]['text']
                input_tokens = data.get('usage', {}).get('input_tokens', 0)
                output_tokens = data.get('usage', {}).get('output_tokens', 0)
                stats["duration_seconds"] = time.time() - start_time
                return True, text, input_tokens, output_tokens, None, stats
            else:
                error = data.get('error', {}).get('message', 'Unknown error')
                error_type, can_retry = classify_error(Exception(error), response)

                if can_retry and attempt < MAX_RETRIES - 1:
                    delay = calculate_retry_delay(attempt)
                    stats["retries"] += 1
                    time.sleep(delay)
                    continue

                stats["duration_seconds"] = time.time() - start_time
                return False, '', 0, 0, error, stats

        except requests.exceptions.Timeout:
            if attempt < MAX_RETRIES - 1:
                delay = calculate_retry_delay(attempt)
                if log_callback:
                    log_callback(f"   ⏳ Claude timeout, retrying in {delay:.1f}s")
                stats["retries"] += 1
                time.sleep(delay)
                continue

            stats["duration_seconds"] = time.time() - start_time
            return False, '', 0, 0, f"Timeout after {MAX_RETRIES} attempts", stats

        except Exception as e:
            error_type, can_retry = classify_error(e)

            if can_retry and attempt < MAX_RETRIES - 1:
                delay = calculate_retry_delay(attempt)
                stats["retries"] += 1
                time.sleep(delay)
                continue

            stats["duration_seconds"] = time.time() - start_time
            return False, '', 0, 0, str(e), stats

    stats["duration_seconds"] = time.time() - start_time
    return False, '', 0, 0, "Max retries exceeded", stats


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
        url_lower = url.lower()

        if url in already_scraped_set:
            continue

        if any(pattern in url_lower for pattern in IGNORE_PATTERNS):
            continue

        filtered.append(url)

    return filtered


def get_homepage_url(domain: str) -> str:
    """Get homepage URL for a domain"""
    if domain.startswith('http'):
        return domain
    return f"https://{domain}"


# ═══════════════════════════════════════════════════════════════
# MAIN ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════

def qualify_domain(
    domain: str,
    config: QualificationConfig = None,
    log_callback=None,
    diagnostics_manager=None
) -> QualificationResult:
    """
    Qualify a single domain using iterative approach with full retry logic.

    Args:
        domain: Company domain to qualify
        config: Qualification configuration
        log_callback: Optional callback for logging
        diagnostics_manager: Optional DiagnosticsManager for detailed tracking

    Returns:
        QualificationResult with classification and metadata
    """
    if config is None:
        config = QualificationConfig()

    def log(msg):
        if log_callback:
            log_callback(msg)
        print(msg)

    start_time = time.time()
    result = QualificationResult(domain=domain, success=False)

    # Step log for detailed tracking
    step_log = []
    retry_stats = {"map": 0, "scrape": 0, "claude": 0}

    # Track state
    scraped_urls = []
    scraped_content = {}
    site_map = []
    total_tokens = 0
    credits_used = 0

    # Start domain tracking
    if diagnostics_manager:
        diagnostics_manager.domain_diag.start_domain(domain)

    log(f"\n{'='*60}")
    log(f"🔬 QUALIFYING: {domain}")
    log(f"{'='*60}")

    # ─────────────────────────────────────────────────────────
    # STEP 1: MAP THE SITE
    # ─────────────────────────────────────────────────────────
    log(f"\n📍 Step 1: Mapping site...")
    step_start = time.time()

    map_success, site_map, map_error, map_stats = firecrawl_map(
        domain, config.map_limit, config.request_timeout, log
    )
    credits_used += 1
    retry_stats["map"] = map_stats.get("retries", 0)

    step_log.append({
        "step": "map",
        "success": map_success,
        "duration_seconds": time.time() - step_start,
        "urls_found": len(site_map) if map_success else 0,
        "retries": map_stats.get("retries", 0),
        "error": map_error
    })

    if diagnostics_manager:
        if map_success:
            diagnostics_manager.map_diag.record_success(
                domain, map_stats["duration_seconds"],
                retry_count=map_stats.get("retries", 0)
            )
        else:
            error_type, can_retry = classify_error(Exception(map_error or ""))
            diagnostics_manager.map_diag.record_failure(
                domain, error_type, map_error or "Unknown",
                map_stats["duration_seconds"],
                retry_count=map_stats.get("retries", 0),
                can_retry=can_retry
            )
        diagnostics_manager.map_diag.record_api_call(credits=1)
        diagnostics_manager.domain_diag.record_step(
            domain, "map", map_success, map_stats["duration_seconds"],
            credits=1, details={"urls_found": len(site_map)}
        )

    if not map_success:
        result.error = f"Map failed: {map_error}"
        result.duration_ms = int((time.time() - start_time) * 1000)
        result.total_cost_credits = credits_used
        result.step_log = step_log
        result.retry_stats = retry_stats
        log(f"❌ Map failed after {map_stats['attempts']} attempts: {map_error}")

        if diagnostics_manager:
            diagnostics_manager.domain_diag.complete_domain(
                domain, "ERROR", False, result.error
            )

        return result

    log(f"✅ Found {len(site_map)} URLs (retries: {map_stats.get('retries', 0)})")

    # Filter map URLs
    filtered_map = filter_map_urls(site_map)
    log(f"   Filtered to {len(filtered_map)} relevant URLs")

    # ─────────────────────────────────────────────────────────
    # STEP 2: SCRAPE HOMEPAGE
    # ─────────────────────────────────────────────────────────
    log(f"\n📍 Step 2: Scraping homepage...")
    step_start = time.time()

    homepage_url = get_homepage_url(domain)
    scrape_success, homepage_content, scrape_error, scrape_stats = firecrawl_scrape(
        homepage_url, config.scrape_timeout, config.request_timeout, log
    )
    credits_used += 1
    retry_stats["scrape"] += scrape_stats.get("retries", 0)

    step_log.append({
        "step": "scrape_homepage",
        "url": homepage_url,
        "success": scrape_success,
        "duration_seconds": time.time() - step_start,
        "content_length": len(homepage_content) if scrape_success else 0,
        "retries": scrape_stats.get("retries", 0),
        "error": scrape_error
    })

    if diagnostics_manager:
        if scrape_success:
            diagnostics_manager.scrape_diag.record_success(
                homepage_url, scrape_stats["duration_seconds"],
                retry_count=scrape_stats.get("retries", 0)
            )
        else:
            error_type, can_retry = classify_error(Exception(scrape_error or ""))
            diagnostics_manager.scrape_diag.record_failure(
                homepage_url, error_type, scrape_error or "Unknown",
                scrape_stats["duration_seconds"],
                retry_count=scrape_stats.get("retries", 0),
                can_retry=can_retry
            )
        diagnostics_manager.scrape_diag.record_api_call(credits=1)
        diagnostics_manager.domain_diag.record_step(
            domain, "scrape_homepage", scrape_success,
            scrape_stats["duration_seconds"], credits=1,
            details={"content_length": len(homepage_content) if scrape_success else 0}
        )

    if not scrape_success:
        result.error = f"Homepage scrape failed: {scrape_error}"
        result.duration_ms = int((time.time() - start_time) * 1000)
        result.total_cost_credits = credits_used
        result.step_log = step_log
        result.retry_stats = retry_stats
        log(f"❌ Scrape failed after {scrape_stats['attempts']} attempts: {scrape_error}")

        if diagnostics_manager:
            diagnostics_manager.domain_diag.complete_domain(
                domain, "ERROR", False, result.error
            )

        return result

    scraped_urls.append(homepage_url)
    scraped_content[homepage_url] = homepage_content
    log(f"✅ Scraped homepage ({len(homepage_content)} chars, retries: {scrape_stats.get('retries', 0)})")

    # ─────────────────────────────────────────────────────────
    # STEP 3: INITIAL QUALIFICATION
    # ─────────────────────────────────────────────────────────
    log(f"\n📍 Step 3: Initial qualification with Claude...")
    step_start = time.time()

    initial_prompt = build_initial_qualification_prompt(
        domain=domain,
        page_content=homepage_content,
        url=homepage_url
    )

    claude_success, response_text, in_tokens, out_tokens, claude_error, claude_stats = call_claude(
        initial_prompt, config.claude_model, config.max_tokens, log_callback=log
    )
    total_tokens += in_tokens + out_tokens
    retry_stats["claude"] += claude_stats.get("retries", 0)

    step_log.append({
        "step": "classify_initial",
        "success": claude_success,
        "duration_seconds": time.time() - step_start,
        "tokens_in": in_tokens,
        "tokens_out": out_tokens,
        "retries": claude_stats.get("retries", 0),
        "error": claude_error
    })

    if diagnostics_manager:
        if claude_success:
            diagnostics_manager.classify_diag.record_success(
                domain, claude_stats["duration_seconds"],
                retry_count=claude_stats.get("retries", 0)
            )
        else:
            error_type, can_retry = classify_error(Exception(claude_error or ""))
            diagnostics_manager.classify_diag.record_failure(
                domain, error_type, claude_error or "Unknown",
                claude_stats["duration_seconds"],
                retry_count=claude_stats.get("retries", 0),
                can_retry=can_retry
            )
        diagnostics_manager.classify_diag.record_api_call(
            tokens_in=in_tokens, tokens_out=out_tokens
        )
        diagnostics_manager.domain_diag.record_step(
            domain, "classify_initial", claude_success,
            claude_stats["duration_seconds"], tokens=in_tokens + out_tokens
        )

    if not claude_success:
        result.error = f"Claude failed: {claude_error}"
        result.duration_ms = int((time.time() - start_time) * 1000)
        result.total_cost_credits = credits_used
        result.total_tokens = total_tokens
        result.step_log = step_log
        result.retry_stats = retry_stats
        log(f"❌ Claude failed after {claude_stats['attempts']} attempts: {claude_error}")

        if diagnostics_manager:
            diagnostics_manager.domain_diag.complete_domain(
                domain, "ERROR", False, result.error
            )

        return result

    qualification = parse_qualification_response(response_text)
    if not qualification:
        result.error = "Failed to parse Claude response"
        result.duration_ms = int((time.time() - start_time) * 1000)
        result.total_cost_credits = credits_used
        result.total_tokens = total_tokens
        result.step_log = step_log
        result.retry_stats = retry_stats
        log(f"❌ Failed to parse response")

        if diagnostics_manager:
            diagnostics_manager.domain_diag.complete_domain(
                domain, "ERROR", False, result.error
            )

        return result

    log(f"✅ Initial classification: {qualification.get('final_classification')}")
    log(f"   Confidence: {qualification.get('confidence')}")
    log(f"   Needs more pages: {qualification.get('needs_more_pages')}")

    # ─────────────────────────────────────────────────────────
    # STEP 4: ITERATIVE REFINEMENT (if needed)
    # ─────────────────────────────────────────────────────────
    current_qualification = qualification
    iteration = 0

    while should_continue_iteration(
        current_qualification.get('confidence', {}),
        current_qualification.get('needs_more_pages', False),
        iteration,
        config.max_iterations,
        config.critical_questions
    ):
        iteration += 1
        log(f"\n📍 Iteration {iteration}: Need more information...")

        # Check page budget
        pages_remaining = config.max_pages - len(scraped_urls)
        if pages_remaining <= 0:
            log(f"   ⚠️ Page budget exhausted")
            break

        pages_to_select = min(config.pages_per_round, pages_remaining)

        # Get low and high confidence questions
        confidence = current_qualification.get('confidence', {})
        answers = current_qualification.get('answers', {})

        low_conf = {}
        for q, c in confidence.items():
            if is_low_confidence(c):
                low_conf[q] = {'confidence': c, 'answer': answers.get(q)}

        high_conf = {}
        for q, c in confidence.items():
            if c == 'HIGH':
                high_conf[q] = {'confidence': c, 'answer': answers.get(q)}

        # ─────────────────────────────────────────────────────
        # 4a: SELECT PAGES FROM MAP
        # ─────────────────────────────────────────────────────
        log(f"   Selecting {pages_to_select} pages from map...")
        step_start = time.time()

        selection_prompt = build_page_selection_prompt(
            domain=domain,
            high_confidence_questions=high_conf,
            low_confidence_questions=low_conf,
            suggested_page_types=current_qualification.get('suggested_page_types', []),
            already_scraped_urls=scraped_urls,
            site_map_urls=filter_map_urls(filtered_map, scraped_urls),
            max_pages=pages_to_select
        )

        sel_success, sel_response, sel_in, sel_out, sel_error, sel_stats = call_claude(
            selection_prompt, config.claude_model, 1000, log_callback=log
        )
        total_tokens += sel_in + sel_out
        retry_stats["claude"] += sel_stats.get("retries", 0)

        step_log.append({
            "step": f"select_pages_iter{iteration}",
            "success": sel_success,
            "duration_seconds": time.time() - step_start,
            "tokens_in": sel_in,
            "tokens_out": sel_out,
            "retries": sel_stats.get("retries", 0),
            "error": sel_error
        })

        if not sel_success:
            log(f"   ⚠️ Page selection failed after {sel_stats['attempts']} attempts: {sel_error}")
            break

        selection = parse_page_selection_response(sel_response)
        if not selection or not selection.get('selected_urls'):
            log(f"   ⚠️ No pages selected")
            break

        selected_urls = [u['url'] for u in selection['selected_urls']]
        log(f"   Selected: {selected_urls}")

        # ─────────────────────────────────────────────────────
        # 4b: SCRAPE SELECTED PAGES
        # ─────────────────────────────────────────────────────
        log(f"   Scraping {len(selected_urls)} pages...")
        new_content = []

        for url in selected_urls:
            scrape_ok, content, scrape_err, s_stats = firecrawl_scrape(
                url, config.scrape_timeout, config.request_timeout, log
            )
            credits_used += 1
            retry_stats["scrape"] += s_stats.get("retries", 0)

            if scrape_ok and content:
                scraped_urls.append(url)
                scraped_content[url] = content
                new_content.append(f"=== PAGE: {url} ===\n{content}")
                log(f"   ✅ {url} ({len(content)} chars)")
            else:
                log(f"   ⚠️ {url} failed: {scrape_err}")

        step_log.append({
            "step": f"scrape_iter{iteration}",
            "urls_attempted": len(selected_urls),
            "urls_scraped": len(new_content),
            "credits_used": len(selected_urls)
        })

        if not new_content:
            log(f"   ⚠️ No new content scraped")
            break

        # ─────────────────────────────────────────────────────
        # 4c: RE-QUALIFY WITH ALL CONTENT
        # ─────────────────────────────────────────────────────
        log(f"   Re-qualifying with {len(scraped_urls)} total pages...")
        step_start = time.time()

        all_content = "\n\n".join([
            f"=== PAGE: {url} ===\n{scraped_content[url]}"
            for url in scraped_urls
        ])

        questions_to_reevaluate = [q for q, c in confidence.items() if c != 'HIGH']

        requalify_prompt = build_requalification_prompt(
            domain=domain,
            locked_answers=high_conf,
            questions_to_reevaluate=questions_to_reevaluate,
            all_page_content=all_content
        )

        req_success, req_response, req_in, req_out, req_error, req_stats = call_claude(
            requalify_prompt, config.claude_model, config.max_tokens, log_callback=log
        )
        total_tokens += req_in + req_out
        retry_stats["claude"] += req_stats.get("retries", 0)

        step_log.append({
            "step": f"requalify_iter{iteration}",
            "success": req_success,
            "duration_seconds": time.time() - step_start,
            "tokens_in": req_in,
            "tokens_out": req_out,
            "retries": req_stats.get("retries", 0),
            "error": req_error
        })

        if not req_success:
            log(f"   ⚠️ Re-qualification failed: {req_error}")
            break

        new_qualification = parse_qualification_response(req_response)
        if not new_qualification:
            log(f"   ⚠️ Failed to parse re-qualification response")
            break

        current_qualification = new_qualification
        log(f"   ✅ Updated classification: {current_qualification.get('final_classification')}")
        log(f"   Confidence: {current_qualification.get('confidence')}")

    # ─────────────────────────────────────────────────────────
    # FINAL RESULT
    # ─────────────────────────────────────────────────────────
    result.success = True
    result.final_classification = current_qualification.get('final_classification')
    result.disqualification_reason = current_qualification.get('disqualification_reason')
    result.answers = current_qualification.get('answers')
    result.confidence = current_qualification.get('confidence')
    result.products_found = current_qualification.get('products_found')
    result.evidence = current_qualification.get('evidence')
    result.pages_scraped = len(scraped_urls)
    result.iterations = iteration
    result.total_cost_credits = credits_used
    result.total_tokens = total_tokens
    result.duration_ms = int((time.time() - start_time) * 1000)
    result.step_log = step_log
    result.retry_stats = retry_stats

    if diagnostics_manager:
        diagnostics_manager.domain_diag.complete_domain(
            domain, result.final_classification or "UNKNOWN", True
        )

    log(f"\n{'='*60}")
    log(f"🏁 QUALIFICATION COMPLETE")
    log(f"{'='*60}")
    log(f"   Domain: {domain}")
    log(f"   Classification: {result.final_classification}")
    log(f"   Disqualification Reason: {result.disqualification_reason}")
    log(f"   Pages Scraped: {result.pages_scraped}")
    log(f"   Iterations: {result.iterations}")
    log(f"   Credits Used: {result.total_cost_credits}")
    log(f"   Tokens Used: {result.total_tokens}")
    log(f"   Duration: {result.duration_ms}ms")
    log(f"   Retries: Map={retry_stats['map']}, Scrape={retry_stats['scrape']}, Claude={retry_stats['claude']}")

    return result


# ═══════════════════════════════════════════════════════════════
# CLI ENTRY POINT
# ═══════════════════════════════════════════════════════════════

def main():
    import argparse

    parser = argparse.ArgumentParser(description='Qualify a company domain')
    parser.add_argument('domain', help='Domain to qualify')
    parser.add_argument('--max-pages', type=int, default=11, help='Max pages per domain')
    parser.add_argument('--max-iterations', type=int, default=2, help='Max iteration rounds')
    parser.add_argument('--model', default='claude-sonnet-4-20250514', help='Claude model')
    parser.add_argument('--output', '-o', help='Output JSON file')

    args = parser.parse_args()

    # Check API keys
    if not FIRECRAWL_API_KEY:
        print("❌ FIRECRAWL_API_KEY not found")
        sys.exit(1)
    if not ANTHROPIC_API_KEY:
        print("❌ ANTHROPIC_API_KEY not found")
        sys.exit(1)

    config = QualificationConfig(
        max_pages=args.max_pages,
        max_iterations=args.max_iterations,
        claude_model=args.model
    )

    result = qualify_domain(args.domain, config)

    # Save result
    if args.output:
        output_path = Path(args.output)
    else:
        safe_domain = args.domain.replace('.', '_').replace('/', '_')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = OUTPUT_DIR / f"{safe_domain}_{timestamp}.json"

    with open(output_path, 'w') as f:
        json.dump(asdict(result), f, indent=2)

    print(f"\n📄 Result saved to: {output_path}")


if __name__ == '__main__':
    main()
