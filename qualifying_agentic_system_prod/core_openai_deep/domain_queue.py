"""
Domain Queue Manager for Qualifying Agentic System

Thread-safe queue for managing domain processing with concurrent workers.
Following OPTIMUS PRIME Protocol v2.0
"""

import threading
from queue import Queue, Empty
from typing import Dict, Set, Optional, Any, List
from dataclasses import dataclass
from datetime import datetime


@dataclass
class DomainTask:
    """A domain to be qualified."""
    domain: str
    company_name: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class DomainResult:
    """Result of qualifying a domain."""
    domain: str
    success: bool
    classification: Optional[str] = None
    disqualification_reason: Optional[str] = None
    answers: Optional[Dict[str, Any]] = None
    confidence: Optional[Dict[str, str]] = None
    products_found: Optional[List[str]] = None
    evidence: Optional[List[Dict]] = None
    pages_scraped: int = 0
    iterations: int = 0
    credits_used: float = 0
    tokens_used: int = 0
    duration_ms: int = 0
    error: Optional[str] = None


class DomainQueue:
    """
    Thread-safe queue for domain qualification tasks.

    Features:
    - FIFO processing with concurrent workers
    - Duplicate domain detection
    - Result collection
    - Statistics tracking
    """

    def __init__(self):
        """Initialize domain queue."""
        self.task_queue = Queue()
        self.result_queue = Queue()
        self.lock = threading.Lock()

        # Tracking sets
        self.queued_domains: Set[str] = set()
        self.completed_domains: Set[str] = set()

        # Statistics
        self.stats = {
            "total_queued": 0,
            "duplicates_skipped": 0,
            "completed": 0,
            "failed": 0,
            "in_progress": 0
        }

        # Control flags
        self.shutdown_event = threading.Event()
        self.all_tasks_added = threading.Event()

    def add_domain(self, task: DomainTask) -> bool:
        """
        Add a domain to the queue.

        Args:
            task: DomainTask with domain info

        Returns:
            True if added, False if duplicate
        """
        domain = task.domain.lower().strip()

        with self.lock:
            # Check for duplicates
            if domain in self.queued_domains:
                self.stats["duplicates_skipped"] += 1
                return False

            # Add to queue
            self.queued_domains.add(domain)
            self.stats["total_queued"] += 1

        self.task_queue.put(task)
        return True

    def add_domains_from_list(self, domains: List[Dict[str, str]]) -> int:
        """
        Add multiple domains from a list.

        Args:
            domains: List of dicts with 'domain' and optional 'company_name'

        Returns:
            Number of domains added (excluding duplicates)
        """
        added = 0
        for d in domains:
            task = DomainTask(
                domain=d.get("domain", ""),
                company_name=d.get("company_name")
            )
            if task.domain and self.add_domain(task):
                added += 1
        return added

    def get_next_task(self, timeout: float = 1.0) -> Optional[DomainTask]:
        """
        Get next domain to process.

        Args:
            timeout: How long to wait for a task (seconds)

        Returns:
            DomainTask or None if queue empty/shutdown
        """
        if self.shutdown_event.is_set():
            return None

        try:
            task = self.task_queue.get(timeout=timeout)
            with self.lock:
                self.stats["in_progress"] += 1
            return task
        except Empty:
            return None

    def submit_result(self, result: DomainResult):
        """
        Submit a completed result.

        Args:
            result: DomainResult with qualification outcome
        """
        self.result_queue.put(result)

        with self.lock:
            self.stats["in_progress"] -= 1
            self.completed_domains.add(result.domain.lower())

            if result.success:
                self.stats["completed"] += 1
            else:
                self.stats["failed"] += 1

        self.task_queue.task_done()

    def get_result(self, timeout: float = 0.1) -> Optional[DomainResult]:
        """
        Get a completed result (non-blocking).

        Args:
            timeout: How long to wait

        Returns:
            DomainResult or None
        """
        try:
            return self.result_queue.get(timeout=timeout)
        except Empty:
            return None

    def get_all_results(self) -> List[DomainResult]:
        """Get all completed results."""
        results = []
        while True:
            try:
                results.append(self.result_queue.get_nowait())
            except Empty:
                break
        return results

    def mark_all_added(self):
        """Signal that all tasks have been added."""
        self.all_tasks_added.set()

    def shutdown(self):
        """Signal workers to shut down."""
        self.shutdown_event.set()

    def is_shutdown(self) -> bool:
        """Check if shutdown was requested."""
        return self.shutdown_event.is_set()

    def is_complete(self) -> bool:
        """Check if all tasks are complete."""
        with self.lock:
            return (
                self.all_tasks_added.is_set() and
                self.task_queue.empty() and
                self.stats["in_progress"] == 0
            )

    def wait_completion(self, timeout: Optional[float] = None):
        """Wait for all tasks to complete."""
        self.task_queue.join()

    def pending_count(self) -> int:
        """Get number of pending tasks."""
        return self.task_queue.qsize()

    def get_stats(self) -> Dict[str, int]:
        """Get current statistics."""
        with self.lock:
            return {
                **self.stats,
                "pending": self.task_queue.qsize()
            }
