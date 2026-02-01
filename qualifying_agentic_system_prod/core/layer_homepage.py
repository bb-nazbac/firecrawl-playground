#!/usr/bin/env python3
"""
L1: Homepage Scrape + Initial Qualification Layer

This layer:
1. Scrapes the homepage (1 credit)
2. Asks Claude if the homepage has sufficient information
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

from core.markdown_cleaner import strip_markdown

SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════

MAX_RETRIES = 7
INITIAL_RETRY_DELAY = 0.1  # Reduced by 90% (was 1.0)
MAX_RETRY_DELAY = 3.0      # Reduced by 90% (was 30.0)
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
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')

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
class AnalysisSpec:
    """Loaded analysis specification"""
    spec_name: str
    client_description: str
    categories: List[Dict]
    questions: List[Dict]
    classification_logic: Dict
    critical_questions: List[str]

    @classmethod
    def load(cls, spec_path: Path) -> 'AnalysisSpec':
        """Load spec from JSON file"""
        with open(spec_path) as f:
            data = json.load(f)

        return cls(
            spec_name=data.get('spec_name', 'unknown'),
            client_description=data.get('client', {}).get('who_we_target', ''),
            categories=data.get('categories', []),
            questions=data.get('questions', []),
            classification_logic=data.get('classification_logic', {}),
            critical_questions=data.get('iteration_logic', {}).get('critical_questions', [])
        )


# ═══════════════════════════════════════════════════════════════
# RETRY UTILITIES
# ═══════════════════════════════════════════════════════════════

def calculate_retry_delay(attempt: int) -> float:
    """Calculate delay for retry with exponential backoff."""
    delay = INITIAL_RETRY_DELAY * (RETRY_BACKOFF_FACTOR ** attempt)
    return min(delay, MAX_RETRY_DELAY)


def classify_error(error: Exception, response=None) -> Tuple[str, bool]:
    """Classify an error and determine if it's retryable."""
    error_str = str(error).lower()

    if 'timeout' in error_str or 'timed out' in error_str:
        return 'timeout', True
    if 'connection' in error_str:
        return 'connection_error', True
    if response and response.status_code == 429:
        return 'rate_limit', True
    if '429' in error_str or 'rate limit' in error_str:
        return 'rate_limit', True
    if response and 500 <= response.status_code < 600:
        return f'http_{response.status_code}', True
    if response and 400 <= response.status_code < 500:
        return f'http_{response.status_code}', False

    return 'unknown', True


# ═══════════════════════════════════════════════════════════════
# FIRECRAWL SCRAPE
# ═══════════════════════════════════════════════════════════════

def scrape_homepage(
    domain: str,
    semaphore: threading.Semaphore = None,
    timeout: int = 30000,
    request_timeout: int = 60,
    log_callback=None
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
                    log(f"   ⏳ Timeout, retrying in {delay:.1f}s")
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
# CLAUDE API
# ═══════════════════════════════════════════════════════════════

def call_claude(
    prompt: str,
    semaphore: threading.Semaphore = None,
    model: str = "claude-haiku-4-5-20251001",
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

    def log(msg):
        if log_callback:
            log_callback(msg)

    # Use semaphore if provided
    sem = semaphore or threading.Semaphore(30)

    with sem:
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
                    log(f"   ⏳ Claude rate limited, waiting {delay:.1f}s")
                    stats["retries"] += 1
                    time.sleep(delay)
                    continue

                if response.status_code == 529:
                    delay = calculate_retry_delay(attempt)
                    log(f"   ⏳ Claude overloaded, waiting {delay:.1f}s")
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
                    log(f"   ⏳ Claude timeout, retrying in {delay:.1f}s")
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
# WATERFALL FILTER PROMPT (CHEAP - PHASE 1)
# ═══════════════════════════════════════════════════════════════

def build_filter_prompt(domain: str, homepage_content: str) -> str:
    """
    Build a SHORT prompt to check only sells_products and is_b2b.
    This is the first phase of the waterfall - cheap and fast.
    """
    return f"""Analyze this company homepage and answer TWO questions:

DOMAIN: {domain}

HOMEPAGE CONTENT:
{homepage_content[:4000]}

QUESTIONS:
1. sells_products: Does this company SELL chemical/technical products (has product catalog, product pages, products listed)?
   Or do they ONLY provide services/software/logistics/equipment/testing/contract manufacturing?

2. is_b2b: Is this company B2B/wholesale/industrial (sells to businesses)?
   Or retail/DTC consumer-focused only?

Respond in this exact JSON format:
{{
    "sells_products": "YES/NO/UNKNOWN",
    "is_b2b": "YES/NO/UNKNOWN",
    "confidence_sells": "HIGH/MEDIUM/LOW",
    "confidence_b2b": "HIGH/MEDIUM/LOW",
    "evidence": "one sentence of evidence"
}}

Be decisive. If clearly a service company or retail brand, say NO."""


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

    # Build answer options
    answer_fields = {}
    confidence_fields = {}
    for q in spec.questions:
        field = q['field']
        if q.get('answer_type') == 'enum':
            answer_fields[field] = f"one of: {', '.join(q.get('answer_options', []))}"
        elif q.get('answer_type') == 'array':
            answer_fields[field] = "array of strings"
        else:
            answer_fields[field] = "string"
        confidence_fields[field] = "HIGH/MEDIUM/LOW/INSUFFICIENT"

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
    "disqualification_reason": "COMMODITY_ONLY/NOT_PRODUCT_SELLER/RETAIL_ONLY/BROKER_ONLY or null",
    "answers": {{
        "sells_products": "YES/NO/UNKNOWN",
        "is_b2b": "YES/NO/UNKNOWN",
        "has_inventory_or_manufacturing": "YES/NO/UNKNOWN",
        "product_type": "SPECIALTY/COMMODITY/MIXED/NOT_CHEMICAL_PRODUCTS/UNKNOWN",
        "primary_category": "PHARMA/ENGINEERED_MATERIALS/CHEMICAL/OTHER_TECHNICAL/NOT_APPLICABLE"
    }},
    "confidence": {{
        "sells_products": "HIGH/MEDIUM/LOW/INSUFFICIENT",
        "is_b2b": "HIGH/MEDIUM/LOW/INSUFFICIENT",
        "has_inventory_or_manufacturing": "HIGH/MEDIUM/LOW/INSUFFICIENT",
        "product_type": "HIGH/MEDIUM/LOW/INSUFFICIENT",
        "primary_category": "HIGH/MEDIUM/LOW/INSUFFICIENT"
    }},
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
    """Parse Claude's homepage qualification response."""
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
    claude_model: str = "claude-haiku-4-5-20251001",
    firecrawl_semaphore: threading.Semaphore = None,
    claude_semaphore: threading.Semaphore = None,
    log_callback=None,
    use_waterfall: bool = True  # Enable/disable waterfall filter
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
        claude_model: Claude model to use
        firecrawl_semaphore: Semaphore for Firecrawl rate limiting
        claude_semaphore: Semaphore for Claude rate limiting
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
    retry_stats = {"scrape": 0, "claude_filter": 0, "claude_full": 0}

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
        domain, semaphore=firecrawl_semaphore, log_callback=log
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
    # STEP 2: WATERFALL FILTER (CHEAP - Phase 1)
    # ─────────────────────────────────────────────────────────
    if use_waterfall:
        log(f"\n📍 Step 2: Waterfall filter (sells_products? is_b2b?)...")

        filter_prompt = build_filter_prompt(domain, content)

        filter_success, filter_response, f_in, f_out, filter_error, filter_stats = call_claude(
            filter_prompt, semaphore=claude_semaphore, model=claude_model, max_tokens=300, log_callback=log
        )
        result.tokens_used += f_in + f_out
        result.input_tokens += f_in
        result.output_tokens += f_out
        retry_stats["claude_filter"] = filter_stats.get("retries", 0)

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
            result.filter_passed = True  # Assume pass if we can't parse
        else:
            sells = filter_result.get('sells_products', 'UNKNOWN')
            b2b = filter_result.get('is_b2b', 'UNKNOWN')
            evidence = filter_result.get('evidence', '')

            log(f"   sells_products: {sells}, is_b2b: {b2b}")

            # FILTER DECISION: If clearly NO to either, disqualify early
            if sells == 'NO':
                log(f"🚫 FILTERED OUT: Does not sell products")
                result.success = True
                result.sufficient = True
                result.filtered_early = True
                result.filter_passed = False
                result.classification = "DISQUALIFIED"
                result.disqualification_reason = "NOT_PRODUCT_SELLER"
                result.answers = {
                    'sells_products': 'NO',
                    'is_b2b': b2b,
                    'has_inventory_or_manufacturing': 'UNKNOWN',
                    'product_type': 'UNKNOWN',
                    'primary_category': 'NOT_APPLICABLE'
                }
                result.confidence = {
                    'sells_products': filter_result.get('confidence_sells', 'HIGH'),
                    'is_b2b': filter_result.get('confidence_b2b', 'MEDIUM'),
                    'has_inventory_or_manufacturing': 'INSUFFICIENT',
                    'product_type': 'INSUFFICIENT',
                    'primary_category': 'INSUFFICIENT'
                }
                result.evidence = [{"url": "homepage", "excerpt": evidence, "supports_question": "sells_products"}]
                result.duration_ms = int((time.time() - start_time) * 1000)
                result.retry_stats = retry_stats
                return result

            if b2b == 'NO':
                log(f"🚫 FILTERED OUT: Not B2B (retail/DTC only)")
                result.success = True
                result.sufficient = True
                result.filtered_early = True
                result.filter_passed = False
                result.classification = "DISQUALIFIED"
                result.disqualification_reason = "RETAIL_ONLY"
                result.answers = {
                    'sells_products': sells,
                    'is_b2b': 'NO',
                    'has_inventory_or_manufacturing': 'UNKNOWN',
                    'product_type': 'UNKNOWN',
                    'primary_category': 'NOT_APPLICABLE'
                }
                result.confidence = {
                    'sells_products': filter_result.get('confidence_sells', 'MEDIUM'),
                    'is_b2b': filter_result.get('confidence_b2b', 'HIGH'),
                    'has_inventory_or_manufacturing': 'INSUFFICIENT',
                    'product_type': 'INSUFFICIENT',
                    'primary_category': 'INSUFFICIENT'
                }
                result.evidence = [{"url": "homepage", "excerpt": evidence, "supports_question": "is_b2b"}]
                result.duration_ms = int((time.time() - start_time) * 1000)
                result.retry_stats = retry_stats
                return result

            # Filter passed - continue to full qualification
            result.filter_passed = True
            log(f"✅ Filter passed, proceeding to full qualification...")

    # ─────────────────────────────────────────────────────────
    # STEP 3: FULL QUALIFICATION (Phase 2)
    # ─────────────────────────────────────────────────────────
    step_num = 3 if use_waterfall else 2
    log(f"\n📍 Step {step_num}: Full qualification check...")

    prompt = build_homepage_qualification_prompt(domain, content, spec)

    claude_success, response_text, in_tokens, out_tokens, claude_error, claude_stats = call_claude(
        prompt, semaphore=claude_semaphore, model=claude_model, log_callback=log
    )
    result.tokens_used += in_tokens + out_tokens
    result.input_tokens += in_tokens
    result.output_tokens += out_tokens
    retry_stats["claude_full"] = claude_stats.get("retries", 0)

    if not claude_success:
        result.error = f"Claude failed: {claude_error}"
        result.duration_ms = int((time.time() - start_time) * 1000)
        result.retry_stats = retry_stats
        log(f"❌ Claude failed: {claude_error}")
        return result

    # Parse response
    qualification = parse_homepage_response(response_text)
    if not qualification:
        result.error = "Failed to parse Claude response"
        result.duration_ms = int((time.time() - start_time) * 1000)
        result.retry_stats = retry_stats
        log(f"❌ Failed to parse response")
        return result

    # ─────────────────────────────────────────────────────────
    # STEP 4: DETERMINE SUFFICIENCY
    # ─────────────────────────────────────────────────────────
    result.success = True
    result.sufficient = qualification.get('sufficient', False)
    result.classification = qualification.get('final_classification')
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

    parser = argparse.ArgumentParser(description='L1: Homepage qualification')
    parser.add_argument('domain', help='Domain to analyze')
    parser.add_argument('--spec', default=str(ROOT_DIR / 'configs/specs/analysis/poka_labs_chemical_qualification_v2.json'),
                        help='Path to analysis spec')
    parser.add_argument('--model', default='claude-haiku-4-5-20251001', help='Claude model')

    args = parser.parse_args()

    if not FIRECRAWL_API_KEY:
        print("❌ FIRECRAWL_API_KEY not found")
        sys.exit(1)
    if not ANTHROPIC_API_KEY:
        print("❌ ANTHROPIC_API_KEY not found")
        sys.exit(1)

    spec = AnalysisSpec.load(Path(args.spec))
    result = process_homepage(args.domain, spec, args.model)

    print(f"\n{'='*60}")
    print("RESULT:")
    print(json.dumps(asdict(result), indent=2, default=str))
