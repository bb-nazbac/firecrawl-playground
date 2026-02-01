"""
Cost Tracking System for Qualifying Agentic System (OpenAI Version)

Tracks API costs per service with real-time warnings and file persistence.
Following OPTIMUS PRIME Protocol v2.0
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
from threading import Lock


class CostTracker:
    """
    Thread-safe cost tracking for Firecrawl and OpenAI APIs.

    Maintains costs.json file with detailed breakdowns and threshold warnings.
    """

    # API pricing (USD) - Updated January 2025
    PRICING = {
        "firecrawl": {
            "map": 0.001,      # 1 credit per map
            "scrape": 0.001    # 1 credit per scrape
        },
        "openai": {
            "gpt-5-mini": {
                "input_per_1m_tokens": 0.25,
                "output_per_1m_tokens": 2.00
            },
            "gpt-4o": {
                "input_per_1m_tokens": 2.50,
                "output_per_1m_tokens": 10.00
            },
            "gpt-4o-mini": {
                "input_per_1m_tokens": 0.15,
                "output_per_1m_tokens": 0.60
            },
            "gpt-4-turbo": {
                "input_per_1m_tokens": 10.00,
                "output_per_1m_tokens": 30.00
            }
        }
    }

    def __init__(self, output_dir: Path, max_cost_usd: Optional[float] = None):
        """
        Initialize cost tracker.

        Args:
            output_dir: Directory for costs.json file
            max_cost_usd: Optional cost ceiling for warnings/stopping
        """
        self.output_dir = Path(output_dir)
        self.costs_file = self.output_dir / "costs.json"
        self.max_cost_usd = max_cost_usd
        self.lock = Lock()
        self._exceeded_threshold = False

        # Initialize cost structure
        self.costs = {
            "started_at": datetime.now().isoformat(),
            "max_cost_usd": max_cost_usd,
            "total_cost_usd": 0.0,
            "total_credits": 0,
            "warnings": [],
            "breakdown": {
                "firecrawl": {
                    "map_calls": 0,
                    "scrape_calls": 0,
                    "total_credits": 0,
                    "cost_usd": 0.0
                },
                "openai": {
                    "total_requests": 0,
                    "total_input_tokens": 0,
                    "total_output_tokens": 0,
                    "cost_usd": 0.0,
                    "by_model": {}
                }
            },
            "per_domain": {}
        }

        self._save()

    def record_firecrawl_map(self, domain: str, credits: int = 1):
        """Record a Firecrawl map API call."""
        with self.lock:
            cost = credits * self.PRICING["firecrawl"]["map"]

            self.costs["breakdown"]["firecrawl"]["map_calls"] += 1
            self.costs["breakdown"]["firecrawl"]["total_credits"] += credits
            self.costs["breakdown"]["firecrawl"]["cost_usd"] += cost
            self.costs["total_cost_usd"] += cost
            self.costs["total_credits"] += credits

            # Track per-domain
            if domain not in self.costs["per_domain"]:
                self.costs["per_domain"][domain] = {"credits": 0, "cost_usd": 0.0}
            self.costs["per_domain"][domain]["credits"] += credits
            self.costs["per_domain"][domain]["cost_usd"] += cost

            self._check_threshold()
            self._save()

    def record_firecrawl_scrape(self, domain: str, credits: int = 1):
        """Record a Firecrawl scrape API call."""
        with self.lock:
            cost = credits * self.PRICING["firecrawl"]["scrape"]

            self.costs["breakdown"]["firecrawl"]["scrape_calls"] += 1
            self.costs["breakdown"]["firecrawl"]["total_credits"] += credits
            self.costs["breakdown"]["firecrawl"]["cost_usd"] += cost
            self.costs["total_cost_usd"] += cost
            self.costs["total_credits"] += credits

            # Track per-domain
            if domain not in self.costs["per_domain"]:
                self.costs["per_domain"][domain] = {"credits": 0, "cost_usd": 0.0}
            self.costs["per_domain"][domain]["credits"] += credits
            self.costs["per_domain"][domain]["cost_usd"] += cost

            self._check_threshold()
            self._save()

    def record_openai_request(
        self,
        domain: str,
        model: str,
        input_tokens: int,
        output_tokens: int
    ):
        """Record an OpenAI API request."""
        with self.lock:
            if model not in self.PRICING["openai"]:
                # Unknown model - estimate with gpt-5-mini pricing
                model = "gpt-5-mini"

            pricing = self.PRICING["openai"][model]
            input_cost = (input_tokens / 1_000_000) * pricing["input_per_1m_tokens"]
            output_cost = (output_tokens / 1_000_000) * pricing["output_per_1m_tokens"]
            total_cost = input_cost + output_cost

            # Update OpenAI totals
            openai = self.costs["breakdown"]["openai"]
            openai["total_requests"] += 1
            openai["total_input_tokens"] += input_tokens
            openai["total_output_tokens"] += output_tokens
            openai["cost_usd"] += total_cost

            # Update per-model breakdown
            if model not in openai["by_model"]:
                openai["by_model"][model] = {
                    "requests": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost_usd": 0.0
                }
            openai["by_model"][model]["requests"] += 1
            openai["by_model"][model]["input_tokens"] += input_tokens
            openai["by_model"][model]["output_tokens"] += output_tokens
            openai["by_model"][model]["cost_usd"] += total_cost

            # Update totals
            self.costs["total_cost_usd"] += total_cost

            # Track per-domain
            if domain not in self.costs["per_domain"]:
                self.costs["per_domain"][domain] = {"credits": 0, "cost_usd": 0.0}
            self.costs["per_domain"][domain]["cost_usd"] += total_cost

            self._check_threshold()
            self._save()

    def get_total_cost(self) -> float:
        """Get current total cost in USD."""
        with self.lock:
            return self.costs["total_cost_usd"]

    def get_total_credits(self) -> int:
        """Get total Firecrawl credits used."""
        with self.lock:
            return self.costs["total_credits"]

    def is_over_budget(self) -> bool:
        """Check if we've exceeded the cost ceiling."""
        with self.lock:
            return self._exceeded_threshold

    def get_domain_cost(self, domain: str) -> Dict[str, Any]:
        """Get cost breakdown for a specific domain."""
        with self.lock:
            return self.costs["per_domain"].get(domain, {"credits": 0, "cost_usd": 0.0})

    def _check_threshold(self):
        """Check if cost exceeds threshold and add warning."""
        if self.max_cost_usd is None:
            return

        total = self.costs["total_cost_usd"]
        percent = (total / self.max_cost_usd) * 100

        # Warn at 80%, 90%, 100%
        for threshold in [80, 90, 100]:
            if percent >= threshold:
                warning = f"Cost threshold {threshold}% reached: ${total:.2f} / ${self.max_cost_usd:.2f}"
                if warning not in self.costs["warnings"]:
                    self.costs["warnings"].append(warning)
                    if threshold >= 100:
                        self._exceeded_threshold = True
                    break

    def _save(self):
        """Save costs to file."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        with open(self.costs_file, 'w') as f:
            json.dump(self.costs, f, indent=2)

    def to_summary_string(self) -> str:
        """Generate console-friendly cost summary."""
        with self.lock:
            lines = [
                f"\n{'═'*60}",
                "COST SUMMARY",
                f"{'═'*60}",
                f"\nFirecrawl:",
                f"  Map calls: {self.costs['breakdown']['firecrawl']['map_calls']}",
                f"  Scrape calls: {self.costs['breakdown']['firecrawl']['scrape_calls']}",
                f"  Total credits: {self.costs['breakdown']['firecrawl']['total_credits']}",
                f"  Cost: ${self.costs['breakdown']['firecrawl']['cost_usd']:.2f}",
                f"\nOpenAI:",
                f"  Requests: {self.costs['breakdown']['openai']['total_requests']}",
                f"  Input tokens: {self.costs['breakdown']['openai']['total_input_tokens']:,}",
                f"  Output tokens: {self.costs['breakdown']['openai']['total_output_tokens']:,}",
                f"  Cost: ${self.costs['breakdown']['openai']['cost_usd']:.2f}",
                f"\n{'═'*60}",
                f"TOTAL: ${self.costs['total_cost_usd']:.2f} ({self.costs['total_credits']} credits)"
            ]

            if self.max_cost_usd:
                percent = (self.costs['total_cost_usd'] / self.max_cost_usd) * 100
                lines.append(f"Budget: ${self.max_cost_usd:.2f} ({percent:.1f}% used)")

            if self.costs["warnings"]:
                lines.append(f"\n⚠️  WARNINGS:")
                for w in self.costs["warnings"]:
                    lines.append(f"  {w}")

            lines.append(f"{'═'*60}\n")
            return "\n".join(lines)
