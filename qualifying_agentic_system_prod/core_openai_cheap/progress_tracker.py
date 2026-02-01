"""
Progress Tracking System for Qualifying Agentic System

Real-time progress tracking for batch domain qualification.
Following OPTIMUS PRIME Protocol v2.0
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
from threading import Lock


class ProgressTracker:
    """
    Thread-safe progress tracking for domain qualification pipeline.

    Writes progress.json with real-time status updates.
    """

    def __init__(self, output_dir: Path, total_domains: int = 0):
        """
        Initialize progress tracker.

        Args:
            output_dir: Directory for progress.json file
            total_domains: Total number of domains to process
        """
        self.output_dir = Path(output_dir)
        self.progress_file = self.output_dir / "progress.json"
        self.lock = Lock()

        # Initialize progress structure
        self.progress = {
            "run_id": self.output_dir.name,
            "started_at": datetime.now().isoformat(),
            "status": "running",  # running, completed, failed, stopped
            "total_domains": total_domains,
            "processed": 0,
            "successful": 0,
            "failed": 0,
            "percent": 0.0,
            "current_domain": None,
            "classifications": {
                "CHEMICAL": 0,
                "PHARMA": 0,
                "ENGINEERED_MATERIALS": 0,
                "OTHER_TECHNICAL": 0,
                "DISQUALIFIED": 0,
                "INSUFFICIENT_INFO": 0
            },
            "iteration_stats": {
                "homepage_only": 0,      # Qualified on homepage
                "one_iteration": 0,      # Needed 1 extra round
                "two_iterations": 0,     # Needed 2 extra rounds
                "avg_pages_per_domain": 0.0,
                "total_pages_scraped": 0
            },
            "errors": []
        }

        self._save()

    def set_total(self, total: int):
        """Set total number of domains."""
        with self.lock:
            self.progress["total_domains"] = total
            self._save()

    def start_domain(self, domain: str):
        """Mark a domain as being processed."""
        with self.lock:
            self.progress["current_domain"] = domain
            self._save()

    def complete_domain(
        self,
        domain: str,
        classification: str,
        iterations: int,
        pages_scraped: int,
        success: bool = True,
        error: Optional[str] = None
    ):
        """
        Record domain completion.

        Args:
            domain: Domain that was processed
            classification: Final classification result
            iterations: Number of iteration rounds used (0, 1, or 2)
            pages_scraped: Total pages scraped for this domain
            success: Whether qualification succeeded
            error: Error message if failed
        """
        with self.lock:
            self.progress["processed"] += 1

            if success:
                self.progress["successful"] += 1

                # Update classification counts
                if classification in self.progress["classifications"]:
                    self.progress["classifications"][classification] += 1

                # Update iteration stats
                if iterations == 0:
                    self.progress["iteration_stats"]["homepage_only"] += 1
                elif iterations == 1:
                    self.progress["iteration_stats"]["one_iteration"] += 1
                else:
                    self.progress["iteration_stats"]["two_iterations"] += 1

                # Update page stats
                self.progress["iteration_stats"]["total_pages_scraped"] += pages_scraped
                total_successful = self.progress["successful"]
                if total_successful > 0:
                    self.progress["iteration_stats"]["avg_pages_per_domain"] = (
                        self.progress["iteration_stats"]["total_pages_scraped"] / total_successful
                    )
            else:
                self.progress["failed"] += 1
                if error:
                    self.progress["errors"].append({
                        "domain": domain,
                        "error": error,
                        "timestamp": datetime.now().isoformat()
                    })

            # Update percent
            if self.progress["total_domains"] > 0:
                self.progress["percent"] = (
                    self.progress["processed"] / self.progress["total_domains"]
                ) * 100

            self.progress["current_domain"] = None
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

    def stop_run(self, reason: str):
        """Mark the run as stopped (e.g., cost ceiling reached)."""
        with self.lock:
            self.progress["status"] = "stopped"
            self.progress["completed_at"] = datetime.now().isoformat()
            self.progress["stop_reason"] = reason
            self._save()

    def get_progress(self) -> Dict[str, Any]:
        """Get current progress data."""
        with self.lock:
            return self.progress.copy()

    def _save(self):
        """Save progress to file."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        with open(self.progress_file, 'w') as f:
            json.dump(self.progress, f, indent=2)

    def to_summary_string(self) -> str:
        """Generate console-friendly progress summary."""
        with self.lock:
            p = self.progress

            # Progress bar
            bar_width = 40
            filled = int(bar_width * p["percent"] / 100) if p["percent"] > 0 else 0
            bar = "█" * filled + "░" * (bar_width - filled)

            lines = [
                f"\n{'═'*60}",
                f"PROGRESS: {p['status'].upper()}",
                f"{'═'*60}",
                f"\n[{bar}] {p['percent']:.1f}%",
                f"\nDomains: {p['processed']}/{p['total_domains']}",
                f"  Successful: {p['successful']}",
                f"  Failed: {p['failed']}",
                f"\nClassifications:",
            ]

            for cls, count in p["classifications"].items():
                if count > 0:
                    lines.append(f"  {cls}: {count}")

            lines.extend([
                f"\nIteration Stats:",
                f"  Homepage sufficient: {p['iteration_stats']['homepage_only']}",
                f"  Needed 1 round: {p['iteration_stats']['one_iteration']}",
                f"  Needed 2 rounds: {p['iteration_stats']['two_iterations']}",
                f"  Avg pages/domain: {p['iteration_stats']['avg_pages_per_domain']:.1f}",
                f"  Total pages scraped: {p['iteration_stats']['total_pages_scraped']}",
            ])

            if p["errors"]:
                lines.append(f"\n⚠️  Errors: {len(p['errors'])}")

            lines.append(f"{'═'*60}\n")
            return "\n".join(lines)
