"""
Cost Tracking System

Tracks API costs per service and per model with real-time warnings.
Maintains costs.json file with detailed breakdowns.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
from threading import Lock


class CostTracker:
    """
    Tracks API costs across the pipeline

    Thread-safe cost tracking with automatic file writing and threshold warnings.
    """

    # API pricing (USD)
    PRICING = {
        "serper": {
            "per_query": 0.10
        },
        "firecrawl": {
            "per_page": 0.025
        },
        "claude": {
            "claude-sonnet-4-20250514": {
                "input_per_1m_tokens": 3.00,
                "output_per_1m_tokens": 15.00
            },
            "claude-opus-4-20250514": {
                "input_per_1m_tokens": 15.00,
                "output_per_1m_tokens": 75.00
            },
            "claude-sonnet-3-5-20241022": {
                "input_per_1m_tokens": 3.00,
                "output_per_1m_tokens": 15.00
            },
            "claude-opus-3-5-20241022": {
                "input_per_1m_tokens": 15.00,
                "output_per_1m_tokens": 75.00
            },
            "claude-3-5-haiku-20241022": {
                "input_per_1m_tokens": 0.80,
                "output_per_1m_tokens": 4.00
            }
        }
    }

    def __init__(self, output_dir: Path, max_cost_usd: Optional[float] = None):
        """
        Initialize cost tracker

        Args:
            output_dir: Output directory for this run
            max_cost_usd: Optional maximum cost threshold for warnings
        """
        self.output_dir = Path(output_dir)
        self.costs_file = self.output_dir / "costs.json"
        self.max_cost_usd = max_cost_usd
        self.lock = Lock()

        # Initialize costs structure
        self.costs = {
            "started_at": datetime.now().isoformat(),
            "max_cost_usd": max_cost_usd,
            "total_cost_usd": 0.0,
            "warnings": [],
            "breakdown_by_api": {
                "serper": {
                    "total_queries": 0,
                    "cost_usd": 0.0
                },
                "firecrawl": {
                    "total_pages": 0,
                    "cost_usd": 0.0
                },
                "claude": {
                    "total_requests": 0,
                    "total_input_tokens": 0,
                    "total_output_tokens": 0,
                    "cost_usd": 0.0,
                    "breakdown_by_model": {}
                }
            }
        }

        # Write initial costs file
        self._save()

    def record_serper_query(self, query_count: int = 1):
        """
        Record Serper API query cost

        Args:
            query_count: Number of queries made
        """
        with self.lock:
            cost = query_count * self.PRICING["serper"]["per_query"]

            self.costs["breakdown_by_api"]["serper"]["total_queries"] += query_count
            self.costs["breakdown_by_api"]["serper"]["cost_usd"] += cost
            self.costs["total_cost_usd"] += cost

            self._check_threshold()
            self._save()

    def record_firecrawl_scrape(self, page_count: int = 1):
        """
        Record Firecrawl API scrape cost

        Args:
            page_count: Number of pages scraped
        """
        with self.lock:
            cost = page_count * self.PRICING["firecrawl"]["per_page"]

            self.costs["breakdown_by_api"]["firecrawl"]["total_pages"] += page_count
            self.costs["breakdown_by_api"]["firecrawl"]["cost_usd"] += cost
            self.costs["total_cost_usd"] += cost

            self._check_threshold()
            self._save()

    def record_claude_request(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int
    ):
        """
        Record Claude API request cost

        Args:
            model: Model name (e.g., "claude-sonnet-4-20250514")
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
        """
        with self.lock:
            if model not in self.PRICING["claude"]:
                # Unknown model, skip cost tracking
                return

            pricing = self.PRICING["claude"][model]

            # Calculate cost
            input_cost = (input_tokens / 1_000_000) * pricing["input_per_1m_tokens"]
            output_cost = (output_tokens / 1_000_000) * pricing["output_per_1m_tokens"]
            total_cost = input_cost + output_cost

            # Update global Claude stats
            claude_data = self.costs["breakdown_by_api"]["claude"]
            claude_data["total_requests"] += 1
            claude_data["total_input_tokens"] += input_tokens
            claude_data["total_output_tokens"] += output_tokens
            claude_data["cost_usd"] += total_cost

            # Update per-model breakdown
            if model not in claude_data["breakdown_by_model"]:
                claude_data["breakdown_by_model"][model] = {
                    "requests": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost_usd": 0.0,
                    "pricing": pricing
                }

            model_data = claude_data["breakdown_by_model"][model]
            model_data["requests"] += 1
            model_data["input_tokens"] += input_tokens
            model_data["output_tokens"] += output_tokens
            model_data["cost_usd"] += total_cost

            # Update total cost
            self.costs["total_cost_usd"] += total_cost

            self._check_threshold()
            self._save()

    def get_total_cost(self) -> float:
        """
        Get current total cost

        Returns:
            Total cost in USD
        """
        with self.lock:
            return self.costs["total_cost_usd"]

    def get_costs(self) -> Dict[str, Any]:
        """
        Get complete costs data

        Returns:
            Costs dictionary
        """
        with self.lock:
            return self.costs.copy()

    def get_api_costs(self, api_name: str) -> Dict[str, Any]:
        """
        Get costs for a specific API

        Args:
            api_name: API name ("serper", "firecrawl", or "claude")

        Returns:
            API cost breakdown
        """
        with self.lock:
            return self.costs["breakdown_by_api"][api_name].copy()

    def get_warnings(self) -> list:
        """
        Get all cost warnings

        Returns:
            List of warning messages
        """
        with self.lock:
            return self.costs["warnings"].copy()

    def _check_threshold(self):
        """
        Check if cost exceeds threshold and add warning

        Must be called within lock.
        """
        if self.max_cost_usd is None:
            return

        total_cost = self.costs["total_cost_usd"]
        percent = (total_cost / self.max_cost_usd) * 100

        # Warn at 80%, 90%, 100%, 110%, etc.
        warning_thresholds = [80, 90, 100] + list(range(110, 1000, 10))

        for threshold in warning_thresholds:
            threshold_cost = (threshold / 100) * self.max_cost_usd

            # Check if we just crossed this threshold
            if total_cost >= threshold_cost:
                warning_msg = f"Cost threshold {threshold}% reached: ${total_cost:.2f} / ${self.max_cost_usd:.2f}"

                # Only add warning if not already present
                if warning_msg not in self.costs["warnings"]:
                    self.costs["warnings"].append(warning_msg)
                    break  # Only add one warning per update

    def _save(self):
        """Save costs to file (must be called within lock)"""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        with open(self.costs_file, 'w') as f:
            json.dump(self.costs, f, indent=2)

    def to_console_string(self) -> str:
        """
        Generate console-friendly cost summary

        Returns:
            Formatted cost string for console display
        """
        with self.lock:
            lines = []
            lines.append(f"\n{'='*60}")
            lines.append("COST BREAKDOWN")
            lines.append(f"{'='*60}")

            # Serper
            serper = self.costs["breakdown_by_api"]["serper"]
            lines.append(f"\nSerper.dev:")
            lines.append(f"  Queries: {serper['total_queries']}")
            lines.append(f"  Cost: ${serper['cost_usd']:.2f}")

            # Firecrawl
            firecrawl = self.costs["breakdown_by_api"]["firecrawl"]
            lines.append(f"\nFirecrawl:")
            lines.append(f"  Pages: {firecrawl['total_pages']}")
            lines.append(f"  Cost: ${firecrawl['cost_usd']:.2f}")

            # Claude
            claude = self.costs["breakdown_by_api"]["claude"]
            lines.append(f"\nClaude:")
            lines.append(f"  Requests: {claude['total_requests']}")
            lines.append(f"  Input tokens: {claude['total_input_tokens']:,}")
            lines.append(f"  Output tokens: {claude['total_output_tokens']:,}")
            lines.append(f"  Total cost: ${claude['cost_usd']:.2f}")

            # Per-model breakdown
            if claude["breakdown_by_model"]:
                lines.append(f"\n  Breakdown by model:")
                for model, data in claude["breakdown_by_model"].items():
                    lines.append(f"    {model}:")
                    lines.append(f"      Requests: {data['requests']}")
                    lines.append(f"      Tokens: {data['input_tokens']:,} in / {data['output_tokens']:,} out")
                    lines.append(f"      Cost: ${data['cost_usd']:.2f}")

            # Total
            lines.append(f"\n{'='*60}")
            lines.append(f"TOTAL COST: ${self.costs['total_cost_usd']:.2f}")

            # Show max cost if set
            if self.max_cost_usd:
                percent = (self.costs['total_cost_usd'] / self.max_cost_usd) * 100
                lines.append(f"Max cost: ${self.max_cost_usd:.2f} ({percent:.1f}% used)")

            # Show warnings
            if self.costs["warnings"]:
                lines.append(f"\nWARNINGS:")
                for warning in self.costs["warnings"]:
                    lines.append(f"  ⚠ {warning}")

            lines.append(f"{'='*60}\n")

            return "\n".join(lines)


def load_costs(output_dir: Path) -> Optional[Dict[str, Any]]:
    """
    Load existing costs file

    Args:
        output_dir: Output directory for the run

    Returns:
        Costs dictionary or None if file doesn't exist
    """
    costs_file = Path(output_dir) / "costs.json"

    if not costs_file.exists():
        return None

    with open(costs_file, 'r') as f:
        return json.load(f)
