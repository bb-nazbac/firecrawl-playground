"""
Layer 1: Search Implementation

Searches for businesses across cities using Serper.dev API.
Outputs domains.csv ready for the qualifying pipeline.
"""

import os
import csv
import time
import requests
from datetime import datetime
from typing import List, Dict, Any
from pathlib import Path
import json
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading


class SearchLayer:
    """
    Layer 1: Search using Serper.dev API

    Performs paginated searches for each city and outputs domains.csv
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

        # Thread-safe logging and domain tracking
        self.log_lock = threading.Lock()
        self.domains_seen = set()
        self.domains_lock = threading.Lock()

    def run(self) -> Dict[str, Any]:
        """
        Execute search layer in parallel

        Returns:
            Dictionary with search results and metadata
        """
        self.logger.info(f"Searching {len(self.cities)} cities in PARALLEL...")
        self.logger.info(f"Query template: {self.config.search.query}")
        self.logger.info(f"Results per city: {self.config.search.results_per_city}")
        self.logger.info(f"Workers: 30 concurrent searches")
        self.logger.info("")

        all_results = []
        start_time = datetime.now()
        completed_count = 0

        # Run searches in parallel
        with ThreadPoolExecutor(max_workers=30) as executor:
            future_to_city = {}
            for idx, city in enumerate(self.cities, 1):
                query = self.config.search.query.replace("{city}", city)
                future = executor.submit(self._search_city_wrapper, city, query, idx)
                future_to_city[future] = city

            for future in as_completed(future_to_city):
                city = future_to_city[future]
                completed_count += 1

                try:
                    result = future.result()
                    all_results.extend(result['results'])

                    with self.log_lock:
                        self.logger.info(
                            f"[{completed_count}/{len(self.cities)}] ✓ {city}: "
                            f"{len(result['results'])} results in {result['duration']:.1f}s"
                        )

                except Exception as e:
                    with self.log_lock:
                        self.logger.error(f"[{completed_count}/{len(self.cities)}] ✗ {city}: {e}")

        # Complete layer
        total_duration = (datetime.now() - start_time).total_seconds()
        self.layer_diag.complete()
        self.progress.complete_layer("l1_search")

        # Extract unique domains and save domains.csv
        domains_data = self._extract_domains(all_results)

        # Save raw results (for debugging)
        raw_results_file = self.output_dir / "l1_search_results.json"
        with open(raw_results_file, 'w') as f:
            json.dump({
                "metadata": {
                    "query_template": self.config.search.query,
                    "cities": self.cities,
                    "total_results": len(all_results),
                    "unique_domains": len(domains_data),
                    "duration_seconds": total_duration
                },
                "results": all_results
            }, f, indent=2)

        # Save domains.csv (main output)
        domains_csv = self.output_dir / "domains.csv"
        self._save_domains_csv(domains_data, domains_csv)

        self.logger.info("")
        self.logger.info(f"✓ Layer 1 complete in {total_duration:.1f}s")
        self.logger.info(f"  Total URLs: {len(all_results)}")
        self.logger.info(f"  Unique domains: {len(domains_data)}")
        self.logger.info(f"  Output: {domains_csv}")
        self.logger.info("")

        return {
            "total_results": len(all_results),
            "unique_domains": len(domains_data),
            "domains_csv": str(domains_csv),
            "raw_results_file": str(raw_results_file)
        }

    def _extract_domains(self, results: List[Dict]) -> List[Dict]:
        """
        Extract unique domains from search results

        Args:
            results: List of search results

        Returns:
            List of unique domain records
        """
        domains_seen = set()
        domains_data = []

        for result in results:
            url = result.get('url', '')
            if not url:
                continue

            # Extract domain
            try:
                parsed = urlparse(url)
                domain = parsed.netloc.lower()

                # Remove www. prefix for consistency
                if domain.startswith('www.'):
                    domain = domain[4:]

                # Skip if already seen
                if domain in domains_seen:
                    continue

                domains_seen.add(domain)

                domains_data.append({
                    'domain': domain,
                    'url': url,
                    'city': result.get('city', ''),
                    'title': result.get('title', ''),
                    'snippet': result.get('snippet', ''),
                    'position': result.get('position', 0),
                    'query': result.get('query', '')
                })

            except Exception:
                continue

        return domains_data

    def _save_domains_csv(self, domains_data: List[Dict], output_path: Path):
        """
        Save domains to CSV file

        Args:
            domains_data: List of domain records
            output_path: Path to output CSV file
        """
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'domain', 'url', 'city', 'title', 'snippet', 'position', 'query'
            ])
            writer.writeheader()
            writer.writerows(domains_data)

    def _search_city_wrapper(self, city: str, query: str, idx: int) -> Dict[str, Any]:
        """
        Wrapper for parallel city search with timing and error handling

        Args:
            city: City name
            query: Search query string
            idx: City index number

        Returns:
            Dictionary with results and metadata
        """
        city_start = datetime.now()

        try:
            results = self._search_city(query, city)

            duration = (datetime.now() - city_start).total_seconds()
            self.layer_diag.record_success(
                item_id=city,
                duration_seconds=duration,
                metadata={"city": city, "results_count": len(results)}
            )

            self.progress.increment_progress("l1_search", completed=1)

            return {
                'results': results,
                'duration': duration,
                'city': city
            }

        except Exception as e:
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
            raise

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
                "gl": self.config.search.gl,
                "hl": "en",
                "num": 10,
                "page": page
            }

            try:
                response = requests.post(url, json=payload, headers=headers, timeout=10)

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

            except requests.exceptions.Timeout:
                self.logger.warning(f"    Timeout on page {page}, retrying...")
                time.sleep(2)
                continue

        return all_results[:self.config.search.results_per_city]
