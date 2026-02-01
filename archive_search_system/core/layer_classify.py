"""
Layer 3: Classify Implementation

Integrates Claude API with production tracking systems and new spec format.
"""

import os
import json
from datetime import datetime
from typing import List, Dict, Any
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import anthropic


class ClassifyLayer:
    """
    Layer 3: Classify using Claude API

    Classifies scraped pages using analysis spec with concurrent processing.
    """

    def __init__(self, config, spec, progress, costs, diagnostics, logger, output_dir):
        """
        Initialize classify layer

        Args:
            config: RunConfig object
            spec: AnalysisSpec object
            progress: ProgressTracker instance
            costs: CostTracker instance
            diagnostics: DiagnosticsManager instance
            logger: Logger instance
            output_dir: Output directory path
        """
        self.config = config
        self.spec = spec
        self.progress = progress
        self.costs = costs
        self.diagnostics = diagnostics
        self.logger = logger
        self.output_dir = Path(output_dir)

        # Get API key
        api_key = os.getenv('ANTHROPIC_API_KEY')
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in environment variables")

        # Initialize Anthropic client
        self.anthropic = anthropic.Anthropic(api_key=api_key)

        # Setup layer diagnostics
        self.layer_diag = self.diagnostics.get_layer("classify", 3)

        # Thread lock for progress updates
        self.lock = Lock()

    def run(self) -> Dict[str, Any]:
        """
        Execute classify layer

        Returns:
            Dictionary with classification results and metadata
        """
        # Load L2 results
        l2_file = self.output_dir / "l2_scraped_pages.json"
        if not l2_file.exists():
            raise FileNotFoundError(f"L2 results not found: {l2_file}")

        with open(l2_file, 'r') as f:
            l2_data = json.load(f)

        pages = [p for p in l2_data['pages'] if p.get('success')]

        # Apply test mode limit
        if self.config.test_mode:
            self.logger.info(f"Test mode: limiting to first {self.config.test_mode} pages")
            pages = pages[:self.config.test_mode]

        self.logger.info(f"Classifying {len(pages)} pages...")
        self.logger.info(f"Spec: {self.spec.spec_name}")
        self.logger.info(f"Model: {self.spec.llm.model}")
        self.logger.info(f"Concurrency: {self.config.concurrency} threads")
        self.logger.info("")

        # Setup progress
        self.layer_diag.set_total_items(len(pages))
        self.progress.start_layer("l3_classify", total_items=len(pages))

        # Classify pages concurrently
        classified_pages = self._classify_concurrent(pages)

        # Complete layer
        self.layer_diag.complete()
        self.progress.complete_layer("l3_classify")

        # Save results
        results_file = self.output_dir / "l3_classified_pages.json"
        with open(results_file, 'w') as f:
            json.dump({
                "metadata": {
                    "spec": self.spec.spec_name,
                    "model": self.spec.llm.model,
                    "total_pages": len(classified_pages)
                },
                "pages": classified_pages
            }, f, indent=2)

        self.logger.info(f"✓ Layer 3 complete: {len(classified_pages)} pages classified")
        self.logger.info(f"  Saved to: {results_file}")
        self.logger.info("")

        return {
            "total_pages": len(classified_pages),
            "results_file": str(results_file)
        }

    def _classify_concurrent(self, pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Classify pages concurrently

        Args:
            pages: List of scraped pages

        Returns:
            List of classified page data
        """
        if not pages:
            return []

        classified_pages = []

        def classify_with_index(page_tuple):
            idx, page = page_tuple
            result = self._classify_page(page)
            return (idx, result)

        with ThreadPoolExecutor(max_workers=self.config.concurrency) as executor:
            futures = {
                executor.submit(classify_with_index, (i, page)): (i, page)
                for i, page in enumerate(pages)
            }

            for future in as_completed(futures):
                idx, page = futures[future]

                try:
                    result_idx, classification = future.result()

                    with self.lock:
                        if classification.get('success'):
                            self.progress.increment_progress("l3_classify", completed=1)
                            cat = classification.get('classification', 'unknown')
                            tokens = classification.get('tokens_input', 0) + classification.get('tokens_output', 0)
                            self.logger.info(f"  ✓ [{result_idx+1}/{len(pages)}] {page['url'][:60]}... → {cat} ({tokens} tokens)")
                        else:
                            self.progress.increment_progress("l3_classify", failed=1)
                            self.logger.error(f"  ✗ [{result_idx+1}/{len(pages)}] {page['url'][:60]}... ({classification.get('error')})")

                        classified_pages.append((result_idx, classification))

                except Exception as e:
                    with self.lock:
                        self.progress.increment_progress("l3_classify", failed=1)
                        self.logger.error(f"  ✗ Exception: {e}")
                        classified_pages.append((idx, {
                            "url": page.get('url', 'unknown'),
                            "success": False,
                            "error": str(e)
                        }))

        # Sort by original index
        classified_pages.sort(key=lambda x: x[0])
        return [page for idx, page in classified_pages]

    def _classify_page(self, page: Dict[str, Any]) -> Dict[str, Any]:
        """
        Classify a single page with retries

        Args:
            page: Scraped page data

        Returns:
            Classification result
        """
        url = page.get('url', 'unknown')
        markdown = page.get('markdown', '')
        links = page.get('links', [])

        # Truncate inputs (50k chars for markdown, 100 links)
        markdown = markdown[:50000]
        links = links[:100]

        # Build prompt
        prompt = self._build_prompt(markdown, links)

        max_retries = 3
        classify_start = datetime.now()

        for attempt in range(max_retries):
            try:
                # Call Claude API
                message = self.anthropic.messages.create(
                    model=self.spec.llm.model,
                    max_tokens=self.spec.llm.max_tokens,
                    temperature=self.spec.llm.temperature,
                    messages=[{"role": "user", "content": prompt}],
                    timeout=60
                )

                content = message.content[0].text

                # Record cost
                self.costs.record_claude_request(
                    model=self.spec.llm.model,
                    input_tokens=message.usage.input_tokens,
                    output_tokens=message.usage.output_tokens
                )

                # Parse JSON response
                cleaned_content = self._clean_json_response(content)
                result = json.loads(cleaned_content)

                # Record success
                duration = (datetime.now() - classify_start).total_seconds()
                self.layer_diag.record_success(
                    item_id=url,
                    duration_seconds=duration
                )

                if attempt > 0:
                    self.layer_diag.record_retry(succeeded=True)

                # Build response
                return {
                    'url': url,
                    'success': True,
                    'classification': result.get('classification', 'unknown'),
                    'confidence': result.get('confidence', 'unknown'),
                    'reasoning': result.get('reasoning', ''),
                    'extracted_data': result.get('extracted_data', {}),
                    'questions': result.get('questions', {}),
                    'tokens_input': message.usage.input_tokens,
                    'tokens_output': message.usage.output_tokens
                }

            except json.JSONDecodeError as e:
                if attempt < max_retries - 1:
                    self.layer_diag.record_retry(succeeded=False)
                    continue

                duration = (datetime.now() - classify_start).total_seconds()
                self.layer_diag.record_failure(
                    item_id=url,
                    error_type="json_parse_error",
                    error_message=str(e),
                    retry_count=attempt + 1,
                    can_retry=True,
                    duration_seconds=duration
                )

                return {
                    'url': url,
                    'success': False,
                    'error': f'JSON parse error: {str(e)}'
                }

            except Exception as e:
                if attempt < max_retries - 1:
                    self.layer_diag.record_retry(succeeded=False)
                    continue

                duration = (datetime.now() - classify_start).total_seconds()
                self.layer_diag.record_failure(
                    item_id=url,
                    error_type="api_error",
                    error_message=str(e),
                    retry_count=attempt + 1,
                    can_retry=True,
                    duration_seconds=duration
                )

                return {
                    'url': url,
                    'success': False,
                    'error': str(e)
                }

        return {
            'url': url,
            'success': False,
            'error': 'Max retries exceeded'
        }

    def _build_prompt(self, markdown: str, links: List[str]) -> str:
        """
        Build classification prompt from spec

        Args:
            markdown: Page markdown content
            links: List of links found on page

        Returns:
            Formatted prompt string
        """
        # Build categories section
        categories_list = ', '.join([cat.id for cat in self.spec.categories])
        categories_desc = '\n'.join([
            f"- {cat.id}: {cat.description}"
            for cat in self.spec.categories
        ])

        # Build extraction fields section
        extraction_desc = '\n'.join([
            f"- {field.name} ({field.type}, {'required' if field.required else 'optional'}): {field.description}"
            for field in self.spec.extraction_fields.values()
        ])

        # Build questions section
        questions_desc = '\n'.join([
            f"- {q.field}: {q.question} (answer type: {q.answer_type})"
            for q in self.spec.questions
        ])

        # Build output schema
        output_schema = {
            "classification": "one of: " + categories_list,
            "confidence": "high, medium, or low",
            "reasoning": "Brief explanation of classification (2-3 sentences)",
            "extracted_data": {
                field.name: f"<{field.type}>"
                for field in self.spec.extraction_fields.values()
            },
            "questions": {
                q.field: {
                    "answer": f"<{q.answer_type}>",
                    "reasoning": "<string>" if q.reasoning_required else None,
                    "evidence": "<string>" if q.evidence_required else None
                }
                for q in self.spec.questions
            }
        }

        # Clean up None values
        for q_field in output_schema["questions"]:
            output_schema["questions"][q_field] = {
                k: v for k, v in output_schema["questions"][q_field].items() if v is not None
            }

        prompt = f"""TASK: Analyze this webpage and provide structured classification and extraction.

<critical_instruction>
CRITICAL: Respond with PURE JSON ONLY.
- NO markdown code blocks (no ```json)
- NO explanatory text before or after
- ONLY the JSON object as specified below
</critical_instruction>

ANALYSIS SPEC: {self.spec.spec_name}
Description: {self.spec.description}

CLASSIFICATION:
Classify the webpage as one of: {categories_list}

CATEGORIES:
{categories_desc}

EXTRACTION FIELDS:
{extraction_desc}

QUESTIONS TO ANSWER:
{questions_desc}

WEBPAGE CONTENT:

Markdown:
{markdown}

Links found on page:
{chr(10).join(links[:50])}

<critical_instruction>
RESPOND WITH THIS EXACT JSON STRUCTURE (pure JSON, no markdown):
{json.dumps(output_schema, indent=2)}
</critical_instruction>
"""

        return prompt

    def _clean_json_response(self, content: str) -> str:
        """
        Clean JSON response by removing markdown code blocks

        Args:
            content: Raw response content

        Returns:
            Cleaned JSON string
        """
        cleaned = content.strip()

        # Remove markdown code blocks
        if cleaned.startswith('```'):
            first_newline = cleaned.find('\n')
            if first_newline != -1:
                cleaned = cleaned[first_newline+1:]
            if cleaned.endswith('```'):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

        return cleaned
