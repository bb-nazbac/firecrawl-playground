#!/usr/bin/env python3
"""
Pipeline Analytics Module

Provides real-time tracking of:
- Concurrency utilization (Firecrawl + LLM active workers)
- Latency percentiles (P50, P95, P99)
- Throughput metrics
- Error rates
- Queue depth

Outputs:
- analytics.jsonl: Time-series data every second
- Analytics summary in summary.json
"""

import json
import time
import threading
import statistics
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from collections import deque


@dataclass
class AnalyticsSnapshot:
    """Single point-in-time analytics snapshot"""
    timestamp: str
    elapsed_seconds: float

    # Concurrency
    firecrawl_active: int
    firecrawl_limit: int
    firecrawl_utilization_pct: float
    openai_active: int
    openai_limit: int
    openai_utilization_pct: float

    # Throughput (domains processed)
    domains_processed: int
    domains_per_minute: float

    # Queue depth (estimated from concurrency)
    domains_in_flight: int


@dataclass
class LatencyStats:
    """Latency statistics for a single operation type"""
    count: int = 0
    min_ms: float = 0
    max_ms: float = 0
    mean_ms: float = 0
    p50_ms: float = 0
    p95_ms: float = 0
    p99_ms: float = 0


@dataclass
class AnalyticsSummary:
    """Final analytics summary for the run"""
    # Duration
    start_time: str = ""
    end_time: str = ""
    duration_seconds: float = 0

    # Concurrency peaks
    firecrawl_peak_active: int = 0
    firecrawl_avg_active: float = 0
    firecrawl_avg_utilization_pct: float = 0
    openai_peak_active: int = 0
    openai_avg_active: float = 0
    openai_avg_utilization_pct: float = 0

    # Throughput
    total_domains: int = 0
    domains_per_minute: float = 0
    domains_per_hour: float = 0

    # Latency - Scrape
    scrape_latency: Dict = field(default_factory=dict)

    # Latency - LLM
    llm_latency: Dict = field(default_factory=dict)

    # Latency - Total per domain
    domain_latency: Dict = field(default_factory=dict)

    # Errors
    scrape_errors: int = 0
    llm_errors: int = 0
    error_rate_pct: float = 0

    # Rate limits
    rate_limit_hits: int = 0
    overload_hits: int = 0


class PipelineAnalytics:
    """
    Real-time analytics tracker for the pipeline.

    Thread-safe tracking of concurrency, latency, and throughput.
    """

    def __init__(
        self,
        output_dir: Path,
        firecrawl_limit: int = 50,
        openai_limit: int = 30,
        snapshot_interval: float = 1.0  # seconds
    ):
        self.output_dir = Path(output_dir)
        self.firecrawl_limit = firecrawl_limit
        self.openai_limit = openai_limit
        self.snapshot_interval = snapshot_interval

        # Thread safety
        self._lock = threading.Lock()

        # Timing
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None

        # Active worker counts
        self._firecrawl_active = 0
        self._openai_active = 0

        # Latency tracking (store individual measurements)
        self._scrape_latencies: List[float] = []  # in ms
        self._llm_latencies: List[float] = []  # in ms
        self._domain_latencies: List[float] = []  # in ms

        # Error tracking
        self._scrape_errors = 0
        self._llm_errors = 0

        # Rate limit tracking
        self._rate_limit_hits = 0
        self._overload_hits = 0

        # Domain processing
        self._domains_processed = 0

        # Snapshot history for averages
        self._snapshots: List[AnalyticsSnapshot] = []

        # Peak tracking
        self._firecrawl_peak = 0
        self._openai_peak = 0

        # Output file
        self.analytics_path = self.output_dir / "analytics.jsonl"

        # Background thread for snapshots
        self._running = False
        self._snapshot_thread: Optional[threading.Thread] = None

    def start(self):
        """Start analytics collection."""
        self.start_time = time.time()
        self._running = True

        # Clear analytics file
        with open(self.analytics_path, 'w') as f:
            pass

        # Start snapshot thread
        self._snapshot_thread = threading.Thread(target=self._snapshot_loop, daemon=True)
        self._snapshot_thread.start()

    def stop(self):
        """Stop analytics collection."""
        self._running = False
        self.end_time = time.time()
        if self._snapshot_thread:
            self._snapshot_thread.join(timeout=2.0)

    def _snapshot_loop(self):
        """Background thread that takes snapshots every interval."""
        while self._running:
            self._take_snapshot()
            time.sleep(self.snapshot_interval)

    def _take_snapshot(self):
        """Take a single analytics snapshot."""
        with self._lock:
            if self.start_time is None:
                return

            elapsed = time.time() - self.start_time
            domains_per_minute = (self._domains_processed / elapsed * 60) if elapsed > 0 else 0

            snapshot = AnalyticsSnapshot(
                timestamp=datetime.now().isoformat(),
                elapsed_seconds=round(elapsed, 1),
                firecrawl_active=self._firecrawl_active,
                firecrawl_limit=self.firecrawl_limit,
                firecrawl_utilization_pct=round(self._firecrawl_active / self.firecrawl_limit * 100, 1),
                openai_active=self._openai_active,
                openai_limit=self.openai_limit,
                openai_utilization_pct=round(self._openai_active / self.openai_limit * 100, 1),
                domains_processed=self._domains_processed,
                domains_per_minute=round(domains_per_minute, 2),
                domains_in_flight=self._firecrawl_active + self._openai_active
            )

            self._snapshots.append(snapshot)

            # Update peaks
            if self._firecrawl_active > self._firecrawl_peak:
                self._firecrawl_peak = self._firecrawl_active
            if self._openai_active > self._openai_peak:
                self._openai_peak = self._openai_active

        # Write to file (outside lock)
        with open(self.analytics_path, 'a') as f:
            f.write(json.dumps(asdict(snapshot)) + '\n')

    # ─────────────────────────────────────────────────────────
    # CONCURRENCY TRACKING
    # ─────────────────────────────────────────────────────────

    def firecrawl_start(self):
        """Called when a Firecrawl request starts."""
        with self._lock:
            self._firecrawl_active += 1
            if self._firecrawl_active > self._firecrawl_peak:
                self._firecrawl_peak = self._firecrawl_active

    def firecrawl_end(self, duration_ms: float, error: bool = False):
        """Called when a Firecrawl request ends."""
        with self._lock:
            self._firecrawl_active = max(0, self._firecrawl_active - 1)
            self._scrape_latencies.append(duration_ms)
            if error:
                self._scrape_errors += 1

    def openai_start(self):
        """Called when an OpenAI request starts."""
        with self._lock:
            self._openai_active += 1
            if self._openai_active > self._openai_peak:
                self._openai_peak = self._openai_active

    def openai_end(self, duration_ms: float, error: bool = False):
        """Called when an OpenAI request ends."""
        with self._lock:
            self._openai_active = max(0, self._openai_active - 1)
            self._llm_latencies.append(duration_ms)
            if error:
                self._llm_errors += 1

    def domain_complete(self, duration_ms: float):
        """Called when a domain is fully processed."""
        with self._lock:
            self._domains_processed += 1
            self._domain_latencies.append(duration_ms)

    # ─────────────────────────────────────────────────────────
    # RATE LIMIT TRACKING
    # ─────────────────────────────────────────────────────────

    def record_rate_limit(self):
        """Called when OpenAI returns 429 rate limit error (even if retrying)."""
        with self._lock:
            self._rate_limit_hits += 1

    def record_overload(self):
        """Called when OpenAI returns 503 overloaded error (even if retrying)."""
        with self._lock:
            self._overload_hits += 1

    # ─────────────────────────────────────────────────────────
    # SUMMARY GENERATION
    # ─────────────────────────────────────────────────────────

    def _calculate_percentiles(self, values: List[float]) -> LatencyStats:
        """Calculate latency statistics from a list of values."""
        if not values:
            return LatencyStats()

        sorted_values = sorted(values)
        n = len(sorted_values)

        return LatencyStats(
            count=n,
            min_ms=round(min(values), 1),
            max_ms=round(max(values), 1),
            mean_ms=round(statistics.mean(values), 1),
            p50_ms=round(sorted_values[int(n * 0.50)], 1),
            p95_ms=round(sorted_values[int(n * 0.95)] if n > 1 else sorted_values[-1], 1),
            p99_ms=round(sorted_values[int(n * 0.99)] if n > 1 else sorted_values[-1], 1)
        )

    def get_summary(self) -> AnalyticsSummary:
        """Generate final analytics summary."""
        with self._lock:
            duration = (self.end_time or time.time()) - (self.start_time or time.time())

            # Calculate averages from snapshots
            if self._snapshots:
                avg_firecrawl = statistics.mean(s.firecrawl_active for s in self._snapshots)
                avg_firecrawl_util = statistics.mean(s.firecrawl_utilization_pct for s in self._snapshots)
                avg_openai = statistics.mean(s.openai_active for s in self._snapshots)
                avg_openai_util = statistics.mean(s.openai_utilization_pct for s in self._snapshots)
            else:
                avg_firecrawl = avg_firecrawl_util = avg_openai = avg_openai_util = 0

            # Calculate throughput
            domains_per_minute = (self._domains_processed / duration * 60) if duration > 0 else 0
            domains_per_hour = domains_per_minute * 60

            # Calculate error rate
            total_scrapes = len(self._scrape_latencies) + self._scrape_errors
            error_rate = (self._scrape_errors / total_scrapes * 100) if total_scrapes > 0 else 0

            return AnalyticsSummary(
                start_time=datetime.fromtimestamp(self.start_time).isoformat() if self.start_time else "",
                end_time=datetime.fromtimestamp(self.end_time).isoformat() if self.end_time else "",
                duration_seconds=round(duration, 1),

                firecrawl_peak_active=self._firecrawl_peak,
                firecrawl_avg_active=round(avg_firecrawl, 1),
                firecrawl_avg_utilization_pct=round(avg_firecrawl_util, 1),
                openai_peak_active=self._openai_peak,
                openai_avg_active=round(avg_openai, 1),
                openai_avg_utilization_pct=round(avg_openai_util, 1),

                total_domains=self._domains_processed,
                domains_per_minute=round(domains_per_minute, 2),
                domains_per_hour=round(domains_per_hour, 1),

                scrape_latency=asdict(self._calculate_percentiles(self._scrape_latencies)),
                llm_latency=asdict(self._calculate_percentiles(self._llm_latencies)),
                domain_latency=asdict(self._calculate_percentiles(self._domain_latencies)),

                scrape_errors=self._scrape_errors,
                llm_errors=self._llm_errors,
                error_rate_pct=round(error_rate, 2),

                rate_limit_hits=self._rate_limit_hits,
                overload_hits=self._overload_hits
            )

    def get_summary_dict(self) -> Dict:
        """Get summary as a dictionary for JSON serialization."""
        return asdict(self.get_summary())
