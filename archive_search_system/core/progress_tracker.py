"""
Progress Tracking System

Manages real-time progress tracking for pipeline runs.
Updates progress.json file with current status of each layer.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
from threading import Lock


class ProgressTracker:
    """
    Tracks pipeline progress in real-time

    Thread-safe progress tracking that writes to progress.json file.
    """

    def __init__(self, output_dir: Path):
        """
        Initialize progress tracker

        Args:
            output_dir: Output directory for this run (e.g., outputs/fuse/run_20251113_140000/)
        """
        self.output_dir = Path(output_dir)
        self.progress_file = self.output_dir / "progress.json"
        self.lock = Lock()

        # Initialize progress structure
        self.progress = {
            "run_id": self.output_dir.name,
            "started_at": datetime.now().isoformat(),
            "status": "running",  # running, completed, failed
            "current_layer": None,
            "layers": {
                "l1_search": {
                    "status": "pending",  # pending, running, completed, failed
                    "started_at": None,
                    "completed_at": None,
                    "total": 0,
                    "completed": 0,
                    "failed": 0,
                    "percent": 0.0
                },
                "l2_scrape": {
                    "status": "pending",
                    "started_at": None,
                    "completed_at": None,
                    "total": 0,
                    "completed": 0,
                    "failed": 0,
                    "skipped_cached": 0,
                    "percent": 0.0
                },
                "l3_classify": {
                    "status": "pending",
                    "started_at": None,
                    "completed_at": None,
                    "total": 0,
                    "completed": 0,
                    "failed": 0,
                    "skipped_cached": 0,
                    "percent": 0.0
                },
                "l4_export": {
                    "status": "pending",
                    "started_at": None,
                    "completed_at": None
                },
                "l5_dedupe": {
                    "status": "pending",
                    "started_at": None,
                    "completed_at": None,
                    "total": 0,
                    "duplicates_removed": 0
                }
            },
            "summary": {
                "total_searches": 0,
                "total_pages_scraped": 0,
                "total_pages_classified": 0,
                "final_results": 0
            }
        }

        # Write initial progress file
        self._save()

    def start_layer(self, layer: str, total_items: Optional[int] = None):
        """
        Mark a layer as started

        Args:
            layer: Layer name (l1_search, l2_scrape, l3_classify, l4_export, l5_dedupe)
            total_items: Total number of items to process (for L1-L3)
        """
        with self.lock:
            self.progress["current_layer"] = layer
            self.progress["layers"][layer]["status"] = "running"
            self.progress["layers"][layer]["started_at"] = datetime.now().isoformat()

            if total_items is not None:
                self.progress["layers"][layer]["total"] = total_items

            self._save()

    def complete_layer(self, layer: str):
        """
        Mark a layer as completed

        Args:
            layer: Layer name
        """
        with self.lock:
            self.progress["layers"][layer]["status"] = "completed"
            self.progress["layers"][layer]["completed_at"] = datetime.now().isoformat()

            # Update percent to 100%
            if "percent" in self.progress["layers"][layer]:
                self.progress["layers"][layer]["percent"] = 100.0

            self._save()

    def fail_layer(self, layer: str, error: str):
        """
        Mark a layer as failed

        Args:
            layer: Layer name
            error: Error message
        """
        with self.lock:
            self.progress["layers"][layer]["status"] = "failed"
            self.progress["layers"][layer]["completed_at"] = datetime.now().isoformat()
            self.progress["layers"][layer]["error"] = error

            self._save()

    def update_progress(
        self,
        layer: str,
        completed: Optional[int] = None,
        failed: Optional[int] = None,
        skipped_cached: Optional[int] = None
    ):
        """
        Update progress counters for a layer

        Args:
            layer: Layer name
            completed: Number of completed items (incremental or absolute)
            failed: Number of failed items (incremental or absolute)
            skipped_cached: Number of items skipped due to cache (incremental or absolute)
        """
        with self.lock:
            layer_data = self.progress["layers"][layer]

            if completed is not None:
                layer_data["completed"] = completed

            if failed is not None:
                layer_data["failed"] = failed

            if skipped_cached is not None:
                layer_data["skipped_cached"] = skipped_cached

            # Calculate percentage
            if layer_data["total"] > 0:
                processed = layer_data["completed"] + layer_data["failed"]
                if "skipped_cached" in layer_data:
                    processed += layer_data["skipped_cached"]
                layer_data["percent"] = (processed / layer_data["total"]) * 100.0

            self._save()

    def increment_progress(
        self,
        layer: str,
        completed: int = 0,
        failed: int = 0,
        skipped_cached: int = 0
    ):
        """
        Increment progress counters for a layer

        Args:
            layer: Layer name
            completed: Number of items to add to completed count
            failed: Number of items to add to failed count
            skipped_cached: Number of items to add to skipped_cached count
        """
        with self.lock:
            layer_data = self.progress["layers"][layer]

            layer_data["completed"] += completed
            layer_data["failed"] += failed

            if "skipped_cached" in layer_data:
                layer_data["skipped_cached"] += skipped_cached

            # Calculate percentage
            if layer_data["total"] > 0:
                processed = layer_data["completed"] + layer_data["failed"]
                if "skipped_cached" in layer_data:
                    processed += layer_data["skipped_cached"]
                layer_data["percent"] = (processed / layer_data["total"]) * 100.0

            self._save()

    def complete_run(self):
        """Mark the entire run as completed"""
        with self.lock:
            self.progress["status"] = "completed"
            self.progress["completed_at"] = datetime.now().isoformat()

            # Update summary
            self.progress["summary"]["total_searches"] = self.progress["layers"]["l1_search"]["completed"]
            self.progress["summary"]["total_pages_scraped"] = self.progress["layers"]["l2_scrape"]["completed"]
            self.progress["summary"]["total_pages_classified"] = self.progress["layers"]["l3_classify"]["completed"]

            self._save()

    def fail_run(self, error: str):
        """
        Mark the entire run as failed

        Args:
            error: Error message
        """
        with self.lock:
            self.progress["status"] = "failed"
            self.progress["completed_at"] = datetime.now().isoformat()
            self.progress["error"] = error

            self._save()

    def update_summary(self, **kwargs):
        """
        Update summary fields

        Args:
            **kwargs: Key-value pairs to update in summary
        """
        with self.lock:
            self.progress["summary"].update(kwargs)
            self._save()

    def get_progress(self) -> Dict[str, Any]:
        """
        Get current progress data

        Returns:
            Progress dictionary
        """
        with self.lock:
            return self.progress.copy()

    def get_layer_progress(self, layer: str) -> Dict[str, Any]:
        """
        Get progress for a specific layer

        Args:
            layer: Layer name

        Returns:
            Layer progress dictionary
        """
        with self.lock:
            return self.progress["layers"][layer].copy()

    def _save(self):
        """Save progress to file (must be called within lock)"""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        with open(self.progress_file, 'w') as f:
            json.dump(self.progress, f, indent=2)

    def to_console_string(self) -> str:
        """
        Generate console-friendly progress string

        Returns:
            Formatted progress string for console display
        """
        with self.lock:
            lines = []
            lines.append(f"\n{'='*60}")
            lines.append(f"Run: {self.progress['run_id']}")
            lines.append(f"Status: {self.progress['status'].upper()}")
            lines.append(f"Current Layer: {self.progress['current_layer'] or 'None'}")
            lines.append(f"{'='*60}")

            for layer_name, layer_data in self.progress["layers"].items():
                status_icon = {
                    "pending": "⏸",
                    "running": "▶",
                    "completed": "✓",
                    "failed": "✗"
                }.get(layer_data["status"], "?")

                lines.append(f"\n{status_icon} {layer_name.upper()}: {layer_data['status']}")

                if "total" in layer_data and layer_data["total"] > 0:
                    lines.append(f"  Progress: {layer_data['completed']}/{layer_data['total']} completed")
                    if layer_data["failed"] > 0:
                        lines.append(f"  Failed: {layer_data['failed']}")
                    if "skipped_cached" in layer_data and layer_data["skipped_cached"] > 0:
                        lines.append(f"  Cached: {layer_data['skipped_cached']}")
                    lines.append(f"  {self._generate_progress_bar(layer_data['percent'])}")

            lines.append(f"\n{'='*60}")
            lines.append("SUMMARY:")
            lines.append(f"  Total searches: {self.progress['summary']['total_searches']}")
            lines.append(f"  Pages scraped: {self.progress['summary']['total_pages_scraped']}")
            lines.append(f"  Pages classified: {self.progress['summary']['total_pages_classified']}")
            lines.append(f"  Final results: {self.progress['summary']['final_results']}")
            lines.append(f"{'='*60}\n")

            return "\n".join(lines)

    def _generate_progress_bar(self, percent: float, width: int = 40) -> str:
        """
        Generate ASCII progress bar

        Args:
            percent: Percentage complete (0-100)
            width: Width of progress bar in characters

        Returns:
            Formatted progress bar string
        """
        filled = int(width * percent / 100)
        empty = width - filled
        bar = "█" * filled + "░" * empty
        return f"  [{bar}] {percent:.1f}%"


def load_progress(output_dir: Path) -> Optional[Dict[str, Any]]:
    """
    Load existing progress file

    Args:
        output_dir: Output directory for the run

    Returns:
        Progress dictionary or None if file doesn't exist
    """
    progress_file = Path(output_dir) / "progress.json"

    if not progress_file.exists():
        return None

    with open(progress_file, 'r') as f:
        return json.load(f)
