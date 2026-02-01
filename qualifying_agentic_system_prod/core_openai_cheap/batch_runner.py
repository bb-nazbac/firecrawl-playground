#!/usr/bin/env python3
"""
Batch Runner for Qualifying Agentic System (OpenAI Version)

Processes multiple domains concurrently using worker threads.
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
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict

# Add paths for imports
SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT_DIR))

from core_openai.domain_queue import DomainQueue, DomainTask, DomainResult
from core_openai.cost_tracker import CostTracker
from core_openai.progress_tracker import ProgressTracker
from core_openai.diagnostics import DiagnosticsManager


def load_env():
    """Load environment variables from .env file."""
    env_path = ROOT_DIR / ".env"
    if not env_path.exists():
        env_path = ROOT_DIR.parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip())


load_env()


class BatchRunner:
    """
    Orchestrates batch domain qualification with concurrent processing.

    Features:
    - CSV input support
    - Concurrent Firecrawl and OpenAI workers
    - Real-time progress tracking
    - Cost tracking with budget limits
    - JSON output with full results
    """

    def __init__(
        self,
        output_dir: Path,
        max_cost_usd: float = 100,
        firecrawl_concurrency: int = 50,
        openai_concurrency: int = 30,
        max_pages_per_domain: int = 11,
        max_iterations: int = 2,
        openai_model: str = "gpt-4o-mini",
        test_mode: Optional[int] = None
    ):
        """
        Initialize batch runner.

        Args:
            output_dir: Directory for outputs
            max_cost_usd: Maximum budget in USD
            firecrawl_concurrency: Max concurrent Firecrawl requests
            openai_concurrency: Max concurrent OpenAI requests
            max_pages_per_domain: Max pages to scrape per domain
            max_iterations: Max iteration rounds after homepage
            openai_model: OpenAI model to use
            test_mode: If set, only process first N domains
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.max_cost_usd = max_cost_usd
        self.firecrawl_concurrency = firecrawl_concurrency
        self.openai_concurrency = openai_concurrency
        self.max_pages_per_domain = max_pages_per_domain
        self.max_iterations = max_iterations
        self.openai_model = openai_model
        self.test_mode = test_mode

        # Initialize trackers
        self.cost_tracker = CostTracker(self.output_dir, max_cost_usd)
        self.progress_tracker = ProgressTracker(self.output_dir)
        self.diagnostics = DiagnosticsManager(self.output_dir)
        self.queue = DomainQueue()

        # Results storage
        self.results: List[DomainResult] = []
        self.results_lock = threading.Lock()

        # Worker control
        self.stop_event = threading.Event()

    def load_csv(self, csv_path: str) -> List[Dict[str, str]]:
        """
        Load domains from CSV file.

        Expected columns: domain (required), company_name (optional)

        Args:
            csv_path: Path to CSV file

        Returns:
            List of domain dicts
        """
        domains = []
        path = Path(csv_path)

        if not path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")

        with open(path, 'r', encoding='utf-8') as f:
            # Try to detect if there's a header
            sample = f.read(1024)
            f.seek(0)

            # Check if first line looks like a header
            first_line = sample.split('\n')[0].lower()
            has_header = 'domain' in first_line

            if has_header:
                reader = csv.DictReader(f)
                for row in reader:
                    domain = row.get('domain', '').strip()
                    if domain:
                        domains.append({
                            'domain': domain,
                            'company_name': row.get('company_name', '').strip() or None
                        })
            else:
                # No header - assume first column is domain
                reader = csv.reader(f)
                for row in reader:
                    if row and row[0].strip():
                        domains.append({
                            'domain': row[0].strip(),
                            'company_name': row[1].strip() if len(row) > 1 else None
                        })

        # Apply test mode limit
        if self.test_mode and len(domains) > self.test_mode:
            domains = domains[:self.test_mode]

        return domains

    def qualify_domain(self, task: DomainTask) -> DomainResult:
        """
        Qualify a single domain using the orchestrator.

        Args:
            task: DomainTask with domain info

        Returns:
            DomainResult with qualification outcome
        """
        # Import here to avoid circular imports
        sys.path.insert(0, str(ROOT_DIR / "testing" / "round_01_map_and_homepage_qualification" / "l2_iterative_qualify"))
        from orchestrator import qualify_domain as do_qualify, QualificationConfig

        config = QualificationConfig(
            max_pages=self.max_pages_per_domain,
            max_iterations=self.max_iterations,
            openai_model=self.openai_model
        )

        # Track costs via callback - write to log file
        log_file = self.output_dir / "qualification.log"
        def log_callback(msg):
            with open(log_file, 'a') as f:
                f.write(msg + '\n')

        result = do_qualify(task.domain, config, log_callback, self.diagnostics)

        # Record costs
        # Note: The orchestrator already uses the APIs, but we track here for batch totals
        self.cost_tracker.record_firecrawl_map(task.domain, 1)
        self.cost_tracker.record_firecrawl_scrape(task.domain, result.pages_scraped)

        # Estimate OpenAI costs from tokens
        if result.total_tokens > 0:
            # Rough split: 80% input, 20% output
            input_tokens = int(result.total_tokens * 0.8)
            output_tokens = result.total_tokens - input_tokens
            self.cost_tracker.record_openai_request(
                task.domain, self.openai_model, input_tokens, output_tokens
            )

        return DomainResult(
            domain=task.domain,
            success=result.success,
            classification=result.final_classification,
            disqualification_reason=result.disqualification_reason,
            answers=result.answers,
            confidence=result.confidence,
            products_found=result.products_found,
            evidence=result.evidence,
            pages_scraped=result.pages_scraped,
            iterations=result.iterations,
            credits_used=result.total_cost_credits,
            tokens_used=result.total_tokens,
            duration_ms=result.duration_ms,
            error=result.error
        )

    def worker(self, worker_id: int):
        """
        Worker thread that processes domains from the queue.

        Args:
            worker_id: Unique worker identifier
        """
        while not self.stop_event.is_set():
            # Check budget
            if self.cost_tracker.is_over_budget():
                print(f"Worker {worker_id}: Budget exceeded, stopping")
                break

            # Get next task
            task = self.queue.get_next_task(timeout=1.0)
            if task is None:
                if self.queue.is_complete():
                    break
                continue

            # Process domain
            try:
                self.progress_tracker.start_domain(task.domain)
                result = self.qualify_domain(task)

                # Submit result
                self.queue.submit_result(result)

                # Update progress
                self.progress_tracker.complete_domain(
                    domain=task.domain,
                    classification=result.classification or "UNKNOWN",
                    iterations=result.iterations,
                    pages_scraped=result.pages_scraped,
                    success=result.success,
                    error=result.error
                )

                # Store result
                with self.results_lock:
                    self.results.append(result)

            except Exception as e:
                error_result = DomainResult(
                    domain=task.domain,
                    success=False,
                    error=str(e)
                )
                self.queue.submit_result(error_result)
                self.progress_tracker.complete_domain(
                    domain=task.domain,
                    classification="ERROR",
                    iterations=0,
                    pages_scraped=0,
                    success=False,
                    error=str(e)
                )

    def run(self, csv_path: str) -> List[DomainResult]:
        """
        Run batch qualification on domains from CSV.

        Args:
            csv_path: Path to input CSV file

        Returns:
            List of DomainResult objects
        """
        print(f"\n{'═'*60}")
        print("QUALIFYING AGENTIC SYSTEM - BATCH RUN (OpenAI)")
        print(f"{'═'*60}")
        print(f"Output: {self.output_dir}")
        print(f"Budget: ${self.max_cost_usd}")
        print(f"Concurrency: {self.firecrawl_concurrency} Firecrawl / {self.openai_concurrency} OpenAI")
        print(f"Max pages/domain: {self.max_pages_per_domain}")
        print(f"{'═'*60}\n")

        # Load domains
        print(f"Loading domains from {csv_path}...")
        domains = self.load_csv(csv_path)
        print(f"Loaded {len(domains)} domains")

        if not domains:
            print("No domains to process")
            return []

        # Initialize progress
        self.progress_tracker.set_total(len(domains))

        # Add domains to queue
        added = self.queue.add_domains_from_list(domains)
        print(f"Queued {added} domains ({len(domains) - added} duplicates skipped)")
        self.queue.mark_all_added()

        # Start workers
        # Use min of configured concurrency and domain count
        num_workers = min(self.openai_concurrency, added)
        print(f"Starting {num_workers} workers...")

        start_time = time.time()

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [
                executor.submit(self.worker, i)
                for i in range(num_workers)
            ]

            # Monitor progress
            while not self.queue.is_complete():
                time.sleep(5)

                # Print status
                stats = self.queue.get_stats()
                progress = self.progress_tracker.get_progress()
                cost = self.cost_tracker.get_total_cost()

                print(f"\r[{progress['percent']:.1f}%] "
                      f"{progress['processed']}/{progress['total_domains']} domains | "
                      f"${cost:.2f} spent | "
                      f"{stats['pending']} pending", end="", flush=True)

                # Check budget
                if self.cost_tracker.is_over_budget():
                    print("\n\n⚠️  BUDGET EXCEEDED - Stopping...")
                    self.stop_event.set()
                    self.queue.shutdown()
                    break

            # Wait for workers to finish
            for future in futures:
                future.result()

        # Complete run
        duration = time.time() - start_time

        if self.cost_tracker.is_over_budget():
            self.progress_tracker.stop_run("Budget exceeded")
        else:
            self.progress_tracker.complete_run()

        # Save results
        self._save_results()

        # Save diagnostics summary
        self.diagnostics.save_final_summary()

        # Print summary
        print(f"\n\n{'═'*60}")
        print("RUN COMPLETE")
        print(f"{'═'*60}")
        print(f"Duration: {duration:.1f}s")
        print(self.progress_tracker.to_summary_string())
        print(self.cost_tracker.to_summary_string())

        return self.results

    def _save_results(self):
        """Save all results to JSON file."""
        results_file = self.output_dir / "results.json"

        with self.results_lock:
            results_data = {
                "run_id": self.output_dir.name,
                "completed_at": datetime.now().isoformat(),
                "total_domains": len(self.results),
                "results": [asdict(r) for r in self.results]
            }

        with open(results_file, 'w') as f:
            json.dump(results_data, f, indent=2)

        print(f"\nResults saved to: {results_file}")


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='Batch domain qualification (OpenAI)')
    parser.add_argument('csv_file', help='Input CSV file with domains')
    parser.add_argument('--output', '-o', help='Output directory')
    parser.add_argument('--budget', type=float, default=100, help='Max cost in USD')
    parser.add_argument('--concurrency', type=int, default=30, help='Max concurrent workers')
    parser.add_argument('--max-pages', type=int, default=11, help='Max pages per domain')
    parser.add_argument('--test', type=int, help='Only process first N domains')
    parser.add_argument('--model', default='gpt-4o-mini', help='OpenAI model')

    args = parser.parse_args()

    # Set output directory
    if args.output:
        output_dir = Path(args.output)
    else:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_dir = ROOT_DIR / "outputs" / f"run_{timestamp}"

    # Run batch
    runner = BatchRunner(
        output_dir=output_dir,
        max_cost_usd=args.budget,
        openai_concurrency=args.concurrency,
        max_pages_per_domain=args.max_pages,
        test_mode=args.test,
        openai_model=args.model
    )

    runner.run(args.csv_file)


if __name__ == '__main__':
    main()
