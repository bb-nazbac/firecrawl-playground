"""
Unified Analytics Engine

Merges CostTracker + ProgressTracker + DiagnosticsManager into a single
AnalyticsEngine that provides comprehensive tracking for the pipeline.

All classes are thread-safe using threading.Lock.
"""

import json
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from threading import Lock


# =====================================================================
# PRICING
# =====================================================================

PRICING = {
    # Fixed-cost APIs
    "serper": {"per_query": 0.001},
    "firecrawl": {"per_page": 0.001},

    # LLM token-based pricing: (input_per_1m, output_per_1m)
    "claude-haiku-4-5-20251001": (1.0, 5.0),
    "claude-3-5-haiku-20241022": (0.80, 4.00),
    "claude-sonnet-4-20250514": (3.0, 15.0),
    "claude-opus-4-20250514": (15.0, 75.0),
    "gpt-5-mini": (0.15, 0.60),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.0),
    "sonar": (1.0, 1.0),
    "sonar-pro": (3.0, 15.0),
}


def _get_llm_pricing(model: str):
    """
    Get (input_per_1m, output_per_1m) pricing for a model.
    Falls back to cheapest pricing if unknown model.
    """
    if model in PRICING and isinstance(PRICING[model], tuple):
        return PRICING[model]

    # Try partial matching
    model_lower = model.lower()
    for key, val in PRICING.items():
        if isinstance(val, tuple) and key in model_lower:
            return val

    # Unknown model - use a conservative default (haiku pricing)
    return (1.0, 5.0)


# =====================================================================
# COST TRACKER
# =====================================================================

class CostTracker:
    """
    Thread-safe cost tracking for all API services.

    Tracks costs for Serper, Firecrawl, and LLMs (Claude, OpenAI, Perplexity).
    Supports budget enforcement with warnings at 50%, 80%, 90%, and hard stop at 100%.
    """

    def __init__(self, output_dir: Path, max_cost_usd: Optional[float] = None):
        self.output_dir = Path(output_dir)
        self.costs_file = self.output_dir / "costs.json"
        self.max_cost_usd = max_cost_usd
        self.lock = Lock()
        self._budget_exceeded = False
        self._warning_thresholds_hit = set()

        self.costs = {
            "started_at": datetime.now().isoformat(),
            "max_cost_usd": max_cost_usd,
            "total_cost_usd": 0.0,
            "warnings": [],
            "breakdown_by_api": {
                "serper": {"total_queries": 0, "cost_usd": 0.0},
                "firecrawl": {"total_pages": 0, "cost_usd": 0.0},
                "llm": {
                    "total_requests": 0,
                    "total_input_tokens": 0,
                    "total_output_tokens": 0,
                    "cost_usd": 0.0,
                    "by_model": {},
                },
            },
        }
        self._save()

    def record_api_cost(
        self,
        api: str,
        model: str = None,
        tokens_in: int = 0,
        tokens_out: int = 0,
        credits: int = 0,
    ):
        """
        Record an API cost.

        Args:
            api: API name - "serper", "firecrawl", or "llm"
            model: Model name (required for llm)
            tokens_in: Input tokens (for llm)
            tokens_out: Output tokens (for llm)
            credits: Number of credits/queries (for serper/firecrawl)
        """
        with self.lock:
            if api == "serper":
                count = max(credits, 1)
                cost = count * PRICING["serper"]["per_query"]
                self.costs["breakdown_by_api"]["serper"]["total_queries"] += count
                self.costs["breakdown_by_api"]["serper"]["cost_usd"] += cost
                self.costs["total_cost_usd"] += cost

            elif api == "firecrawl":
                count = max(credits, 1)
                cost = count * PRICING["firecrawl"]["per_page"]
                self.costs["breakdown_by_api"]["firecrawl"]["total_pages"] += count
                self.costs["breakdown_by_api"]["firecrawl"]["cost_usd"] += cost
                self.costs["total_cost_usd"] += cost

            elif api == "llm" and model:
                input_price, output_price = _get_llm_pricing(model)
                input_cost = (tokens_in / 1_000_000) * input_price
                output_cost = (tokens_out / 1_000_000) * output_price
                total_cost = input_cost + output_cost

                llm_data = self.costs["breakdown_by_api"]["llm"]
                llm_data["total_requests"] += 1
                llm_data["total_input_tokens"] += tokens_in
                llm_data["total_output_tokens"] += tokens_out
                llm_data["cost_usd"] += total_cost

                if model not in llm_data["by_model"]:
                    llm_data["by_model"][model] = {
                        "requests": 0,
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "cost_usd": 0.0,
                    }
                model_data = llm_data["by_model"][model]
                model_data["requests"] += 1
                model_data["input_tokens"] += tokens_in
                model_data["output_tokens"] += tokens_out
                model_data["cost_usd"] += total_cost

                self.costs["total_cost_usd"] += total_cost

            self._check_threshold()
            self._save()

    def is_over_budget(self) -> bool:
        """Check if we've exceeded the cost ceiling."""
        with self.lock:
            return self._budget_exceeded

    def get_total_cost(self) -> float:
        """Get current total cost in USD."""
        with self.lock:
            return self.costs["total_cost_usd"]

    def get_costs(self) -> Dict[str, Any]:
        """Get complete costs data."""
        with self.lock:
            return json.loads(json.dumps(self.costs))

    def _check_threshold(self):
        """Check if cost exceeds budget thresholds (called within lock)."""
        if self.max_cost_usd is None:
            return

        total = self.costs["total_cost_usd"]
        percent = (total / self.max_cost_usd) * 100

        for threshold in [50, 80, 90, 100]:
            if percent >= threshold and threshold not in self._warning_thresholds_hit:
                self._warning_thresholds_hit.add(threshold)
                warning = (
                    f"Cost threshold {threshold}% reached: "
                    f"${total:.4f} / ${self.max_cost_usd:.2f}"
                )
                self.costs["warnings"].append(warning)
                if threshold >= 100:
                    self._budget_exceeded = True

    def _save(self):
        """Save costs to file (called within lock)."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        with open(self.costs_file, 'w') as f:
            json.dump(self.costs, f, indent=2)

    def to_console_string(self) -> str:
        """Generate console-friendly cost summary."""
        with self.lock:
            lines = []
            lines.append(f"{'='*60}")
            lines.append("COST BREAKDOWN")
            lines.append(f"{'='*60}")

            serper = self.costs["breakdown_by_api"]["serper"]
            lines.append(f"\nSerper.dev:")
            lines.append(f"  Queries: {serper['total_queries']}")
            lines.append(f"  Cost: ${serper['cost_usd']:.4f}")

            firecrawl = self.costs["breakdown_by_api"]["firecrawl"]
            lines.append(f"\nFirecrawl:")
            lines.append(f"  Pages: {firecrawl['total_pages']}")
            lines.append(f"  Cost: ${firecrawl['cost_usd']:.4f}")

            llm = self.costs["breakdown_by_api"]["llm"]
            lines.append(f"\nLLM:")
            lines.append(f"  Requests: {llm['total_requests']}")
            lines.append(f"  Input tokens: {llm['total_input_tokens']:,}")
            lines.append(f"  Output tokens: {llm['total_output_tokens']:,}")
            lines.append(f"  Cost: ${llm['cost_usd']:.4f}")

            if llm["by_model"]:
                for model, data in llm["by_model"].items():
                    lines.append(f"    {model}: {data['requests']} reqs, ${data['cost_usd']:.4f}")

            lines.append(f"\n{'='*60}")
            lines.append(f"TOTAL COST: ${self.costs['total_cost_usd']:.4f}")

            if self.max_cost_usd:
                percent = (self.costs['total_cost_usd'] / self.max_cost_usd) * 100
                lines.append(f"Budget: ${self.max_cost_usd:.2f} ({percent:.1f}% used)")

            if self.costs["warnings"]:
                lines.append(f"\nWARNINGS:")
                for w in self.costs["warnings"]:
                    lines.append(f"  ! {w}")

            lines.append(f"{'='*60}")
            return "\n".join(lines)


# =====================================================================
# PROGRESS TRACKER
# =====================================================================

class ProgressTracker:
    """
    Thread-safe stage-agnostic progress tracker.

    Tracks progress per stage (dynamic stage names, not hardcoded).
    Writes progress.json with real-time status updates.
    """

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.progress_file = self.output_dir / "progress.json"
        self.lock = Lock()

        self.progress = {
            "started_at": datetime.now().isoformat(),
            "status": "running",
            "stages": {},
        }
        self._save()

    def start_stage(self, stage: str, total_items: int = None):
        """
        Mark a stage as started.

        Args:
            stage: Stage name (e.g. "search", "qualify", "dedupe", "fact_check")
            total_items: Total number of items to process in this stage (if known)
        """
        with self.lock:
            self.progress["stages"][stage] = {
                "status": "running",
                "started_at": datetime.now().isoformat(),
                "completed_at": None,
                "total_items": total_items,
                "completed": 0,
                "failed": 0,
                "percent": 0.0,
            }
            self._save()

    def increment_progress(self, stage: str, completed: int = 0, failed: int = 0):
        """
        Increment progress counters for a stage.

        Args:
            stage: Stage name
            completed: Number of newly completed items
            failed: Number of newly failed items
        """
        with self.lock:
            if stage not in self.progress["stages"]:
                self.progress["stages"][stage] = {
                    "status": "running",
                    "started_at": datetime.now().isoformat(),
                    "completed_at": None,
                    "total_items": None,
                    "completed": 0,
                    "failed": 0,
                    "percent": 0.0,
                }

            s = self.progress["stages"][stage]
            s["completed"] += completed
            s["failed"] += failed

            total = s.get("total_items")
            if total and total > 0:
                processed = s["completed"] + s["failed"]
                s["percent"] = round((processed / total) * 100, 1)

            self._save()

    def complete_stage(self, stage: str):
        """Mark a stage as completed."""
        with self.lock:
            if stage in self.progress["stages"]:
                s = self.progress["stages"][stage]
                s["status"] = "completed"
                s["completed_at"] = datetime.now().isoformat()
                s["percent"] = 100.0
            self._save()

    def fail_stage(self, stage: str, error: str = None):
        """Mark a stage as failed."""
        with self.lock:
            if stage in self.progress["stages"]:
                s = self.progress["stages"][stage]
                s["status"] = "failed"
                s["completed_at"] = datetime.now().isoformat()
                if error:
                    s["error"] = error
            self._save()

    def complete_run(self):
        """Mark the entire run as completed."""
        with self.lock:
            self.progress["status"] = "completed"
            self.progress["completed_at"] = datetime.now().isoformat()
            self._save()

    def fail_run(self, error: str):
        """Mark the entire run as failed."""
        with self.lock:
            self.progress["status"] = "failed"
            self.progress["completed_at"] = datetime.now().isoformat()
            self.progress["fatal_error"] = error
            self._save()

    def get_progress(self) -> Dict[str, Any]:
        """Get current progress data."""
        with self.lock:
            return json.loads(json.dumps(self.progress))

    def _save(self):
        """Save progress to file (called within lock)."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        with open(self.progress_file, 'w') as f:
            json.dump(self.progress, f, indent=2)

    def to_console_string(self) -> str:
        """Generate console-friendly progress summary."""
        with self.lock:
            lines = []
            lines.append(f"{'='*60}")
            lines.append(f"PROGRESS: {self.progress['status'].upper()}")
            lines.append(f"{'='*60}")

            for stage_name, s in self.progress["stages"].items():
                total = s.get("total_items") or "?"
                completed = s["completed"]
                failed = s["failed"]
                pct = s["percent"]
                status = s["status"]

                bar_width = 30
                filled = int(bar_width * pct / 100) if pct > 0 else 0
                bar = "#" * filled + "-" * (bar_width - filled)

                lines.append(f"\n  {stage_name} [{status}]")
                lines.append(f"    [{bar}] {pct:.1f}%")
                lines.append(f"    Done: {completed}/{total}  Failed: {failed}")

            lines.append(f"\n{'='*60}")
            return "\n".join(lines)


# =====================================================================
# DIAGNOSTICS MANAGER
# =====================================================================

class DiagnosticsManager:
    """
    Thread-safe diagnostics tracking per stage.

    Creates per-stage files:
    - diagnostics_{stage}.json: aggregate stats
    - failures_{stage}.json: detailed failure records
    """

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.lock = Lock()

        # Per-stage data
        self._stages: Dict[str, Dict] = {}
        self._failures: Dict[str, List[Dict]] = {}
        self._durations: Dict[str, List[float]] = {}

    def _ensure_stage(self, stage: str):
        """Initialize stage data if not present (called within lock)."""
        if stage not in self._stages:
            self._stages[stage] = {
                "stage": stage,
                "started_at": datetime.now().isoformat(),
                "completed_at": None,
                "status": "running",
                "successful": 0,
                "failed": 0,
                "timing": {
                    "avg_item_seconds": 0,
                    "min_item_seconds": None,
                    "max_item_seconds": None,
                    "p95_item_seconds": None,
                },
                "errors_by_type": {},
            }
            self._failures[stage] = []
            self._durations[stage] = []

    def record_success(
        self,
        stage: str,
        item_id: str,
        duration_seconds: float,
        metadata: dict = None,
    ):
        """
        Record a successful operation.

        Args:
            stage: Stage name
            item_id: Unique identifier (domain, URL, etc.)
            duration_seconds: Time taken
            metadata: Additional context
        """
        with self.lock:
            self._ensure_stage(stage)
            self._stages[stage]["successful"] += 1
            self._durations[stage].append(duration_seconds)
            self._update_timing(stage)
            self._save_stage(stage)

    def record_failure(
        self,
        stage: str,
        item_id: str,
        error_type: str,
        error_message: str,
        duration_seconds: float,
        can_retry: bool = True,
    ):
        """
        Record a failed operation.

        Args:
            stage: Stage name
            item_id: Unique identifier
            error_type: Category (timeout, http_4xx, rate_limit, etc.)
            error_message: Full error message
            duration_seconds: Time before failure
            can_retry: Whether this can be retried in a re-run
        """
        with self.lock:
            self._ensure_stage(stage)
            self._stages[stage]["failed"] += 1
            self._durations[stage].append(duration_seconds)

            # Count by error type
            errors = self._stages[stage]["errors_by_type"]
            errors[error_type] = errors.get(error_type, 0) + 1

            # Add to failures list
            failure = {
                "item_id": item_id,
                "error_type": error_type,
                "error_message": error_message,
                "duration_seconds": round(duration_seconds, 3),
                "can_retry": can_retry,
                "failed_at": datetime.now().isoformat(),
            }
            self._failures[stage].append(failure)

            self._update_timing(stage)
            self._save_stage(stage)

    def complete_stage(self, stage: str):
        """Mark a stage diagnostics as complete."""
        with self.lock:
            self._ensure_stage(stage)
            self._stages[stage]["status"] = "completed"
            self._stages[stage]["completed_at"] = datetime.now().isoformat()
            self._save_stage(stage)

    def get_diagnostics(self, stage: str) -> Dict:
        """Get diagnostics for a stage."""
        with self.lock:
            self._ensure_stage(stage)
            return json.loads(json.dumps(self._stages[stage]))

    def get_failures(self, stage: str) -> List[Dict]:
        """Get failures for a stage."""
        with self.lock:
            return list(self._failures.get(stage, []))

    def get_retryable_failures(self, stage: str) -> List[Dict]:
        """Get retryable failures for a stage."""
        with self.lock:
            return [f for f in self._failures.get(stage, []) if f.get("can_retry", True)]

    def get_all_stages(self) -> List[str]:
        """Get list of all tracked stage names."""
        with self.lock:
            return list(self._stages.keys())

    def _update_timing(self, stage: str):
        """Update timing stats for a stage (called within lock)."""
        durations = self._durations[stage]
        if not durations:
            return

        timing = self._stages[stage]["timing"]
        timing["avg_item_seconds"] = round(sum(durations) / len(durations), 3)
        timing["min_item_seconds"] = round(min(durations), 3)
        timing["max_item_seconds"] = round(max(durations), 3)

        if len(durations) >= 20:
            sorted_d = sorted(durations)
            p95_idx = int(len(sorted_d) * 0.95)
            timing["p95_item_seconds"] = round(sorted_d[p95_idx], 3)

    def _save_stage(self, stage: str):
        """Save diagnostics and failures files for a stage (called within lock)."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        diag_file = self.output_dir / f"diagnostics_{stage}.json"
        with open(diag_file, 'w') as f:
            json.dump(self._stages[stage], f, indent=2)

        failures_file = self.output_dir / f"failures_{stage}.json"
        failures = self._failures.get(stage, [])
        with open(failures_file, 'w') as f:
            json.dump({
                "stage": stage,
                "total_failures": len(failures),
                "retryable": len([fl for fl in failures if fl.get("can_retry")]),
                "failures": failures,
            }, f, indent=2)


# =====================================================================
# UNIFIED ANALYTICS ENGINE
# =====================================================================

class AnalyticsEngine:
    """
    Unified analytics engine combining CostTracker, ProgressTracker, and DiagnosticsManager.

    Provides a single interface for all tracking needs.
    """

    def __init__(self, output_dir: Path, max_cost_usd: float = None):
        """
        Initialize the analytics engine.

        Args:
            output_dir: Directory for all analytics output files
            max_cost_usd: Optional cost ceiling for budget enforcement
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.cost_tracker = CostTracker(output_dir, max_cost_usd)
        self.progress_tracker = ProgressTracker(output_dir)
        self.diagnostics = DiagnosticsManager(output_dir)

        self._start_time = time.time()

    # --- Cost delegation ---

    def record_api_cost(
        self,
        api: str,
        model: str = None,
        tokens_in: int = 0,
        tokens_out: int = 0,
        credits: int = 0,
    ):
        """Record an API cost. See CostTracker.record_api_cost."""
        self.cost_tracker.record_api_cost(api, model, tokens_in, tokens_out, credits)

    def is_over_budget(self) -> bool:
        """Check if we've exceeded the cost ceiling."""
        return self.cost_tracker.is_over_budget()

    def get_total_cost(self) -> float:
        """Get current total cost in USD."""
        return self.cost_tracker.get_total_cost()

    # --- Progress delegation ---

    def start_stage(self, stage: str, total_items: int = None):
        """Start tracking a pipeline stage."""
        self.progress_tracker.start_stage(stage, total_items)

    def increment_progress(self, stage: str, completed: int = 0, failed: int = 0):
        """Increment progress counters for a stage."""
        self.progress_tracker.increment_progress(stage, completed, failed)

    def complete_stage(self, stage: str):
        """Mark a stage as completed (in both progress and diagnostics)."""
        self.progress_tracker.complete_stage(stage)
        self.diagnostics.complete_stage(stage)

    # --- Diagnostics delegation ---

    def record_success(
        self,
        stage: str,
        item_id: str,
        duration_seconds: float,
        metadata: dict = None,
    ):
        """Record a successful operation."""
        self.diagnostics.record_success(stage, item_id, duration_seconds, metadata)

    def record_failure(
        self,
        stage: str,
        item_id: str,
        error_type: str,
        error_message: str,
        duration_seconds: float,
        can_retry: bool = True,
    ):
        """Record a failed operation."""
        self.diagnostics.record_failure(
            stage, item_id, error_type, error_message, duration_seconds, can_retry
        )

    # --- Finalization ---

    def finalize(self):
        """
        Finalize all trackers and write summary files.
        Call this at the end of a pipeline run.
        """
        self.progress_tracker.complete_run()

        # Write final summary
        elapsed = time.time() - self._start_time
        summary = {
            "completed_at": datetime.now().isoformat(),
            "duration_seconds": round(elapsed, 1),
            "costs": self.cost_tracker.get_costs(),
            "progress": self.progress_tracker.get_progress(),
            "diagnostics": {},
        }

        for stage in self.diagnostics.get_all_stages():
            summary["diagnostics"][stage] = self.diagnostics.get_diagnostics(stage)

        summary_file = self.output_dir / "run_summary.json"
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)

    def to_console_string(self) -> str:
        """Generate a combined console-friendly summary string."""
        elapsed = time.time() - self._start_time

        lines = []
        lines.append(f"\n{'='*60}")
        lines.append("PIPELINE ANALYTICS SUMMARY")
        lines.append(f"{'='*60}")
        lines.append(f"\nDuration: {elapsed:.1f}s ({elapsed/60:.1f}m)")

        # Cost summary
        lines.append(f"\n{self.cost_tracker.to_console_string()}")

        # Progress summary
        lines.append(f"\n{self.progress_tracker.to_console_string()}")

        # Diagnostics summary per stage
        for stage in self.diagnostics.get_all_stages():
            diag = self.diagnostics.get_diagnostics(stage)
            failures = self.diagnostics.get_failures(stage)
            lines.append(f"\n  [{stage}] Success: {diag['successful']}  Failed: {diag['failed']}")
            if diag["errors_by_type"]:
                for err_type, count in diag["errors_by_type"].items():
                    lines.append(f"    {err_type}: {count}")
            if failures:
                retryable = len([f for f in failures if f.get("can_retry")])
                lines.append(f"    Retryable failures: {retryable}/{len(failures)}")

        lines.append(f"\n{'='*60}")
        return "\n".join(lines)
