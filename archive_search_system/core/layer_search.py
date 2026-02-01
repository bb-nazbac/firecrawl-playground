"""
Layer 1: Search Implementation

Integrates Serper.dev API with production tracking systems.
"""

import os
import time
import requests
from datetime import datetime
from typing import List, Dict, Any
from pathlib import Path
import json


class SearchLayer:
    """
    Layer 1: Search using Serper.dev API

    Performs paginated searches for each city and tracks all metrics.
    """

    def __init__(self, config, progress, costs, diagnostics, logger, output_dir):
        """
        Initialize search layer

        Args:
            config: RunConfig object
            progress: ProgressTracker instance
            costs: CostTracker instance
            diagnostics: DiagnosticsManager instance
            logger: Logger instance
            output_dir: Output directory path
        """
        self.config = config
        self.progress = progress
        self.costs = costs
        self.diagnostics = diagnostics
        self.logger = logger
        self.output_dir = Path(output_dir)

        # Get API key
        self.api_key = os.getenv('SERP_API_KEY')
        if not self.api_key:
            raise ValueError("SERP_API_KEY not found in environment variables")

        # Setup layer diagnostics
        self.layer_diag = self.diagnostics.get_layer("search", 1)

        # Determine cities to search
        self.cities = self.config.search.cities
        if self.config.test_mode:
            self.logger.info(f"Test mode: limiting to first {self.config.test_mode} cities")
            self.cities = self.cities[:self.config.test_mode]

        self.layer_diag.set_total_items(len(self.cities))
        self.progress.start_layer("l1_search", total_items=len(self.cities))

    def run(self) -> Dict[str, Any]:
        """
        Execute search layer

        Returns:
            Dictionary with search results and metadata
        """
        self.logger.info(f"Searching {len(self.cities)} cities...")
        self.logger.info(f"Query template: {self.config.search.query}")
        self.logger.info(f"Results per city: {self.config.search.results_per_city}")
        self.logger.info("")

        all_results = []
        start_time = datetime.now()

        for idx, city in enumerate(self.cities, 1):
            city_start = datetime.now()

            # Format query for this city
            query = self.config.search.query.replace("{city}", city)

            self.logger.info(f"[{idx}/{len(self.cities)}] Searching: {city}")
            self.logger.info(f"  Query: {query}")

            try:
                # Perform search
                results = self._search_city(query, city)

                # Record success
                duration = (datetime.now() - city_start).total_seconds()
                self.layer_diag.record_success(
                    item_id=city,
                    duration_seconds=duration,
                    metadata={"city": city, "results_count": len(results)}
                )

                all_results.extend(results)

                self.progress.increment_progress("l1_search", completed=1)
                self.logger.info(f"  ✓ Found {len(results)} results in {duration:.1f}s")
                self.logger.info("")

            except Exception as e:
                # Record failure
                duration = (datetime.now() - city_start).total_seconds()
                self.layer_diag.record_failure(
                    item_id=city,
                    error_type="search_error",
                    error_message=str(e),
                    retry_count=0,
                    can_retry=True,
                    duration_seconds=duration,
                    metadata={"city": city, "query": query}
                )

                self.progress.increment_progress("l1_search", failed=1)
                self.logger.error(f"  ✗ Error: {e}")
                self.logger.info("")

        # Complete layer
        total_duration = (datetime.now() - start_time).total_seconds()
        self.layer_diag.complete()
        self.progress.complete_layer("l1_search")

        # Save results
        results_file = self.output_dir / "l1_search_results.json"
        with open(results_file, 'w') as f:
            json.dump({
                "metadata": {
                    "query_template": self.config.search.query,
                    "cities": self.cities,
                    "total_results": len(all_results),
                    "duration_seconds": total_duration
                },
                "results": all_results
            }, f, indent=2)

        self.logger.info(f"✓ Layer 1 complete: {len(all_results)} total results")
        self.logger.info(f"  Saved to: {results_file}")
        self.logger.info("")

        return {
            "total_results": len(all_results),
            "results_file": str(results_file)
        }

    def _search_city(self, query: str, city: str) -> List[Dict[str, Any]]:
        """
        Search for a single city with pagination

        Args:
            query: Search query string
            city: City name

        Returns:
            List of search results
        """
        url = "https://google.serper.dev/search"
        headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json"
        }

        all_results = []
        page = 1
        pages_needed = min((self.config.search.results_per_city + 9) // 10, 25)

        while page <= pages_needed and len(all_results) < self.config.search.results_per_city:
            payload = {
                "q": query,
                "gl": "us",
                "hl": "en",
                "num": 10,
                "page": page
            }

            try:
                response = requests.post(url, json=payload, headers=headers, timeout=10)

                if response.status_code == 429:
                    self.logger.warning(f"    Rate limited, waiting 5s...")
                    time.sleep(5)
                    continue

                if response.status_code != 200:
                    raise Exception(f"HTTP {response.status_code}")

                data = response.json()

                if 'error' in data:
                    raise Exception(f"API Error: {data['error']}")

                organic = data.get('organic', [])

                if not organic:
                    break

                # Record cost
                self.costs.record_serper_query(1)

                for item in organic:
                    all_results.append({
                        'position': item.get('position'),
                        'title': item.get('title'),
                        'url': item.get('link'),
                        'snippet': item.get('snippet'),
                        'city': city,
                        'query': query
                    })

                page += 1
                time.sleep(0.3)  # Rate limiting

            except requests.exceptions.Timeout:
                self.logger.warning(f"    Timeout on page {page}, retrying...")
                time.sleep(2)
                continue

        return all_results[:self.config.search.results_per_city]
