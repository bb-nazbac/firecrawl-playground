import json
import time
import re
import threading
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from stages.base import BaseStage

# Import core modules - they will be at core/ relative to project root
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.firecrawl_client import FirecrawlClient
from core.llm_provider import LLMProvider


@dataclass
class QualifyResult:
    domain: str
    success: bool
    path: str = "unknown"  # filtered_early, homepage_only, homepage_plus_iterate, url_direct
    filtered_early: bool = False
    company_name: Optional[str] = None
    classification: Optional[str] = None
    disqualification_reason: Optional[str] = None
    answers: Optional[Dict] = None
    confidence: Optional[Dict] = None
    products_found: Optional[List] = None
    evidence: Optional[List] = None
    pages_scraped: int = 0
    iterations: int = 0
    map_used: bool = False
    credits_used: int = 0
    tokens_used: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0
    error: Optional[str] = None


class QualifyStage(BaseStage):
    STAGE_NAME = "qualify"

    def __init__(self, config, spec, analytics, output, logger):
        super().__init__(config, spec, analytics, output, logger)

        model_name = config.get('model', 'claude-haiku-4-5-20251001')
        self.llm = LLMProvider.from_model(model_name)
        self.firecrawl = FirecrawlClient()

        fc_concurrency = config.get('firecrawl_concurrency', 45)
        llm_concurrency = config.get('llm_concurrency', 30)
        self.fc_semaphore = threading.Semaphore(fc_concurrency)
        self.llm_semaphore = threading.Semaphore(llm_concurrency)

        self.scrape_mode = config.get('scrape_mode', 'domain')
        self.use_waterfall = config.get('waterfall', True)
        self.max_pages = config.get('max_pages', 11)

        # CSV setup
        self._csv_initialized = False
        self._results_lock = threading.Lock()
        self.total_domains = 0
        self.processed = 0
        self.filtered_early = 0
        self.homepage_sufficient = 0
        self.needed_iteration = 0
        self.failed = 0

    def run(self, input_data) -> Dict:
        """
        input_data: dict with 'domains' key (list of domain dicts) or list of domain dicts
        """
        if isinstance(input_data, dict):
            domains = input_data.get('domains', [])
        elif isinstance(input_data, list):
            domains = input_data
        else:
            domains = []

        self.total_domains = len(domains)
        self.analytics.start_stage("qualify", total_items=self.total_domains)

        self.logger.info(f"Qualifying {self.total_domains} domains (mode={self.scrape_mode})")

        # Init CSV with spec-appropriate columns
        self._init_csv()

        # Process with thread pool
        num_workers = max(
            self.config.get('firecrawl_concurrency', 45),
            self.config.get('llm_concurrency', 30)
        )

        results = []
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = {}
            for d in domains:
                domain = d if isinstance(d, str) else d.get('domain', d.get('url', ''))
                url = d.get('url', '') if isinstance(d, dict) else ''
                future = executor.submit(self._process_domain, domain, url)
                futures[future] = domain

            for future in as_completed(futures):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    domain = futures[future]
                    self.logger.error(f"Error processing {domain}: {e}")

        self.analytics.complete_stage("qualify")

        self.logger.info(f"Qualify complete: {self.processed}/{self.total_domains}")
        self.logger.info(f"  Filtered early: {self.filtered_early}")
        self.logger.info(f"  Homepage sufficient: {self.homepage_sufficient}")
        self.logger.info(f"  Needed iteration: {self.needed_iteration}")
        self.logger.info(f"  Failed: {self.failed}")

        return {"results": results, "results_csv": str(self.output.output_dir / "results.csv")}

    def _process_domain(self, domain: str, url: str = '') -> QualifyResult:
        """Process a single domain through qualify pipeline."""
        start_time = time.time()

        if self.scrape_mode == 'url' and url:
            result = self._process_url_mode(domain, url)
        else:
            result = self._process_domain_mode(domain)

        result.duration_ms = int((time.time() - start_time) * 1000)

        # Record analytics
        with self._results_lock:
            self.processed += 1
            if not result.success:
                self.failed += 1
            elif result.filtered_early:
                self.filtered_early += 1
            elif result.path == "homepage_only":
                self.homepage_sufficient += 1
            else:
                self.needed_iteration += 1

            # Write result immediately
            self._write_result(result)

            # Progress
            pct = (self.processed / self.total_domains) * 100 if self.total_domains > 0 else 0
            self.logger.info(
                f"[{pct:.0f}%] {self.processed}/{self.total_domains} | "
                f"F:{self.filtered_early} HP:{self.homepage_sufficient} "
                f"It:{self.needed_iteration} Fail:{self.failed}"
            )

        # Record to analytics engine
        if result.success:
            self.analytics.increment_progress("qualify", completed=1)
            self.analytics.record_success("qualify", domain, result.duration_ms / 1000)
        else:
            self.analytics.increment_progress("qualify", failed=1)
            self.analytics.record_failure("qualify", domain, "qualify_error", result.error or "unknown", result.duration_ms / 1000)

        # Record API costs
        if result.credits_used > 0:
            self.analytics.record_api_cost("firecrawl", credits=result.credits_used)
        if result.input_tokens > 0 or result.output_tokens > 0:
            model = self.config.get('model', 'unknown')
            self.analytics.record_api_cost("llm", model=model, tokens_in=result.input_tokens, tokens_out=result.output_tokens)

        return result

    def _process_url_mode(self, domain: str, url: str) -> QualifyResult:
        """Scrape exact URL, run LLM once, done. For articles/news pages."""
        result = QualifyResult(domain=domain, success=False)

        # Scrape the URL
        success, content, error, stats = self.firecrawl.scrape(url, self.fc_semaphore)
        result.credits_used += 1
        result.pages_scraped = 1

        if not success:
            result.error = f"Scrape failed: {error}"
            return result

        # Run waterfall filter if enabled
        if self.use_waterfall and self.spec.waterfall_filter:
            filter_result = self._run_waterfall_filter(domain, content)
            result.input_tokens += filter_result.get('input_tokens', 0)
            result.output_tokens += filter_result.get('output_tokens', 0)
            result.tokens_used += filter_result.get('input_tokens', 0) + filter_result.get('output_tokens', 0)

            if filter_result.get('disqualified'):
                result.success = True
                result.path = "filtered_early"
                result.filtered_early = True
                result.classification = filter_result.get('classification', 'DISQUALIFIED')
                result.disqualification_reason = filter_result.get('reason')
                result.answers = filter_result.get('answers')
                return result

        # Full qualification
        qual_result = self._run_full_qualification(domain, content, url)
        result.input_tokens += qual_result.get('input_tokens', 0)
        result.output_tokens += qual_result.get('output_tokens', 0)
        result.tokens_used += qual_result.get('input_tokens', 0) + qual_result.get('output_tokens', 0)

        result.success = True
        result.path = "url_direct"
        result.classification = qual_result.get('classification')
        result.disqualification_reason = qual_result.get('disqualification_reason')
        result.answers = qual_result.get('answers')
        result.confidence = qual_result.get('confidence')
        result.products_found = qual_result.get('products_found')
        result.evidence = qual_result.get('evidence')
        result.company_name = qual_result.get('company_name')

        return result

    def _process_domain_mode(self, domain: str) -> QualifyResult:
        """Homepage-first qualification with optional map+iterate."""
        result = QualifyResult(domain=domain, success=False)

        # L1: Scrape homepage
        homepage_url = f"https://{domain}" if not domain.startswith("http") else domain
        success, content, error, stats = self.firecrawl.scrape(homepage_url, self.fc_semaphore)
        result.credits_used += 1
        result.pages_scraped = 1

        if not success:
            result.error = f"Homepage scrape failed: {error}"
            return result

        # Waterfall filter
        if self.use_waterfall and self.spec.waterfall_filter:
            filter_result = self._run_waterfall_filter(domain, content)
            result.input_tokens += filter_result.get('input_tokens', 0)
            result.output_tokens += filter_result.get('output_tokens', 0)
            result.tokens_used += filter_result.get('input_tokens', 0) + filter_result.get('output_tokens', 0)

            if filter_result.get('disqualified'):
                result.success = True
                result.path = "filtered_early"
                result.filtered_early = True
                result.classification = filter_result.get('classification', 'DISQUALIFIED')
                result.disqualification_reason = filter_result.get('reason')
                result.answers = filter_result.get('answers')
                return result

        # Full homepage qualification
        qual = self._run_full_qualification(domain, content, homepage_url)
        result.input_tokens += qual.get('input_tokens', 0)
        result.output_tokens += qual.get('output_tokens', 0)
        result.tokens_used += qual.get('input_tokens', 0) + qual.get('output_tokens', 0)

        if not qual.get('parsed'):
            result.error = "Failed to parse qualification response"
            return result

        # Check sufficiency
        if qual.get('sufficient', False):
            result.success = True
            result.path = "homepage_only"
            result.classification = qual.get('classification')
            result.disqualification_reason = qual.get('disqualification_reason')
            result.answers = qual.get('answers')
            result.confidence = qual.get('confidence')
            result.products_found = qual.get('products_found')
            result.evidence = qual.get('evidence')
            result.company_name = qual.get('company_name')
            return result

        # L2: Map + Iterate (if insufficient and max_pages > 1)
        if self.max_pages > 1:
            l2_result = self._run_iterative(
                domain, homepage_url, content,
                qual.get('homepage_summary', ''),
                qual.get('answers', {}),
                qual.get('confidence', {}),
                qual.get('low_confidence_questions', []),
                qual.get('suggested_page_types', [])
            )

            result.credits_used += l2_result.get('credits_used', 0)
            result.input_tokens += l2_result.get('input_tokens', 0)
            result.output_tokens += l2_result.get('output_tokens', 0)
            result.tokens_used += l2_result.get('input_tokens', 0) + l2_result.get('output_tokens', 0)
            result.pages_scraped += l2_result.get('pages_scraped', 0)
            result.iterations = l2_result.get('iterations', 0)
            result.map_used = True

            result.success = True
            result.path = "homepage_plus_iterate"
            result.classification = l2_result.get('classification') or qual.get('classification')
            result.disqualification_reason = l2_result.get('disqualification_reason')
            result.answers = l2_result.get('answers') or qual.get('answers')
            result.confidence = l2_result.get('confidence') or qual.get('confidence')
            result.products_found = l2_result.get('products_found')
            result.evidence = l2_result.get('evidence')
            result.company_name = l2_result.get('company_name')
        else:
            # No iteration - use homepage result as-is
            result.success = True
            result.path = "homepage_only"
            result.classification = qual.get('classification')
            result.disqualification_reason = qual.get('disqualification_reason')
            result.answers = qual.get('answers')
            result.confidence = qual.get('confidence')
            result.products_found = qual.get('products_found')
            result.evidence = qual.get('evidence')
            result.company_name = qual.get('company_name')

        return result

    def _run_waterfall_filter(self, domain: str, content: str) -> dict:
        """Run cheap waterfall filter from spec."""
        wf = self.spec.waterfall_filter
        questions = wf.get('questions', [])
        rules = wf.get('disqualify_rules', [])

        # Build filter prompt
        q_text = "\n".join([f"- {q['field']}: {q['prompt']}" for q in questions])
        output_schema = wf.get('output_schema', {})

        prompt = f"""Analyze this company homepage and answer these filter questions:

DOMAIN: {domain}

HOMEPAGE CONTENT:
{content[:4000]}

QUESTIONS:
{q_text}

Respond in JSON: {json.dumps(output_schema)}

Be decisive. If clearly not matching, say NO."""

        with self.llm_semaphore:
            response = self.llm.complete(prompt, max_tokens=300)

        result = {
            'input_tokens': response.input_tokens,
            'output_tokens': response.output_tokens,
            'disqualified': False,
        }

        if not response.success:
            return result

        parsed = self._parse_json(response.content)
        if not parsed:
            return result

        # Check disqualify rules
        for rule in rules:
            field = rule.get('if_field', '')
            equals = rule.get('equals', '')
            if parsed.get(field) == equals and rule.get('then_disqualify'):
                result['disqualified'] = True
                result['classification'] = 'DISQUALIFIED'
                result['reason'] = rule.get('reason', 'FILTERED')
                result['answers'] = parsed
                return result

        return result

    def _run_full_qualification(self, domain: str, content: str, url: str) -> dict:
        """Run full spec-driven qualification on content."""
        # Build prompt from spec
        categories_text = "\n".join([
            f"- {c.get('name', c.get('id', ''))}: {c.get('description', '')}"
            for c in self.spec.categories
        ])

        questions_text = "\n".join([
            f"- {q['field']}: {q['question']}"
            for q in self.spec.questions
        ])

        prompt = f"""Analyze this webpage to qualify the company.

DOMAIN: {domain}
URL: {url}

CONTENT:
{content[:8000]}

CATEGORIES:
{categories_text}

QUESTIONS:
{questions_text}

CLASSIFICATION LOGIC:
{json.dumps(self.spec.classification_logic.get('apply_in_order', []), indent=2) if self.spec.classification_logic else 'Apply based on answers'}

Respond in JSON:
{{
    "sufficient": true/false,
    "company_name": "...",
    "final_classification": "one of the categories",
    "disqualification_reason": "reason or null",
    "answers": {{...field: answer...}},
    "confidence": {{...field: "HIGH/MEDIUM/LOW/INSUFFICIENT"...}},
    "products_found": ["..."],
    "evidence": [{{"url": "...", "excerpt": "..."}}],
    "suggested_page_types": ["Products", "About"],
    "low_confidence_questions": ["field1"],
    "homepage_summary": "1-2 sentence summary"
}}

Set sufficient=true ONLY if all critical questions have HIGH confidence."""

        with self.llm_semaphore:
            response = self.llm.complete(prompt, max_tokens=2000)

        result = {
            'input_tokens': response.input_tokens,
            'output_tokens': response.output_tokens,
            'parsed': False,
        }

        if not response.success:
            result['error'] = response.error
            return result

        parsed = self._parse_json(response.content)
        if not parsed:
            return result

        result['parsed'] = True
        result['sufficient'] = parsed.get('sufficient', False)
        result['classification'] = parsed.get('final_classification')
        result['disqualification_reason'] = parsed.get('disqualification_reason')
        result['answers'] = parsed.get('answers')
        result['confidence'] = parsed.get('confidence')
        result['products_found'] = parsed.get('products_found')
        result['evidence'] = parsed.get('evidence')
        result['company_name'] = parsed.get('company_name')
        result['suggested_page_types'] = parsed.get('suggested_page_types')
        result['low_confidence_questions'] = parsed.get('low_confidence_questions')
        result['homepage_summary'] = parsed.get('homepage_summary', '')

        return result

    def _run_iterative(self, domain, homepage_url, homepage_content, homepage_summary,
                       prev_answers, prev_confidence, low_conf_questions, suggested_pages) -> dict:
        """L2: Map site and iteratively scrape pages until confident."""
        result = {
            'credits_used': 0, 'input_tokens': 0, 'output_tokens': 0,
            'pages_scraped': 0, 'iterations': 0,
        }

        # Map the site
        map_ok, site_map, map_err, map_stats = self.firecrawl.map(domain, self.fc_semaphore)
        result['credits_used'] += 1

        if not map_ok:
            return result

        # Filter URLs
        IGNORE = ['/login', '/privacy', '/terms', '/blog/', '/news/', '/careers/',
                  '/docs/', '/cart', '.pdf', '.jpg', '.png', '/search', '/tag/',
                  '/de/', '/fr/', '/es/', '/wp-content/']
        scraped = [homepage_url]
        filtered = [u for u in site_map if not any(p in u.lower() for p in IGNORE) and u not in scraped]

        current_answers = (prev_answers or {}).copy()
        current_confidence = (prev_confidence or {}).copy()
        current_low_conf = (low_conf_questions or []).copy()
        page_summaries = {}
        qualification = None

        max_additional = self.max_pages - 1
        pages_scraped = 0

        while pages_scraped < max_additional and filtered:
            result['iterations'] = pages_scraped + 1

            # Select page via LLM
            sel_prompt = f"""Select ONE page from {domain} to determine: {', '.join(current_low_conf or ['general qualification'])}

SCRAPED: {', '.join([u.split('/')[-1][:20] for u in scraped])}

URLS:
{chr(10).join(filtered[:50])}

JSON: {{"selected_url":{{"url":"...","reason":"...","page_type":"Products|About|Solutions"}}}}"""

            with self.llm_semaphore:
                sel_resp = self.llm.complete(sel_prompt, max_tokens=500)
            result['input_tokens'] += sel_resp.input_tokens
            result['output_tokens'] += sel_resp.output_tokens

            if not sel_resp.success:
                break

            sel = self._parse_json(sel_resp.content)
            selected_url = None
            if sel and sel.get('selected_url'):
                selected_url = sel['selected_url'].get('url')

            if not selected_url:
                break

            # Scrape selected page
            ok, content, err, s_stats = self.firecrawl.scrape(selected_url, self.fc_semaphore)
            result['credits_used'] += 1
            pages_scraped += 1
            result['pages_scraped'] = pages_scraped

            if not ok or not content:
                filtered = [u for u in filtered if u != selected_url]
                continue

            scraped.append(selected_url)
            filtered = [u for u in filtered if u not in scraped]

            # Re-qualify
            requalify_prompt = f"""Re-qualify {domain} based on new page content.

CURRENT: {json.dumps(current_answers)} | Confidence: {json.dumps(current_confidence)}

HOMEPAGE: {homepage_summary}
{''.join([f'[{u.split("/")[-1][:30]}]: {s}' + chr(10) for u, s in page_summaries.items()])}

=== NEW PAGE: {selected_url} ===
{content[:5000]}

Update answers. JSON: {{"sufficient":bool,"company_name":"...","final_classification":"...","disqualification_reason":"...or null","answers":{{...}},"confidence":{{...}},"products_found":[...],"needs_more_pages":bool,"current_page_summary":"..."}}"""

            with self.llm_semaphore:
                req_resp = self.llm.complete(requalify_prompt, max_tokens=2000)
            result['input_tokens'] += req_resp.input_tokens
            result['output_tokens'] += req_resp.output_tokens

            if not req_resp.success:
                break

            qualification = self._parse_json(req_resp.content)
            if not qualification:
                break

            # Store page summary
            summary = qualification.get('current_page_summary', content[:200] + '...')
            page_summaries[selected_url] = summary

            current_answers = qualification.get('answers', current_answers)
            current_confidence = qualification.get('confidence', current_confidence)

            if qualification.get('sufficient', False):
                break

            current_low_conf = [
                q for q, c in current_confidence.items()
                if c in ['LOW', 'MEDIUM', 'INSUFFICIENT']
            ]
            if not current_low_conf or not qualification.get('needs_more_pages', True):
                break

        if qualification:
            result['classification'] = qualification.get('final_classification')
            result['disqualification_reason'] = qualification.get('disqualification_reason')
            result['answers'] = current_answers
            result['confidence'] = current_confidence
            result['products_found'] = qualification.get('products_found')
            result['evidence'] = qualification.get('evidence')
            result['company_name'] = qualification.get('company_name')
        else:
            result['answers'] = current_answers
            result['confidence'] = current_confidence

        return result

    def _parse_json(self, text: str) -> Optional[dict]:
        """Parse JSON from LLM response."""
        try:
            match = re.search(r'\{[\s\S]*\}', text)
            if match:
                return json.loads(match.group())
        except (json.JSONDecodeError, AttributeError):
            pass
        return None

    def _init_csv(self):
        """Initialize CSV with headers based on spec."""
        base_fields = ['domain', 'success', 'path', 'classification', 'disqualification_reason']

        # Add answer fields from spec
        answer_fields = []
        if self.spec and self.spec.questions:
            for q in self.spec.questions:
                field = q.get('field', '')
                if field:
                    answer_fields.append(field)

        metric_fields = ['pages_scraped', 'map_used', 'credits_used', 'input_tokens', 'output_tokens', 'duration_ms', 'error']

        all_fields = base_fields + answer_fields + metric_fields
        self.output.init_results_csv(all_fields)
        self._csv_initialized = True

    def _write_result(self, result: QualifyResult):
        """Write a single result to output files."""
        row = {
            'domain': result.domain,
            'success': result.success,
            'path': result.path,
            'classification': result.classification,
            'disqualification_reason': result.disqualification_reason,
        }

        # Flatten answers
        if result.answers and isinstance(result.answers, dict):
            for k, v in result.answers.items():
                row[k] = v

        row.update({
            'pages_scraped': result.pages_scraped,
            'map_used': result.map_used,
            'credits_used': result.credits_used,
            'input_tokens': result.input_tokens,
            'output_tokens': result.output_tokens,
            'duration_ms': result.duration_ms,
            'error': result.error,
        })

        self.output.append_result(row)
