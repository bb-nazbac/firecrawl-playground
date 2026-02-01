"""
Diagnostics and Failure Tracking System

Manages exhaustive diagnostics and failure tracking for each pipeline layer.
Creates diagnostics_l{N}.json and failures_l{N}.json files.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from collections import defaultdict
from threading import Lock


class LayerDiagnostics:
    """
    Tracks detailed diagnostics for a pipeline layer

    Thread-safe diagnostics tracking with automatic file writing.
    """

    def __init__(self, output_dir: Path, layer_name: str, layer_num: int):
        """
        Initialize layer diagnostics

        Args:
            output_dir: Output directory for this run
            layer_name: Human-readable layer name (e.g., "search", "scrape", "classify")
            layer_num: Layer number (1-5)
        """
        self.output_dir = Path(output_dir)
        self.layer_name = layer_name
        self.layer_num = layer_num
        self.lock = Lock()

        self.diagnostics_file = self.output_dir / f"diagnostics_l{layer_num}_{layer_name}.json"
        self.failures_file = self.output_dir / f"failures_l{layer_num}_{layer_name}.json"

        # Initialize diagnostics structure
        self.diagnostics = {
            "layer": f"l{layer_num}_{layer_name}",
            "started_at": datetime.now().isoformat(),
            "completed_at": None,
            "status": "running",  # running, completed, failed
            "total_items": 0,
            "successful": 0,
            "failed": 0,
            "skipped_cached": 0,
            "retries": {
                "total_retry_attempts": 0,
                "items_succeeded_after_retry": 0,
                "items_failed_after_all_retries": 0
            },
            "timing": {
                "total_duration_seconds": 0,
                "avg_item_duration_seconds": 0,
                "min_item_duration_seconds": None,
                "max_item_duration_seconds": None
            },
            "errors_by_type": {},
            "per_city_breakdown": {},  # For L1/L2
            "api_stats": {},  # API-specific stats
            "cache_stats": {}  # Cache hit/miss stats for L2/L3
        }

        # Initialize failures list
        self.failures = []

        # Temporary tracking for calculations
        self._item_durations = []

        # Write initial files
        self._save()

    def set_total_items(self, total: int):
        """Set the total number of items to process"""
        with self.lock:
            self.diagnostics["total_items"] = total
            self._save()

    def record_success(self, item_id: str, duration_seconds: float, metadata: Optional[Dict] = None):
        """
        Record a successful operation

        Args:
            item_id: Unique identifier for the item
            duration_seconds: Time taken to process
            metadata: Optional additional metadata (city, api_response, etc.)
        """
        with self.lock:
            self.diagnostics["successful"] += 1
            self._item_durations.append(duration_seconds)
            self._update_timing()

            # Update per-city breakdown if city provided
            if metadata and "city" in metadata:
                city = metadata["city"]
                if city not in self.diagnostics["per_city_breakdown"]:
                    self.diagnostics["per_city_breakdown"][city] = {
                        "total": 0,
                        "successful": 0,
                        "failed": 0
                    }
                self.diagnostics["per_city_breakdown"][city]["total"] += 1
                self.diagnostics["per_city_breakdown"][city]["successful"] += 1

            self._save()

    def record_failure(
        self,
        item_id: str,
        error_type: str,
        error_message: str,
        retry_count: int,
        can_retry: bool,
        duration_seconds: float,
        metadata: Optional[Dict] = None
    ):
        """
        Record a failed operation

        Args:
            item_id: Unique identifier for the item
            error_type: Type of error (e.g., "timeout", "api_error", "parse_error")
            error_message: Detailed error message
            retry_count: Number of retries attempted
            can_retry: Whether this failure can be retried in a re-run
            duration_seconds: Time taken before failure
            metadata: Optional additional metadata (city, url, etc.)
        """
        with self.lock:
            self.diagnostics["failed"] += 1
            self._item_durations.append(duration_seconds)
            self._update_timing()

            # Update error counts by type
            if error_type not in self.diagnostics["errors_by_type"]:
                self.diagnostics["errors_by_type"][error_type] = 0
            self.diagnostics["errors_by_type"][error_type] += 1

            # Update per-city breakdown if city provided
            if metadata and "city" in metadata:
                city = metadata["city"]
                if city not in self.diagnostics["per_city_breakdown"]:
                    self.diagnostics["per_city_breakdown"][city] = {
                        "total": 0,
                        "successful": 0,
                        "failed": 0
                    }
                self.diagnostics["per_city_breakdown"][city]["total"] += 1
                self.diagnostics["per_city_breakdown"][city]["failed"] += 1

            # Add to failures list
            failure_record = {
                "item_id": item_id,
                "error_type": error_type,
                "error_message": error_message,
                "retry_count": retry_count,
                "can_retry": can_retry,
                "failed_at": datetime.now().isoformat(),
                "duration_seconds": duration_seconds,
                "metadata": metadata or {}
            }
            self.failures.append(failure_record)

            self._save()

    def record_retry(self, succeeded: bool):
        """
        Record a retry attempt

        Args:
            succeeded: Whether the retry succeeded
        """
        with self.lock:
            self.diagnostics["retries"]["total_retry_attempts"] += 1
            if succeeded:
                self.diagnostics["retries"]["items_succeeded_after_retry"] += 1
            else:
                self.diagnostics["retries"]["items_failed_after_all_retries"] += 1

            self._save()

    def record_cache_hit(self, item_id: str):
        """
        Record a cache hit (item skipped because already processed)

        Args:
            item_id: Unique identifier for the cached item
        """
        with self.lock:
            self.diagnostics["skipped_cached"] += 1

            if "hits" not in self.diagnostics["cache_stats"]:
                self.diagnostics["cache_stats"]["hits"] = 0
                self.diagnostics["cache_stats"]["misses"] = 0

            self.diagnostics["cache_stats"]["hits"] += 1

            self._save()

    def record_cache_miss(self):
        """Record a cache miss (item not in cache, needs processing)"""
        with self.lock:
            if "hits" not in self.diagnostics["cache_stats"]:
                self.diagnostics["cache_stats"]["hits"] = 0
                self.diagnostics["cache_stats"]["misses"] = 0

            self.diagnostics["cache_stats"]["misses"] += 1

            self._save()

    def update_api_stats(self, api_name: str, stats: Dict[str, Any]):
        """
        Update API-specific statistics

        Args:
            api_name: Name of the API (e.g., "serper", "firecrawl", "claude")
            stats: Dictionary of statistics to merge
        """
        with self.lock:
            if api_name not in self.diagnostics["api_stats"]:
                self.diagnostics["api_stats"][api_name] = {}

            self.diagnostics["api_stats"][api_name].update(stats)

            self._save()

    def complete(self):
        """Mark the layer as completed"""
        with self.lock:
            self.diagnostics["status"] = "completed"
            self.diagnostics["completed_at"] = datetime.now().isoformat()

            # Calculate total duration
            started = datetime.fromisoformat(self.diagnostics["started_at"])
            completed = datetime.fromisoformat(self.diagnostics["completed_at"])
            self.diagnostics["timing"]["total_duration_seconds"] = (completed - started).total_seconds()

            # Calculate cache hit rate
            if "hits" in self.diagnostics["cache_stats"]:
                total_cache = (
                    self.diagnostics["cache_stats"]["hits"] +
                    self.diagnostics["cache_stats"]["misses"]
                )
                if total_cache > 0:
                    hit_rate = (self.diagnostics["cache_stats"]["hits"] / total_cache) * 100
                    self.diagnostics["cache_stats"]["hit_rate_percent"] = round(hit_rate, 2)

            self._save()

    def fail(self, error: str):
        """
        Mark the layer as failed

        Args:
            error: Error message
        """
        with self.lock:
            self.diagnostics["status"] = "failed"
            self.diagnostics["completed_at"] = datetime.now().isoformat()
            self.diagnostics["error"] = error

            self._save()

    def get_diagnostics(self) -> Dict[str, Any]:
        """Get current diagnostics data"""
        with self.lock:
            return self.diagnostics.copy()

    def get_failures(self) -> List[Dict[str, Any]]:
        """Get list of failures"""
        with self.lock:
            return self.failures.copy()

    def _update_timing(self):
        """Update timing statistics (must be called within lock)"""
        if self._item_durations:
            self.diagnostics["timing"]["avg_item_duration_seconds"] = (
                sum(self._item_durations) / len(self._item_durations)
            )
            self.diagnostics["timing"]["min_item_duration_seconds"] = min(self._item_durations)
            self.diagnostics["timing"]["max_item_duration_seconds"] = max(self._item_durations)

    def _save(self):
        """Save diagnostics and failures to files (must be called within lock)"""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Save diagnostics
        with open(self.diagnostics_file, 'w') as f:
            json.dump(self.diagnostics, f, indent=2)

        # Save failures
        with open(self.failures_file, 'w') as f:
            json.dump({
                "layer": f"l{self.layer_num}_{self.layer_name}",
                "total_failures": len(self.failures),
                "failures": self.failures
            }, f, indent=2)


class DiagnosticsManager:
    """
    Manages diagnostics for all layers in a pipeline run

    Provides easy access to layer diagnostics and aggregated statistics.
    """

    def __init__(self, output_dir: Path):
        """
        Initialize diagnostics manager

        Args:
            output_dir: Output directory for this run
        """
        self.output_dir = Path(output_dir)
        self.layers = {}

    def get_layer(self, layer_name: str, layer_num: int) -> LayerDiagnostics:
        """
        Get or create diagnostics for a layer

        Args:
            layer_name: Human-readable layer name
            layer_num: Layer number (1-5)

        Returns:
            LayerDiagnostics instance
        """
        key = f"l{layer_num}_{layer_name}"
        if key not in self.layers:
            self.layers[key] = LayerDiagnostics(self.output_dir, layer_name, layer_num)
        return self.layers[key]

    def get_aggregate_stats(self) -> Dict[str, Any]:
        """
        Get aggregated statistics across all layers

        Returns:
            Dictionary of aggregate statistics
        """
        total_successful = 0
        total_failed = 0
        total_retries = 0
        errors_by_layer = {}

        for key, layer_diag in self.layers.items():
            diag = layer_diag.get_diagnostics()
            total_successful += diag["successful"]
            total_failed += diag["failed"]
            total_retries += diag["retries"]["total_retry_attempts"]
            errors_by_layer[key] = diag["errors_by_type"]

        return {
            "total_successful": total_successful,
            "total_failed": total_failed,
            "total_retries": total_retries,
            "errors_by_layer": errors_by_layer
        }


def load_diagnostics(output_dir: Path, layer_name: str, layer_num: int) -> Optional[Dict[str, Any]]:
    """
    Load existing diagnostics file

    Args:
        output_dir: Output directory for the run
        layer_name: Human-readable layer name
        layer_num: Layer number (1-5)

    Returns:
        Diagnostics dictionary or None if file doesn't exist
    """
    diagnostics_file = Path(output_dir) / f"diagnostics_l{layer_num}_{layer_name}.json"

    if not diagnostics_file.exists():
        return None

    with open(diagnostics_file, 'r') as f:
        return json.load(f)


def load_failures(output_dir: Path, layer_name: str, layer_num: int) -> Optional[List[Dict[str, Any]]]:
    """
    Load existing failures file

    Args:
        output_dir: Output directory for the run
        layer_name: Human-readable layer name
        layer_num: Layer number (1-5)

    Returns:
        List of failure records or None if file doesn't exist
    """
    failures_file = Path(output_dir) / f"failures_l{layer_num}_{layer_name}.json"

    if not failures_file.exists():
        return None

    with open(failures_file, 'r') as f:
        data = json.load(f)
        return data.get("failures", [])
