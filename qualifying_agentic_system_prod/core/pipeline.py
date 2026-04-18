#!/usr/bin/env python3
"""
Main Pipeline Orchestrator

Ties together L1 (Homepage) and L2 (Map+Iterate) into a single flow.
Optimized to skip /map for companies where homepage is sufficient.

Flow:
1. L1: Scrape homepage → Claude check → if sufficient, DONE
2. L2: (only if insufficient) Map → Iterate → Final classification
3. L3: Export results

Following OPTIMUS PRIME Protocol v2.0
"""

import os
import sys
import csv
import json
import time
import threading
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass, field, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed

SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT_DIR))

from core.layer_homepage import process_homepage, HomepageResult, AnalysisSpec
from core.layer_map_iterate import process_iterative, IterativeResult

# ═══════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════

@dataclass
class PipelineResult:
    """Final result for a single domain"""
    domain: str
    success: bool

    # Which path was taken
    path: str = "unknown"  # "filtered_early", "homepage_only", or "homepage_plus_iterate"
    filtered_early: bool = False  # True if disqualified by waterfall filter

    # Company info
    company_name: Optional[str] = None

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
    map_used: bool = False
    credits_used: int = 0
    tokens_used: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0
    error: Optional[str] = None


@dataclass
class PipelineConfig:
    """Configuration for pipeline run"""
    # Spec file
    spec_path: str = str(ROOT_DIR / "configs/specs/analysis/TEMPLATE.json")
    client_name: str = "example_client"

    # Model
    claude_model: str = "claude-haiku-4-5-20251001"

    # Concurrency - separate for Firecrawl and Claude
    firecrawl_concurrency: int = 45
    claude_concurrency: int = 30

    # Iteration limits
    max_pages: int = 11  # Max additional pages to scrape beyond homepage
    # DEPRECATED: max_iterations and pages_per_round - now using sequential single-page approach
    max_iterations: int = 2  # Not used - kept for backwards compatibility
    pages_per_round: int = 5  # Not used - kept for backwards compatibility

    # Budget
    max_cost_usd: float = 100.0


# ═══════════════════════════════════════════════════════════════
# SINGLE DOMAIN PROCESSING
# ═══════════════════════════════════════════════════════════════

def process_domain(
    domain: str,
    spec: AnalysisSpec,
    config: PipelineConfig,
    firecrawl_semaphore: threading.Semaphore,
    claude_semaphore: threading.Semaphore,
    log_callback=None
) -> PipelineResult:
    """
    Process a single domain through the full pipeline.

    Args:
        domain: Company domain to qualify
        spec: Analysis specification
        config: Pipeline configuration
        firecrawl_semaphore: Semaphore for Firecrawl rate limiting
        claude_semaphore: Semaphore for Claude rate limiting
        log_callback: Optional callback for logging

    Returns:
        PipelineResult with final qualification
    """
    def log(msg):
        if log_callback:
            log_callback(msg)

    start_time = time.time()
    result = PipelineResult(domain=domain, success=False)

    # ─────────────────────────────────────────────────────────
    # L1: HOMEPAGE ANALYSIS
    # ─────────────────────────────────────────────────────────
    l1_result = process_homepage(
        domain=domain,
        spec=spec,
        claude_model=config.claude_model,
        firecrawl_semaphore=firecrawl_semaphore,
        claude_semaphore=claude_semaphore,
        log_callback=log_callback
    )

    if not l1_result.success:
        result.error = l1_result.error
        result.credits_used = l1_result.credits_used
        result.tokens_used = l1_result.tokens_used
        result.input_tokens = l1_result.input_tokens
        result.output_tokens = l1_result.output_tokens
        result.duration_ms = int((time.time() - start_time) * 1000)
        return result

    # Update metrics from L1
    result.credits_used += l1_result.credits_used
    result.tokens_used += l1_result.tokens_used
    result.input_tokens += l1_result.input_tokens
    result.output_tokens += l1_result.output_tokens
    result.pages_scraped = 1  # Homepage

    # ─────────────────────────────────────────────────────────
    # CHECK IF FILTERED EARLY OR SUFFICIENT
    # ─────────────────────────────────────────────────────────
    if l1_result.filtered_early:
        # Waterfall filter disqualified this domain - cheapest path!
        result.success = True
        result.path = "filtered_early"
        result.filtered_early = True
        result.classification = l1_result.classification
        result.disqualification_reason = l1_result.disqualification_reason
        result.answers = l1_result.answers
        result.confidence = l1_result.confidence
        result.evidence = l1_result.evidence
        result.map_used = False
        result.iterations = 0
        result.duration_ms = int((time.time() - start_time) * 1000)

        log(f"\n🚫 FILTERED EARLY: {domain} - {l1_result.disqualification_reason}")
        return result

    if l1_result.sufficient:
        # Fast path - homepage was enough!
        result.success = True
        result.path = "homepage_only"
        result.classification = l1_result.classification
        result.disqualification_reason = l1_result.disqualification_reason
        result.answers = l1_result.answers
        result.confidence = l1_result.confidence
        result.products_found = l1_result.products_found
        result.evidence = l1_result.evidence
        result.map_used = False
        result.iterations = 0
        result.duration_ms = int((time.time() - start_time) * 1000)

        log(f"\n🚀 FAST PATH: Homepage sufficient for {domain}")
        return result

    # ─────────────────────────────────────────────────────────
    # L2: MAP + ITERATIVE (only if insufficient)
    # ─────────────────────────────────────────────────────────
    log(f"\n📍 Homepage insufficient, proceeding to L2...")

    l2_result = process_iterative(
        domain=domain,
        spec=spec,
        homepage_content=l1_result.homepage_content,
        homepage_url=l1_result.homepage_url,
        homepage_summary=l1_result.homepage_summary or '',
        previous_answers=l1_result.answers or {},
        previous_confidence=l1_result.confidence or {},
        low_confidence_questions=l1_result.low_confidence_questions or [],
        suggested_page_types=l1_result.suggested_page_types or [],
        max_pages=config.max_pages - 1,  # -1 for homepage already scraped
        claude_model=config.claude_model,
        firecrawl_semaphore=firecrawl_semaphore,
        claude_semaphore=claude_semaphore,
        log_callback=log_callback
    )

    # Combine results
    result.success = l2_result.success
    result.path = "homepage_plus_iterate"
    result.classification = l2_result.classification
    result.disqualification_reason = l2_result.disqualification_reason
    result.answers = l2_result.answers
    result.confidence = l2_result.confidence
    result.products_found = l2_result.products_found
    result.evidence = l2_result.evidence
    result.pages_scraped = l2_result.pages_scraped
    result.iterations = l2_result.iterations
    result.map_used = True
    result.credits_used += l2_result.credits_used
    result.tokens_used += l2_result.tokens_used
    result.input_tokens += l2_result.input_tokens
    result.output_tokens += l2_result.output_tokens
    result.duration_ms = int((time.time() - start_time) * 1000)
    result.error = l2_result.error

    return result


# ═══════════════════════════════════════════════════════════════
# BATCH PROCESSING
# ═══════════════════════════════════════════════════════════════

class BatchPipeline:
    """
    Batch processor for multiple domains.

    Features:
    - Concurrent processing with separate Firecrawl/Claude limits
    - Progress tracking
    - Cost tracking
    - Client-specific output paths
    - CSV/JSON export
    """

    def __init__(
        self,
        config: PipelineConfig = None
    ):
        self.config = config or PipelineConfig()

        # Load spec
        self.spec = AnalysisSpec.load(Path(self.config.spec_path))

        # Create client-specific output directory
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.output_dir = ROOT_DIR / "outputs" / self.config.client_name / f"run_{timestamp}"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Create semaphores for rate limiting
        self.firecrawl_semaphore = threading.Semaphore(self.config.firecrawl_concurrency)
        self.claude_semaphore = threading.Semaphore(self.config.claude_concurrency)

        # Results storage
        self.results: List[PipelineResult] = []
        self.results_lock = threading.Lock()

        # Incremental output files
        self.jsonl_path = self.output_dir / "results.jsonl"
        self.csv_path = self.output_dir / "results.csv"
        self._init_output_files()

        # Metrics
        self.total_domains = 0
        self.processed = 0
        self.filtered_early = 0  # Waterfall filter disqualified
        self.homepage_sufficient = 0
        self.needed_iteration = 0
        self.failed = 0
        self.total_credits = 0
        self.total_tokens = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    def _init_output_files(self):
        """Initialize output files with headers."""
        # CSV header
        with open(self.csv_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'domain', 'success', 'path', 'classification',
                'disqualification_reason', 'sells_products', 'is_b2b',
                'has_inventory_or_manufacturing', 'product_type', 'primary_category',
                'pages_scraped', 'iterations', 'map_used', 'credits_used',
                'input_tokens', 'output_tokens', 'tokens_used', 'duration_ms', 'error'
            ])
        # JSONL starts empty
        open(self.jsonl_path, 'w').close()

    def _append_result(self, result: PipelineResult):
        """Append a single result to output files (thread-safe, called within lock)."""
        # Append to JSONL
        with open(self.jsonl_path, 'a') as f:
            f.write(json.dumps(asdict(result), default=str) + '\n')

        # Append to CSV
        answers = result.answers or {}
        with open(self.csv_path, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                result.domain, result.success, result.path, result.classification,
                result.disqualification_reason,
                answers.get('sells_products', ''),
                answers.get('is_b2b', ''),
                answers.get('has_inventory_or_manufacturing', ''),
                answers.get('product_type', ''),
                answers.get('primary_category', ''),
                result.pages_scraped, result.iterations, result.map_used, result.credits_used,
                result.input_tokens, result.output_tokens, result.tokens_used, result.duration_ms, result.error
            ])

    def load_csv(self, csv_path: str, limit: int = None) -> List[str]:
        """Load domains from CSV file."""
        domains = []
        path = Path(csv_path)

        if not path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")

        with open(path, 'r', encoding='utf-8') as f:
            sample = f.read(1024)
            f.seek(0)

            first_line = sample.split('\n')[0].lower()
            has_header = 'domain' in first_line

            if has_header:
                reader = csv.DictReader(f)
                for row in reader:
                    domain = row.get('domain', '').strip()
                    if domain:
                        domains.append(domain)
            else:
                reader = csv.reader(f)
                for row in reader:
                    if row and row[0].strip():
                        domains.append(row[0].strip())

        if limit:
            domains = domains[:limit]

        return domains

    def process_worker(self, domain: str) -> PipelineResult:
        """Worker function for processing a single domain."""
        result = process_domain(
            domain=domain,
            spec=self.spec,
            config=self.config,
            firecrawl_semaphore=self.firecrawl_semaphore,
            claude_semaphore=self.claude_semaphore
        )

        with self.results_lock:
            self.results.append(result)
            self._append_result(result)  # Write to disk immediately
            self.processed += 1
            self.total_credits += result.credits_used
            self.total_tokens += result.tokens_used
            self.total_input_tokens += result.input_tokens
            self.total_output_tokens += result.output_tokens

            if not result.success:
                self.failed += 1
            elif result.filtered_early:
                self.filtered_early += 1
            elif result.path == "homepage_only":
                self.homepage_sufficient += 1
            else:
                self.needed_iteration += 1

            # Progress update
            pct = (self.processed / self.total_domains) * 100
            print(f"\r[{pct:.1f}%] {self.processed}/{self.total_domains} | "
                  f"Filter: {self.filtered_early} | HP: {self.homepage_sufficient} | "
                  f"Iter: {self.needed_iteration} | Fail: {self.failed}", end="", flush=True)

        return result

    def run(self, csv_path: str, limit: int = None) -> List[PipelineResult]:
        """
        Run batch processing on domains from CSV.

        Args:
            csv_path: Path to input CSV file
            limit: Optional limit on number of domains to process

        Returns:
            List of PipelineResult objects
        """
        print(f"\n{'═'*70}")
        print("QUALIFYING AGENTIC SYSTEM - OPTIMIZED PIPELINE")
        print(f"{'═'*70}")
        print(f"Client: {self.config.client_name}")
        print(f"Spec: {self.spec.spec_name}")
        print(f"Output: {self.output_dir}")
        print(f"Model: {self.config.claude_model}")
        print(f"Firecrawl Concurrency: {self.config.firecrawl_concurrency}")
        print(f"Claude Concurrency: {self.config.claude_concurrency}")
        print(f"{'═'*70}\n")

        # Load domains
        print(f"Loading domains from {csv_path}...")
        domains = self.load_csv(csv_path, limit)
        self.total_domains = len(domains)
        print(f"Loaded {len(domains)} domains\n")

        if not domains:
            print("No domains to process")
            return []

        # Use the higher concurrency for thread pool (domains process sequentially through both APIs)
        num_workers = max(self.config.firecrawl_concurrency, self.config.claude_concurrency)

        # Process with thread pool
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = {executor.submit(self.process_worker, d): d for d in domains}

            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    domain = futures[future]
                    print(f"\nError processing {domain}: {e}")

        duration = time.time() - start_time

        # Save results
        self._save_results()

        # Calculate costs (Haiku pricing: $1/M input, $5/M output)
        input_cost = (self.total_input_tokens / 1_000_000) * 1.0
        output_cost = (self.total_output_tokens / 1_000_000) * 5.0
        total_cost = input_cost + output_cost

        # Print summary
        print(f"\n\n{'═'*70}")
        print("BATCH COMPLETE")
        print(f"{'═'*70}")
        print(f"Client: {self.config.client_name}")
        print(f"Duration: {duration:.1f}s ({duration/60:.1f}m)")
        print(f"Domains: {self.total_domains}")
        print(f"  - Filtered Early (waterfall): {self.filtered_early} ({self.filtered_early/self.total_domains*100:.1f}%) 💰 SAVED")
        print(f"  - Homepage Sufficient: {self.homepage_sufficient} ({self.homepage_sufficient/self.total_domains*100:.1f}%)")
        print(f"  - Needed Iteration: {self.needed_iteration} ({self.needed_iteration/self.total_domains*100:.1f}%)")
        print(f"  - Failed: {self.failed} ({self.failed/self.total_domains*100:.1f}%)")
        print(f"Total Credits: {self.total_credits}")
        print(f"\n📊 TOKEN USAGE (Claude Haiku):")
        print(f"  Input Tokens:  {self.total_input_tokens:,} (${input_cost:.4f})")
        print(f"  Output Tokens: {self.total_output_tokens:,} (${output_cost:.4f})")
        print(f"  Total Tokens:  {self.total_tokens:,}")
        print(f"  💰 TOTAL COST: ${total_cost:.4f}")
        print(f"  Cost/Domain:   ${total_cost/self.total_domains:.6f}")
        print(f"\nAvg Time/Domain: {duration/self.total_domains:.1f}s")
        print(f"Results: {self.output_dir}")
        print(f"{'═'*70}")

        return self.results

    def _save_results(self):
        """Save final summary JSON (CSV/JSONL already written incrementally)."""
        # Calculate costs
        input_cost = (self.total_input_tokens / 1_000_000) * 1.0
        output_cost = (self.total_output_tokens / 1_000_000) * 5.0
        total_cost = input_cost + output_cost

        # Summary JSON
        summary_path = self.output_dir / "summary.json"
        with open(summary_path, 'w') as f:
            json.dump({
                "client": self.config.client_name,
                "spec": self.spec.spec_name,
                "model": self.config.claude_model,
                "completed_at": datetime.now().isoformat(),
                "total_domains": self.total_domains,
                "filtered_early": self.filtered_early,
                "homepage_sufficient": self.homepage_sufficient,
                "needed_iteration": self.needed_iteration,
                "failed": self.failed,
                "total_credits": self.total_credits,
                "total_tokens": self.total_tokens,
                "input_tokens": self.total_input_tokens,
                "output_tokens": self.total_output_tokens,
                "cost_usd": {
                    "input": round(input_cost, 6),
                    "output": round(output_cost, 6),
                    "total": round(total_cost, 6),
                    "per_domain": round(total_cost / self.total_domains, 8) if self.total_domains > 0 else 0
                }
            }, f, indent=2)
        print(f"\nSummary: {summary_path}")
        print(f"Results CSV: {self.csv_path}")
        print(f"Results JSONL: {self.jsonl_path}")


# ═══════════════════════════════════════════════════════════════
# CLI ENTRY POINT
# ═══════════════════════════════════════════════════════════════

def main():
    import argparse

    parser = argparse.ArgumentParser(description='Qualifying Agentic System - Optimized Pipeline')
    parser.add_argument('input', help='Input CSV file with domains OR single domain')
    parser.add_argument('--limit', '-n', type=int, help='Limit number of domains')
    parser.add_argument('--firecrawl-concurrency', type=int, default=45, help='Firecrawl concurrent requests (default: 45)')
    parser.add_argument('--claude-concurrency', type=int, default=30, help='Claude concurrent requests (default: 30)')
    parser.add_argument('--max-pages', type=int, default=11, help='Max pages per domain (default: 11)')
    parser.add_argument('--model', default='claude-haiku-4-5-20251001', help='Claude model (default: claude-haiku-4-5-20251001)')
    parser.add_argument('--spec', default=str(ROOT_DIR / 'configs/specs/analysis/TEMPLATE.json'),
                        help='Path to analysis spec')
    parser.add_argument('--client', default='example_client', help='Client name for output directory')

    args = parser.parse_args()

    config = PipelineConfig(
        spec_path=args.spec,
        client_name=args.client,
        claude_model=args.model,
        firecrawl_concurrency=args.firecrawl_concurrency,
        claude_concurrency=args.claude_concurrency,
        max_pages=args.max_pages
    )

    # Check if input is a file or single domain
    if Path(args.input).exists() and args.input.endswith('.csv'):
        # Batch mode
        pipeline = BatchPipeline(config)
        pipeline.run(args.input, args.limit)
    else:
        # Single domain mode
        spec = AnalysisSpec.load(Path(config.spec_path))
        firecrawl_sem = threading.Semaphore(config.firecrawl_concurrency)
        claude_sem = threading.Semaphore(config.claude_concurrency)

        result = process_domain(
            args.input, spec, config, firecrawl_sem, claude_sem
        )
        print(f"\n{'='*60}")
        print("RESULT:")
        print(json.dumps(asdict(result), indent=2, default=str))


if __name__ == '__main__':
    main()
