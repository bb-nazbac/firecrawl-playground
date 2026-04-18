#!/usr/bin/env python3
"""
L1: Homepage Scrape + Initial Qualification Layer (OpenAI Version)

This layer:
1. Scrapes the homepage (1 credit)
2. Asks GPT if the homepage has sufficient information
3. Returns qualification result OR signals need for deeper analysis

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

from core_openai.markdown_cleaner import strip_markdown
from core_openai.logger import get_logger

SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════

MAX_RETRIES = 10  # Default max, but error-specific limits take precedence
MAX_RETRIES_DETERMINISTIC = 1  # For errors that won't resolve (SSL, DNS, connection refused)
MAX_RETRIES_TIMEOUT = 2  # For timeout errors (ERR_TIMED_OUT)
MAX_RETRIES_TRANSIENT = 3  # For potentially transient errors (tunnel, empty response)
INITIAL_RETRY_DELAY = 0.5  # Slightly longer initial delay for rate limits
MAX_RETRY_DELAY = 30.0     # Allow longer waits for rate limit recovery
RETRY_BACKOFF_FACTOR = 2.0

# Semaphores for rate limiting - will be set by pipeline
SCRAPE_SEMAPHORE = threading.Semaphore(50)

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
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')

# ═══════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════

@dataclass
class HomepageResult:
    """Result from L1 homepage analysis"""
    domain: str
    success: bool

    # Homepage scrape results
    homepage_url: str = None
    homepage_content: str = None
    homepage_summary: str = None  # Summary for L2 re-qualification (~100 tokens)
    homepage_scraped: bool = False

    # Waterfall filter results (Phase 1)
    filter_passed: Optional[bool] = None  # None = not run, True = passed, False = filtered out
    filtered_early: bool = False  # True if disqualified by filter (no full qualification run)

    # Classification results (if sufficient)
    sufficient: bool = False
    classification: Optional[str] = None
    disqualification_reason: Optional[str] = None
    answers: Optional[Dict] = None
    confidence: Optional[Dict] = None
    products_found: Optional[List] = None
    evidence: Optional[List] = None

    # For insufficient cases - what to look for
    suggested_page_types: Optional[List[str]] = None
    low_confidence_questions: Optional[List[str]] = None

    # Metrics
    credits_used: int = 0
    tokens_used: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0
    error: Optional[str] = None
    retry_stats: Dict = field(default_factory=dict)


@dataclass
class WaterfallFilterConfig:
    """Configuration for waterfall filter from spec"""
    enabled: bool
    questions: List[Dict]
    disqualify_rules: List[Dict]
    output_schema: Dict
    closing_instruction: str

    @classmethod
    def from_dict(cls, data: Dict) -> 'WaterfallFilterConfig':
        """Create from spec waterfall_filter dict"""
        return cls(
            enabled=data.get('enabled', False),
            questions=data.get('questions', []),
            disqualify_rules=data.get('disqualify_rules', []),
            output_schema=data.get('output_schema', {}),
            closing_instruction=data.get('closing_instruction', '')
        )


@dataclass
class AnalysisSpec:
    """Loaded analysis specification"""
    spec_name: str
    client_description: str
    categories: List[Dict]
    questions: List[Dict]
    classification_logic: Dict
    critical_questions: List[str]
    waterfall_filter: Optional[WaterfallFilterConfig] = None
    disqualification_rules: List[Dict] = field(default_factory=list)

    @classmethod
    def load(cls, spec_path: Path) -> 'AnalysisSpec':
        """Load spec from JSON file"""
        with open(spec_path) as f:
            data = json.load(f)

        # Load waterfall filter config if present
        waterfall_data = data.get('waterfall_filter')
        waterfall_config = WaterfallFilterConfig.from_dict(waterfall_data) if waterfall_data else None

        return cls(
            spec_name=data.get('spec_name', 'unknown'),
            client_description=data.get('client', {}).get('who_we_target', ''),
            categories=data.get('categories', []),
            questions=data.get('questions', []),
            classification_logic=data.get('classification_logic', {}),
            critical_questions=data.get('iteration_logic', {}).get('critical_questions', []),
            waterfall_filter=waterfall_config,
            disqualification_rules=data.get('disqualification_rules', [])
        )


# ═══════════════════════════════════════════════════════════════
# RETRY UTILITIES
# ═══════════════════════════════════════════════════════════════

def calculate_retry_delay(attempt: int) -> float:
    """Calculate delay for retry with exponential backoff."""
    delay = INITIAL_RETRY_DELAY * (RETRY_BACKOFF_FACTOR ** attempt)
    return min(delay, MAX_RETRY_DELAY)


def classify_error(error: Exception, response=None) -> Tuple[str, bool, int]:
    """
    Classify an error and determine if it's retryable + max retries allowed.

    Returns:
        Tuple of (error_type, can_retry, max_retries)
    """
    error_str = str(error).lower()

    # ===== DETERMINISTIC FAILURES (fail fast, 1 retry max) =====
    # SSL/TLS errors - certificate problems won't fix themselves
    if 'ssl error' in error_str or 'ssl_error' in error_str or 'certificate' in error_str:
        return 'ssl_error', True, MAX_RETRIES_DETERMINISTIC

    # DNS failures - domain doesn't exist
    if 'dns resolution failed' in error_str or 'name resolution' in error_str:
        return 'dns_error', False, 0  # No retries, domain is gone

    # Connection refused - server actively blocking
    if 'err_connection_refused' in error_str or 'connection refused' in error_str:
        return 'connection_refused', True, MAX_RETRIES_DETERMINISTIC

    # Connection reset - server dropped connection
    if 'err_connection_reset' in error_str or 'connection reset' in error_str:
        return 'connection_reset', True, MAX_RETRIES_DETERMINISTIC

    # Invalid URL format
    if 'valid url' in error_str or 'valid top-level domain' in error_str:
        return 'invalid_url', False, 0  # No retries, bad input

    # Website not supported by Firecrawl
    if 'not currently supported' in error_str:
        return 'unsupported_site', False, 0  # No retries, won't work

    # All scraping engines failed - Firecrawl gave up
    if 'all scraping engines failed' in error_str:
        return 'all_engines_failed', True, MAX_RETRIES_DETERMINISTIC

    # ===== TIMEOUT ERRORS (2 retries) =====
    if 'err_timed_out' in error_str:
        return 'browser_timeout', True, MAX_RETRIES_TIMEOUT

    if 'timeout' in error_str or 'timed out' in error_str:
        return 'timeout', True, MAX_RETRIES_TIMEOUT

    # ===== TRANSIENT ERRORS (3 retries) =====
    # Tunnel/proxy issues - often transient
    if 'err_tunnel_connection_failed' in error_str or 'tunnel' in error_str:
        return 'tunnel_error', True, MAX_RETRIES_TRANSIENT

    # Empty response - server hiccup
    if 'err_empty_response' in error_str or 'empty response' in error_str:
        return 'empty_response', True, MAX_RETRIES_TRANSIENT

    # HTTP/2 protocol errors - often transient
    if 'err_http2' in error_str or 'http2' in error_str:
        return 'http2_error', True, MAX_RETRIES_TRANSIENT

    # ===== RATE LIMITS (keep high retries for these) =====
    if response and response.status_code == 429:
        return 'rate_limit', True, MAX_RETRIES
    if '429' in error_str or 'rate limit' in error_str:
        return 'rate_limit', True, MAX_RETRIES

    # ===== HTTP ERRORS =====
    if response and 500 <= response.status_code < 600:
        return f'http_{response.status_code}', True, MAX_RETRIES_TRANSIENT
    if response and 400 <= response.status_code < 500:
        return f'http_{response.status_code}', False, 0

    # Generic connection errors - try a few times
    if 'connection' in error_str:
        return 'connection_error', True, MAX_RETRIES_TRANSIENT

    return 'unknown', True, MAX_RETRIES_TRANSIENT


# ═══════════════════════════════════════════════════════════════
# FIRECRAWL SCRAPE
# ═══════════════════════════════════════════════════════════════

def scrape_homepage(
    domain: str,
    semaphore: threading.Semaphore = None,
    timeout: int = 30000,
    request_timeout: int = 60,
    log_callback=None,
    analytics=None  # Optional PipelineAnalytics for tracking
) -> Tuple[bool, str, str, Dict]:
    """
    Scrape homepage using Firecrawl /v2/scrape endpoint.

    Returns:
        Tuple of (success, markdown_content, error_message, stats)
    """
    url = f"https://{domain}" if not domain.startswith("http") else domain
    stats = {"attempts": 0, "retries": 0, "duration_seconds": 0}
    start_time = time.time()

    sem = semaphore or SCRAPE_SEMAPHORE

    def log(msg):
        if log_callback:
            log_callback(msg)

    # Track analytics - start
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
                    # Track analytics - end (success)
                    if analytics:
                        analytics.firecrawl_end(stats["duration_seconds"] * 1000, error=False)
                    return True, markdown, None, stats
                else:
                    error = data.get('error', 'Unknown API error')
                    error_type, can_retry, max_retries_for_error = classify_error(Exception(error), response)

                    if can_retry and attempt < max_retries_for_error:
                        delay = calculate_retry_delay(attempt)
                        stats["retries"] += 1
                        time.sleep(delay)
                        continue

                    stats["duration_seconds"] = time.time() - start_time
                    # Track analytics - end (error)
                    if analytics:
                        analytics.firecrawl_end(stats["duration_seconds"] * 1000, error=True)
                    return False, '', error, stats

            except requests.exceptions.Timeout:
                # Use timeout-specific retry limit
                if attempt < MAX_RETRIES_TIMEOUT:
                    delay = calculate_retry_delay(attempt)
                    log(f"   ⏳ Timeout, retrying in {delay:.1f}s")
                    stats["retries"] += 1
                    time.sleep(delay)
                    continue

                stats["duration_seconds"] = time.time() - start_time
                # Track analytics - end (timeout error)
                if analytics:
                    analytics.firecrawl_end(stats["duration_seconds"] * 1000, error=True)
                return False, '', f"Timeout after {attempt + 1} attempts", stats

            except Exception as e:
                error_type, can_retry, max_retries_for_error = classify_error(e)

                if can_retry and attempt < max_retries_for_error:
                    delay = calculate_retry_delay(attempt)
                    stats["retries"] += 1
                    time.sleep(delay)
                    continue

                stats["duration_seconds"] = time.time() - start_time
                # Track analytics - end (exception error)
                if analytics:
                    analytics.firecrawl_end(stats["duration_seconds"] * 1000, error=True)
                return False, '', str(e), stats

    stats["duration_seconds"] = time.time() - start_time
    # Track analytics - end (max retries)
    if analytics:
        analytics.firecrawl_end(stats["duration_seconds"] * 1000, error=True)
    return False, '', "Max retries exceeded", stats


# ═══════════════════════════════════════════════════════════════
# OPENAI API
# ═══════════════════════════════════════════════════════════════

def call_openai(
    prompt: str,
    semaphore: threading.Semaphore = None,
    model: str = "gpt-5-mini",
    max_tokens: int = 2000,
    timeout: int = 120,
    log_callback=None,
    json_mode: bool = True,  # Enable JSON mode by default for structured output
    analytics=None  # Optional PipelineAnalytics for tracking
) -> Tuple[bool, str, int, int, str, Dict]:
    """
    Call OpenAI API with retry logic.

    Returns:
        Tuple of (success, response_text, input_tokens, output_tokens, error_message, stats)
    """
    stats = {"attempts": 0, "retries": 0, "duration_seconds": 0}
    start_time = time.time()

    def log(msg):
        if log_callback:
            log_callback(msg)

    # Use semaphore if provided
    sem = semaphore or threading.Semaphore(30)

    # Track analytics - start
    if analytics:
        analytics.openai_start()

    with sem:
        for attempt in range(MAX_RETRIES):
            stats["attempts"] = attempt + 1

            try:
                # Build request payload
                payload = {
                    'model': model,
                    'max_completion_tokens': max_tokens,
                    'messages': [{'role': 'user', 'content': prompt}]
                }

                # Add JSON mode for structured output (guarantees valid JSON)
                if json_mode:
                    payload['response_format'] = {'type': 'json_object'}

                # reasoning_effort defaults to 'medium' which gives best accuracy
                # Tested 'minimal' but it reduced accuracy by 4.4% and increased Firecrawl usage by 83%

                response = requests.post(
                    'https://api.openai.com/v1/chat/completions',
                    headers={
                        'Authorization': f'Bearer {OPENAI_API_KEY}',
                        'Content-Type': 'application/json'
                    },
                    json=payload,
                    timeout=timeout
                )

                if response.status_code == 429:
                    delay = calculate_retry_delay(attempt)
                    log(f"   ⏳ OpenAI rate limited, waiting {delay:.1f}s")
                    stats["retries"] += 1
                    # Track rate limit hit in analytics (even though we'll retry)
                    if analytics:
                        analytics.record_rate_limit()
                    time.sleep(delay)
                    continue

                if response.status_code == 503:
                    delay = calculate_retry_delay(attempt)
                    log(f"   ⏳ OpenAI overloaded, waiting {delay:.1f}s")
                    stats["retries"] += 1
                    # Track overload hit in analytics (even though we'll retry)
                    if analytics:
                        analytics.record_overload()
                    time.sleep(delay)
                    continue

                data = response.json()

                if 'choices' in data:
                    text = data['choices'][0]['message']['content']
                    input_tokens = data.get('usage', {}).get('prompt_tokens', 0)
                    output_tokens = data.get('usage', {}).get('completion_tokens', 0)
                    stats["duration_seconds"] = time.time() - start_time
                    # Track analytics - end (success)
                    if analytics:
                        analytics.openai_end(stats["duration_seconds"] * 1000, error=False)
                    return True, text, input_tokens, output_tokens, None, stats
                else:
                    error = data.get('error', {}).get('message', 'Unknown error')
                    error_type, can_retry, max_retries_for_error = classify_error(Exception(error), response)

                    # OpenAI rate limits should use full retries
                    if can_retry and attempt < max_retries_for_error:
                        delay = calculate_retry_delay(attempt)
                        stats["retries"] += 1
                        time.sleep(delay)
                        continue

                    stats["duration_seconds"] = time.time() - start_time
                    # Track analytics - end (error)
                    if analytics:
                        analytics.openai_end(stats["duration_seconds"] * 1000, error=True)
                    return False, '', 0, 0, error, stats

            except requests.exceptions.Timeout:
                # OpenAI timeouts - use transient retry limit
                if attempt < MAX_RETRIES_TRANSIENT:
                    delay = calculate_retry_delay(attempt)
                    log(f"   ⏳ OpenAI timeout, retrying in {delay:.1f}s")
                    stats["retries"] += 1
                    time.sleep(delay)
                    continue

                stats["duration_seconds"] = time.time() - start_time
                # Track analytics - end (timeout error)
                if analytics:
                    analytics.openai_end(stats["duration_seconds"] * 1000, error=True)
                return False, '', 0, 0, f"Timeout after {attempt + 1} attempts", stats

            except Exception as e:
                error_type, can_retry, max_retries_for_error = classify_error(e)

                if can_retry and attempt < max_retries_for_error:
                    delay = calculate_retry_delay(attempt)
                    stats["retries"] += 1
                    time.sleep(delay)
                    continue

                stats["duration_seconds"] = time.time() - start_time
                # Track analytics - end (exception error)
                if analytics:
                    analytics.openai_end(stats["duration_seconds"] * 1000, error=True)
                return False, '', 0, 0, str(e), stats

    stats["duration_seconds"] = time.time() - start_time
    # Track analytics - end (max retries)
    if analytics:
        analytics.openai_end(stats["duration_seconds"] * 1000, error=True)
    return False, '', 0, 0, "Max retries exceeded", stats


# ═══════════════════════════════════════════════════════════════
# WATERFALL FILTER PROMPT (CHEAP - PHASE 1)
# ═══════════════════════════════════════════════════════════════

def build_filter_prompt(domain: str, homepage_content: str, filter_config: WaterfallFilterConfig) -> str:
    """
    Build a SHORT prompt dynamically from the spec's waterfall_filter config.
    This is the first phase of the waterfall - cheap and fast.
    """
    # Build questions section from spec
    questions_text = ""
    for i, q in enumerate(filter_config.questions, 1):
        questions_text += f"{i}. {q['field']}: {q['prompt']}\n\n"

    # Build output schema from spec
    output_fields = []
    for field, format_hint in filter_config.output_schema.items():
        output_fields.append(f'    "{field}": "{format_hint}"')
    output_schema_text = "{\n" + ",\n".join(output_fields) + "\n}"

    return f"""Analyze this company homepage and answer the following questions:

DOMAIN: {domain}

HOMEPAGE CONTENT:
{homepage_content[:4000]}

QUESTIONS:
{questions_text}
Respond in this exact JSON format:
{output_schema_text}

{filter_config.closing_instruction}"""


# ═══════════════════════════════════════════════════════════════
# HOMEPAGE QUALIFICATION PROMPT (SPEC-DRIVEN)
# ═══════════════════════════════════════════════════════════════

def build_homepage_qualification_prompt(domain: str, homepage_content: str, spec: AnalysisSpec) -> str:
    """Build prompt for homepage-only qualification using the analysis spec."""

    # Build categories description
    categories_text = "\n".join([
        f"- {cat['name']}: {cat['description']}"
        for cat in spec.categories
    ])

    # Build questions text
    questions_text = "\n".join([
        f"- {q['field']}: {q['question']}"
        for q in spec.questions
    ])

    # Build answer options - ALWAYS use answer_options if present, regardless of answer_type
    answer_fields = {}
    confidence_fields = {}
    for q in spec.questions:
        field = q['field']
        if q.get('answer_options'):
            # Use answer_options if present (for constrained string/enum fields)
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

    return f"""You are analyzing the homepage of a company website to determine if we can fully qualify this company, or if we need to scrape additional pages.

CLIENT CONTEXT: {spec.client_description}

COMPANY DOMAIN: {domain}

HOMEPAGE CONTENT:
{homepage_content[:8000]}

CATEGORIES:
{categories_text}

QUALIFICATION QUESTIONS:
{questions_text}

CRITICAL QUESTIONS (must have HIGH confidence to be sufficient):
{', '.join(spec.critical_questions)}

CLASSIFICATION LOGIC:
{json.dumps(spec.classification_logic.get('apply_in_order', []), indent=2)}

INSTRUCTIONS:
Analyze the homepage content and determine:
1. Can you answer ALL critical questions ({', '.join(spec.critical_questions)}) with HIGH confidence from the homepage alone?
2. If YES: Provide your classification and all answers
3. If NO: List which questions have LOW/MEDIUM confidence and what page types might help

Respond in this exact JSON format:
{{
    "sufficient": true/false,
    "company_name": "extracted company name",
    "final_classification": "one of: {', '.join([c['name'] for c in spec.categories])}",
    "disqualification_reason": "{disq_reasons_text}",
    "answers": {json.dumps(answer_fields, indent=8)},
    "confidence": {json.dumps(confidence_fields, indent=8)},
    "products_found": ["product1", "product2", "...up to 6"],
    "evidence": [
        {{"url": "homepage", "excerpt": "quote from content", "supports_question": "field_name"}}
    ],
    "suggested_page_types": ["Products", "About Us", "Services"],
    "low_confidence_questions": ["question1", "question2"],
    "homepage_summary": "1-2 sentence summary of company: what they do, products/services, target market"
}}

IMPORTANT:
- Set "sufficient": true ONLY if ALL critical questions have HIGH confidence
- Apply classification logic rules in order
- Be conservative - if unsure, mark as needs more info with sufficient: false
"""


def parse_homepage_response(response_text: str) -> Optional[Dict]:
    """Parse OpenAI's homepage qualification response."""
    import re

    try:
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            return json.loads(json_match.group())
    except json.JSONDecodeError:
        pass

    return None


# ═══════════════════════════════════════════════════════════════
# MAIN L1 FUNCTION (WATERFALL)
# ═══════════════════════════════════════════════════════════════

def process_homepage(
    domain: str,
    spec: AnalysisSpec,
    openai_model: str = "gpt-5-mini",
    firecrawl_semaphore: threading.Semaphore = None,
    openai_semaphore: threading.Semaphore = None,
    log_callback=None,
    use_waterfall: bool = True,  # Enable/disable waterfall filter
    analytics=None  # Optional PipelineAnalytics for tracking
) -> HomepageResult:
    """
    L1: Process homepage with WATERFALL approach.

    WATERFALL FLOW:
    1. Scrape homepage (1 credit)
    2. FILTER CHECK (cheap): sells_products? is_b2b?
       - If NO to either → DISQUALIFY immediately (save costs)
       - If YES to both → continue
    3. FULL QUALIFICATION (if filter passed)
    4. If insufficient → caller proceeds to L2

    Args:
        domain: Company domain to qualify
        spec: Analysis specification
        openai_model: OpenAI model to use
        firecrawl_semaphore: Semaphore for Firecrawl rate limiting
        openai_semaphore: Semaphore for OpenAI rate limiting
        log_callback: Optional callback for logging
        use_waterfall: If True, run filter first (default). If False, skip to full qualification.

    Returns:
        HomepageResult with qualification or need for more info
    """
    def log(msg):
        if log_callback:
            log_callback(msg)
        print(msg)

    start_time = time.time()
    result = HomepageResult(domain=domain, success=False)
    retry_stats = {"scrape": 0, "openai_filter": 0, "openai_full": 0}

    log(f"\n{'='*60}")
    log(f"🏠 L1: HOMEPAGE ANALYSIS - {domain}")
    log(f"{'='*60}")

    # ─────────────────────────────────────────────────────────
    # STEP 1: SCRAPE HOMEPAGE
    # ─────────────────────────────────────────────────────────
    log(f"\n📍 Step 1: Scraping homepage...")

    homepage_url = f"https://{domain}" if not domain.startswith("http") else domain
    result.homepage_url = homepage_url

    scrape_success, content, scrape_error, scrape_stats = scrape_homepage(
        domain, semaphore=firecrawl_semaphore, log_callback=log, analytics=analytics
    )
    result.credits_used += 1
    retry_stats["scrape"] = scrape_stats.get("retries", 0)

    if not scrape_success:
        result.error = f"Homepage scrape failed: {scrape_error}"
        result.duration_ms = int((time.time() - start_time) * 1000)
        result.retry_stats = retry_stats
        log(f"❌ Scrape failed: {scrape_error}")
        return result

    result.homepage_scraped = True
    result.homepage_content = content
    log(f"✅ Scraped homepage ({len(content)} chars)")

    # ─────────────────────────────────────────────────────────
    # STEP 2: WATERFALL FILTER (CHEAP - Phase 1) - SPEC-DRIVEN
    # ─────────────────────────────────────────────────────────
    # Check if waterfall filter is enabled in spec AND use_waterfall flag is True
    filter_config = spec.waterfall_filter
    run_waterfall = use_waterfall and filter_config and filter_config.enabled

    if run_waterfall:
        # Build question fields list for logging
        question_fields = [q['field'] for q in filter_config.questions]
        log(f"\n📍 Step 2: Waterfall filter ({', '.join(question_fields)})...")

        filter_prompt = build_filter_prompt(domain, content, filter_config)

        # GPT-5-mini is a reasoning model - needs higher token limits for reasoning phase
        filter_success, filter_response, f_in, f_out, filter_error, filter_stats = call_openai(
            filter_prompt, semaphore=openai_semaphore, model=openai_model, max_tokens=1500, log_callback=log, analytics=analytics
        )
        result.tokens_used += f_in + f_out
        result.input_tokens += f_in
        result.output_tokens += f_out
        retry_stats["openai_filter"] = filter_stats.get("retries", 0)

        if not filter_success:
            result.error = f"Filter check failed: {filter_error}"
            result.duration_ms = int((time.time() - start_time) * 1000)
            result.retry_stats = retry_stats
            log(f"❌ Filter failed: {filter_error}")
            return result

        # Parse filter response
        filter_result = parse_homepage_response(filter_response)
        if not filter_result:
            log(f"⚠️ Could not parse filter response, proceeding to full qualification")
            # Log the parse failure for debugging
            logger = get_logger()
            if logger:
                logger.log_parse_failure(domain, "filter", filter_response, "Failed to parse as JSON")
            result.filter_passed = True  # Assume pass if we can't parse
        else:
            # Log the filter responses
            for q in filter_config.questions:
                field = q['field']
                value = filter_result.get(field, 'UNKNOWN')
                log(f"   {field}: {value}")

            evidence = filter_result.get('evidence', '')

            # Apply disqualify_rules from spec
            disqualified = False
            for rule in filter_config.disqualify_rules:
                field = rule['if_field']
                expected_value = rule['equals']
                actual_value = filter_result.get(field, 'UNKNOWN')

                if actual_value == expected_value and rule.get('then_disqualify', False):
                    log_msg = rule.get('log_message', f'{field} = {expected_value}')
                    log(f"🚫 FILTERED OUT: {log_msg}")

                    result.success = True
                    result.sufficient = True
                    result.filtered_early = True
                    result.filter_passed = False
                    result.classification = "DISQUALIFIED"
                    result.disqualification_reason = rule['reason']

                    # Build answers from filter result
                    result.answers = {k: filter_result.get(k, 'UNKNOWN') for k in
                                     [q['field'] for q in filter_config.questions]}

                    # Build confidence from filter result (look for confidence_<field> keys)
                    result.confidence = {}
                    for q in filter_config.questions:
                        conf_key = f"confidence_{q['field'].split('_')[0]}"  # e.g. confidence_sells
                        result.confidence[q['field']] = filter_result.get(conf_key, 'MEDIUM')

                    result.evidence = [{"url": "homepage", "excerpt": evidence, "supports_question": field}]
                    result.duration_ms = int((time.time() - start_time) * 1000)
                    result.retry_stats = retry_stats
                    disqualified = True
                    return result

            # Filter passed - continue to full qualification
            if not disqualified:
                result.filter_passed = True
                log(f"✅ Filter passed, proceeding to full qualification...")

    # ─────────────────────────────────────────────────────────
    # STEP 3: FULL QUALIFICATION (Phase 2)
    # ─────────────────────────────────────────────────────────
    step_num = 3 if run_waterfall else 2
    log(f"\n📍 Step {step_num}: Full qualification check...")

    prompt = build_homepage_qualification_prompt(domain, content, spec)

    # GPT-5-mini is a reasoning model - needs higher token limits for reasoning phase
    # 4000 tokens gives room for ~2500 reasoning + ~1500 output
    openai_success, response_text, in_tokens, out_tokens, openai_error, openai_stats = call_openai(
        prompt, semaphore=openai_semaphore, model=openai_model, max_tokens=4000, log_callback=log, analytics=analytics
    )
    result.tokens_used += in_tokens + out_tokens
    result.input_tokens += in_tokens
    result.output_tokens += out_tokens
    retry_stats["openai_full"] = openai_stats.get("retries", 0)

    if not openai_success:
        result.error = f"OpenAI failed: {openai_error}"
        result.duration_ms = int((time.time() - start_time) * 1000)
        result.retry_stats = retry_stats
        log(f"❌ OpenAI failed: {openai_error}")
        return result

    # Parse response
    qualification = parse_homepage_response(response_text)
    if not qualification:
        result.error = "Failed to parse OpenAI response"
        result.duration_ms = int((time.time() - start_time) * 1000)
        result.retry_stats = retry_stats
        log(f"❌ Failed to parse response")
        # Log the parse failure for debugging
        logger = get_logger()
        if logger:
            logger.log_parse_failure(domain, "qualification", response_text, "Failed to parse as JSON")
        return result

    # ─────────────────────────────────────────────────────────
    # STEP 4: DETERMINE SUFFICIENCY
    # ─────────────────────────────────────────────────────────
    result.success = True
    result.sufficient = qualification.get('sufficient', False)
    # GPT-5-mini sometimes puts classification in answers.primary_category instead of final_classification
    result.classification = (
        qualification.get('final_classification') or
        qualification.get('answers', {}).get('primary_category')
    )
    result.disqualification_reason = qualification.get('disqualification_reason')
    result.answers = qualification.get('answers')
    result.confidence = qualification.get('confidence')
    result.products_found = qualification.get('products_found')
    result.evidence = qualification.get('evidence')
    result.suggested_page_types = qualification.get('suggested_page_types')
    result.low_confidence_questions = qualification.get('low_confidence_questions')
    result.homepage_summary = qualification.get('homepage_summary', '')
    result.duration_ms = int((time.time() - start_time) * 1000)
    result.retry_stats = retry_stats

    if result.sufficient:
        log(f"\n✅ SUFFICIENT - Homepage has enough information!")
        log(f"   Classification: {result.classification}")
    else:
        log(f"\n⚠️  INSUFFICIENT - Need to scrape more pages")
        log(f"   Low confidence: {result.low_confidence_questions}")
        log(f"   Suggested pages: {result.suggested_page_types}")

    log(f"\n📊 L1 Complete: {result.duration_ms}ms, {result.credits_used} credits, {result.tokens_used} tokens")

    return result


# ═══════════════════════════════════════════════════════════════
# CLI ENTRY POINT
# ═══════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import argparse
    from dataclasses import asdict

    parser = argparse.ArgumentParser(description='L1: Homepage qualification (OpenAI)')
    parser.add_argument('domain', help='Domain to analyze')
    parser.add_argument('--spec', default=str(ROOT_DIR / 'configs/specs/analysis/TEMPLATE.json'),
                        help='Path to analysis spec')
    parser.add_argument('--model', default='gpt-5-mini', help='OpenAI model')

    args = parser.parse_args()

    if not FIRECRAWL_API_KEY:
        print("❌ FIRECRAWL_API_KEY not found")
        sys.exit(1)
    if not OPENAI_API_KEY:
        print("❌ OPENAI_API_KEY not found")
        sys.exit(1)

    spec = AnalysisSpec.load(Path(args.spec))
    result = process_homepage(args.domain, spec, args.model)

    print(f"\n{'='*60}")
    print("RESULT:")
    print(json.dumps(asdict(result), indent=2, default=str))
