"""
Diagnostics and Failure Tracking System for Qualifying Agentic System (OpenAI Version)

Comprehensive diagnostics for each pipeline step with failure recovery support.
Following OPTIMUS PRIME Protocol v2.0
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from threading import Lock


class StepDiagnostics:
    """
    Tracks detailed diagnostics for a pipeline step (map, scrape, classify).

    Thread-safe with automatic file persistence.
    """

    def __init__(self, output_dir: Path, step_name: str):
        """
        Initialize step diagnostics.

        Args:
            output_dir: Output directory for this run
            step_name: Step name (e.g., "map", "scrape", "classify")
        """
        self.output_dir = Path(output_dir)
        self.step_name = step_name
        self.lock = Lock()

        self.diagnostics_file = self.output_dir / f"diagnostics_{step_name}.json"
        self.failures_file = self.output_dir / f"failures_{step_name}.json"

        # Initialize diagnostics structure
        self.diagnostics = {
            "step": step_name,
            "started_at": datetime.now().isoformat(),
            "completed_at": None,
            "status": "running",
            "total_items": 0,
            "successful": 0,
            "failed": 0,
            "retries": {
                "total_attempts": 0,
                "succeeded_after_retry": 0,
                "failed_after_max_retries": 0
            },
            "timing": {
                "total_duration_seconds": 0,
                "avg_item_seconds": 0,
                "min_item_seconds": None,
                "max_item_seconds": None,
                "p95_item_seconds": None
            },
            "errors_by_type": {},
            "api_stats": {
                "requests": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "credits_used": 0
            }
        }

        # Failures list
        self.failures: List[Dict] = []

        # Timing samples for percentile calculation
        self._durations: List[float] = []

        self._save()

    def set_total(self, total: int):
        """Set total items to process."""
        with self.lock:
            self.diagnostics["total_items"] = total
            self._save()

    def record_success(
        self,
        item_id: str,
        duration_seconds: float,
        retry_count: int = 0,
        metadata: Optional[Dict] = None
    ):
        """
        Record successful operation.

        Args:
            item_id: Unique identifier (domain, URL)
            duration_seconds: Time taken
            retry_count: Number of retries needed
            metadata: Additional context
        """
        with self.lock:
            self.diagnostics["successful"] += 1
            self._durations.append(duration_seconds)
            self._update_timing()

            if retry_count > 0:
                self.diagnostics["retries"]["succeeded_after_retry"] += 1

            self._save()

    def record_failure(
        self,
        item_id: str,
        error_type: str,
        error_message: str,
        duration_seconds: float,
        retry_count: int = 0,
        can_retry: bool = True,
        metadata: Optional[Dict] = None
    ):
        """
        Record failed operation.

        Args:
            item_id: Unique identifier
            error_type: Category (timeout, http_4xx, rate_limit, parse_error, etc.)
            error_message: Full error message
            duration_seconds: Time before failure
            retry_count: Retries attempted
            can_retry: Whether this can be retried in a re-run
            metadata: Additional context
        """
        with self.lock:
            self.diagnostics["failed"] += 1
            self._durations.append(duration_seconds)
            self._update_timing()

            # Count by error type
            if error_type not in self.diagnostics["errors_by_type"]:
                self.diagnostics["errors_by_type"][error_type] = 0
            self.diagnostics["errors_by_type"][error_type] += 1

            if retry_count > 0:
                self.diagnostics["retries"]["failed_after_max_retries"] += 1

            # Add to failures list
            failure = {
                "item_id": item_id,
                "error_type": error_type,
                "error_message": error_message,
                "duration_seconds": duration_seconds,
                "retry_count": retry_count,
                "can_retry": can_retry,
                "failed_at": datetime.now().isoformat(),
                "metadata": metadata or {}
            }
            self.failures.append(failure)

            self._save()

    def record_retry(self):
        """Record a retry attempt."""
        with self.lock:
            self.diagnostics["retries"]["total_attempts"] += 1
            self._save()

    def record_api_call(
        self,
        tokens_in: int = 0,
        tokens_out: int = 0,
        credits: int = 0
    ):
        """Record API usage stats."""
        with self.lock:
            self.diagnostics["api_stats"]["requests"] += 1
            self.diagnostics["api_stats"]["tokens_in"] += tokens_in
            self.diagnostics["api_stats"]["tokens_out"] += tokens_out
            self.diagnostics["api_stats"]["credits_used"] += credits
            self._save()

    def complete(self):
        """Mark step as completed."""
        with self.lock:
            self.diagnostics["status"] = "completed"
            self.diagnostics["completed_at"] = datetime.now().isoformat()

            started = datetime.fromisoformat(self.diagnostics["started_at"])
            completed = datetime.fromisoformat(self.diagnostics["completed_at"])
            self.diagnostics["timing"]["total_duration_seconds"] = (
                completed - started
            ).total_seconds()

            self._save()

    def fail(self, error: str):
        """Mark step as failed."""
        with self.lock:
            self.diagnostics["status"] = "failed"
            self.diagnostics["completed_at"] = datetime.now().isoformat()
            self.diagnostics["fatal_error"] = error
            self._save()

    def get_diagnostics(self) -> Dict[str, Any]:
        """Get current diagnostics."""
        with self.lock:
            return self.diagnostics.copy()

    def get_failures(self) -> List[Dict]:
        """Get failures list."""
        with self.lock:
            return self.failures.copy()

    def get_retryable_failures(self) -> List[Dict]:
        """Get failures that can be retried."""
        with self.lock:
            return [f for f in self.failures if f.get("can_retry", True)]

    def _update_timing(self):
        """Update timing stats (called within lock)."""
        if not self._durations:
            return

        self.diagnostics["timing"]["avg_item_seconds"] = (
            sum(self._durations) / len(self._durations)
        )
        self.diagnostics["timing"]["min_item_seconds"] = min(self._durations)
        self.diagnostics["timing"]["max_item_seconds"] = max(self._durations)

        # P95
        if len(self._durations) >= 20:
            sorted_durations = sorted(self._durations)
            p95_idx = int(len(sorted_durations) * 0.95)
            self.diagnostics["timing"]["p95_item_seconds"] = sorted_durations[p95_idx]

    def _save(self):
        """Persist to files (called within lock)."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        with open(self.diagnostics_file, 'w') as f:
            json.dump(self.diagnostics, f, indent=2)

        with open(self.failures_file, 'w') as f:
            json.dump({
                "step": self.step_name,
                "total_failures": len(self.failures),
                "retryable": len([f for f in self.failures if f.get("can_retry")]),
                "failures": self.failures
            }, f, indent=2)


class DomainDiagnostics:
    """
    Tracks per-domain diagnostics across all steps.

    Provides visibility into each domain's journey through the pipeline.
    """

    def __init__(self, output_dir: Path):
        """Initialize domain diagnostics."""
        self.output_dir = Path(output_dir)
        self.lock = Lock()

        self.domains_file = self.output_dir / "domain_diagnostics.json"
        self.domains: Dict[str, Dict] = {}

        self._save()

    def start_domain(self, domain: str):
        """Mark domain as started."""
        with self.lock:
            self.domains[domain] = {
                "domain": domain,
                "started_at": datetime.now().isoformat(),
                "status": "processing",
                "steps": {},
                "total_duration_seconds": 0,
                "total_credits": 0,
                "total_tokens": 0
            }
            self._save()

    def record_step(
        self,
        domain: str,
        step: str,
        success: bool,
        duration_seconds: float,
        credits: int = 0,
        tokens: int = 0,
        details: Optional[Dict] = None,
        error: Optional[str] = None
    ):
        """
        Record a step completion for a domain.

        Args:
            domain: Domain being processed
            step: Step name (map, scrape_homepage, classify, etc.)
            success: Whether step succeeded
            duration_seconds: Time taken
            credits: Firecrawl credits used
            tokens: OpenAI tokens used
            details: Additional details (urls found, pages scraped, etc.)
            error: Error message if failed
        """
        with self.lock:
            if domain not in self.domains:
                self.start_domain(domain)

            step_record = {
                "step": step,
                "success": success,
                "duration_seconds": duration_seconds,
                "completed_at": datetime.now().isoformat(),
                "credits": credits,
                "tokens": tokens
            }

            if details:
                step_record["details"] = details
            if error:
                step_record["error"] = error

            self.domains[domain]["steps"][step] = step_record
            self.domains[domain]["total_credits"] += credits
            self.domains[domain]["total_tokens"] += tokens

            self._save()

    def complete_domain(
        self,
        domain: str,
        classification: str,
        success: bool,
        error: Optional[str] = None
    ):
        """Mark domain as completed."""
        with self.lock:
            if domain not in self.domains:
                return

            self.domains[domain]["status"] = "completed" if success else "failed"
            self.domains[domain]["completed_at"] = datetime.now().isoformat()
            self.domains[domain]["classification"] = classification

            if error:
                self.domains[domain]["error"] = error

            started = datetime.fromisoformat(self.domains[domain]["started_at"])
            completed = datetime.fromisoformat(self.domains[domain]["completed_at"])
            self.domains[domain]["total_duration_seconds"] = (
                completed - started
            ).total_seconds()

            self._save()

    def get_domain(self, domain: str) -> Optional[Dict]:
        """Get diagnostics for a domain."""
        with self.lock:
            return self.domains.get(domain, {}).copy()

    def get_all(self) -> Dict[str, Dict]:
        """Get all domain diagnostics."""
        with self.lock:
            return {k: v.copy() for k, v in self.domains.items()}

    def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics."""
        with self.lock:
            total = len(self.domains)
            completed = sum(1 for d in self.domains.values() if d["status"] == "completed")
            failed = sum(1 for d in self.domains.values() if d["status"] == "failed")
            processing = sum(1 for d in self.domains.values() if d["status"] == "processing")

            return {
                "total_domains": total,
                "completed": completed,
                "failed": failed,
                "processing": processing,
                "total_credits": sum(d["total_credits"] for d in self.domains.values()),
                "total_tokens": sum(d["total_tokens"] for d in self.domains.values())
            }

    def _save(self):
        """Persist to file (called within lock)."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Calculate summary inline to avoid lock re-acquisition
        summary = {}
        if self.domains:
            total = len(self.domains)
            completed = sum(1 for d in self.domains.values() if d["status"] == "completed")
            failed = sum(1 for d in self.domains.values() if d["status"] == "failed")
            processing = sum(1 for d in self.domains.values() if d["status"] == "processing")
            summary = {
                "total_domains": total,
                "completed": completed,
                "failed": failed,
                "processing": processing,
                "total_credits": sum(d["total_credits"] for d in self.domains.values()),
                "total_tokens": sum(d["total_tokens"] for d in self.domains.values())
            }

        with open(self.domains_file, 'w') as f:
            json.dump({
                "summary": summary,
                "domains": self.domains
            }, f, indent=2)


class DiagnosticsManager:
    """
    Central manager for all diagnostics in a run.
    """

    def __init__(self, output_dir: Path):
        """Initialize diagnostics manager."""
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Step diagnostics
        self.map_diag = StepDiagnostics(output_dir, "map")
        self.scrape_diag = StepDiagnostics(output_dir, "scrape")
        self.classify_diag = StepDiagnostics(output_dir, "classify")

        # Domain-level diagnostics
        self.domain_diag = DomainDiagnostics(output_dir)

    def get_aggregate_stats(self) -> Dict[str, Any]:
        """Get aggregate statistics across all steps."""
        map_d = self.map_diag.get_diagnostics()
        scrape_d = self.scrape_diag.get_diagnostics()
        classify_d = self.classify_diag.get_diagnostics()
        domain_s = self.domain_diag.get_summary()

        return {
            "domains": domain_s,
            "map": {
                "successful": map_d["successful"],
                "failed": map_d["failed"],
                "retries": map_d["retries"]["total_attempts"]
            },
            "scrape": {
                "successful": scrape_d["successful"],
                "failed": scrape_d["failed"],
                "retries": scrape_d["retries"]["total_attempts"]
            },
            "classify": {
                "successful": classify_d["successful"],
                "failed": classify_d["failed"],
                "retries": classify_d["retries"]["total_attempts"]
            },
            "total_api_calls": (
                map_d["api_stats"]["requests"] +
                scrape_d["api_stats"]["requests"] +
                classify_d["api_stats"]["requests"]
            ),
            "total_credits": (
                map_d["api_stats"]["credits_used"] +
                scrape_d["api_stats"]["credits_used"]
            ),
            "total_tokens": (
                classify_d["api_stats"]["tokens_in"] +
                classify_d["api_stats"]["tokens_out"]
            )
        }

    def save_final_summary(self):
        """Save final summary file."""
        summary_file = self.output_dir / "run_summary.json"

        with open(summary_file, 'w') as f:
            json.dump({
                "completed_at": datetime.now().isoformat(),
                "aggregate": self.get_aggregate_stats(),
                "map": self.map_diag.get_diagnostics(),
                "scrape": self.scrape_diag.get_diagnostics(),
                "classify": self.classify_diag.get_diagnostics()
            }, f, indent=2)


def load_failures(output_dir: Path, step: str) -> List[Dict]:
    """Load failures from a previous run for retry."""
    failures_file = Path(output_dir) / f"failures_{step}.json"

    if not failures_file.exists():
        return []

    with open(failures_file, 'r') as f:
        data = json.load(f)
        return data.get("failures", [])
