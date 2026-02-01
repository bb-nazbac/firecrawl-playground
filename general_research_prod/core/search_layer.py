"""
Search Layer - Serper.dev Integration

Adapted from search_system_prod/core/layer_search.py.
Generalized to iterate over arbitrary query lists (not just city-based).
"""

import os
import csv
import time
import json
import requests
import threading
from datetime import datetime
from typing import List, Dict, Any
from pathlib import Path
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed


SERPER_COST_PER_QUERY = 0.001  # $0.001 per query


class SearchLayer:
    """
    Search using Serper.dev API.

    Performs paginated searches for each query and outputs domains.csv.
    """

    def __init__(self, queries: List[str], results_per_query: int, gl: str,
                 concurrency: int, output_dir: Path, logger, test_mode: int = None):
        self.queries = queries
        self.results_per_query = results_per_query
        self.gl = gl
        self.concurrency = concurrency
        self.output_dir = Path(output_dir)
        self.logger = logger

        if test_mode:
            self.logger.info(f"Test mode: limiting to first {test_mode} queries")
            self.queries = self.queries[:test_mode]

        self.api_key = os.getenv('SERP_API_KEY')
        if not self.api_key:
            raise ValueError("SERP_API_KEY not found in environment variables")

        self.log_lock = threading.Lock()
        self.total_api_calls = 0
        self.api_calls_lock = threading.Lock()

    def run(self) -> Dict[str, Any]:
        """
        Execute search layer in parallel.

        Returns:
            Dict with total_results, unique_domains, domains_csv path, cost_usd
        """
        self.logger.info(f"Searching {len(self.queries)} queries in parallel...")
        self.logger.info(f"Results per query: {self.results_per_query}")
        self.logger.info(f"Workers: {self.concurrency}")
        self.logger.info("")

        all_results = []
        start_time = datetime.now()
        completed = 0

        with ThreadPoolExecutor(max_workers=self.concurrency) as executor:
            future_to_query = {}
            for idx, query in enumerate(self.queries, 1):
                future = executor.submit(self._search_query, query, idx)
                future_to_query[future] = query

            for future in as_completed(future_to_query):
                query = future_to_query[future]
                completed += 1
                try:
                    result = future.result()
                    all_results.extend(result['results'])
                    with self.log_lock:
                        self.logger.info(
                            f"[{completed}/{len(self.queries)}] {query[:60]}... "
                            f"→ {len(result['results'])} results ({result['duration']:.1f}s)"
                        )
                except Exception as e:
                    with self.log_lock:
                        self.logger.error(f"[{completed}/{len(self.queries)}] FAILED: {query[:60]}... → {e}")

        duration = (datetime.now() - start_time).total_seconds()

        # Extract unique domains
        domains_data = self._extract_domains(all_results)

        # Save raw results
        raw_path = self.output_dir / "1_search_results.json"
        with open(raw_path, 'w') as f:
            json.dump({
                "metadata": {
                    "queries": self.queries,
                    "total_results": len(all_results),
                    "unique_domains": len(domains_data),
                    "duration_seconds": duration,
                    "api_calls": self.total_api_calls,
                    "cost_usd": self.total_api_calls * SERPER_COST_PER_QUERY,
                },
                "results": all_results
            }, f, indent=2)

        # Save domains.csv
        csv_path = self.output_dir / "2_domains.csv"
        self._save_domains_csv(domains_data, csv_path)

        cost = self.total_api_calls * SERPER_COST_PER_QUERY

        self.logger.info("")
        self.logger.info(f"Search complete in {duration:.1f}s")
        self.logger.info(f"  Total URLs: {len(all_results)}")
        self.logger.info(f"  Unique domains: {len(domains_data)}")
        self.logger.info(f"  API calls: {self.total_api_calls}")
        self.logger.info(f"  Search cost: ${cost:.4f}")
        self.logger.info(f"  Output: {csv_path}")

        return {
            "total_results": len(all_results),
            "unique_domains": len(domains_data),
            "domains_csv": str(csv_path),
            "cost_usd": cost,
            "duration_seconds": duration,
        }

    def _search_query(self, query: str, idx: int) -> Dict[str, Any]:
        """Search a single query with pagination."""
        start = datetime.now()
        results = self._paginated_search(query)
        duration = (datetime.now() - start).total_seconds()
        return {'results': results, 'duration': duration, 'query': query}

    def _paginated_search(self, query: str) -> List[Dict]:
        """Execute paginated Serper search for a single query."""
        url = "https://google.serper.dev/search"
        headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json"
        }

        all_results = []
        page = 1
        pages_needed = min((self.results_per_query + 9) // 10, 25)

        while page <= pages_needed and len(all_results) < self.results_per_query:
            payload = {
                "q": query,
                "gl": self.gl,
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

                with self.api_calls_lock:
                    self.total_api_calls += 1

                for item in organic:
                    all_results.append({
                        'position': item.get('position'),
                        'title': item.get('title'),
                        'url': item.get('link'),
                        'snippet': item.get('snippet'),
                        'query': query,
                    })

                page += 1

            except requests.exceptions.Timeout:
                time.sleep(2)
                continue

        return all_results[:self.results_per_query]

    def _extract_domains(self, results: List[Dict]) -> List[Dict]:
        """Extract unique domains from search results."""
        seen = set()
        domains = []

        for r in results:
            url = r.get('url', '')
            if not url:
                continue
            try:
                parsed = urlparse(url)
                domain = parsed.netloc.lower()
                if domain.startswith('www.'):
                    domain = domain[4:]
                if domain in seen:
                    continue
                seen.add(domain)
                domains.append({
                    'domain': domain,
                    'url': url,
                    'title': r.get('title', ''),
                    'snippet': r.get('snippet', ''),
                    'position': r.get('position', 0),
                    'query': r.get('query', ''),
                })
            except Exception:
                continue

        return domains

    def _save_domains_csv(self, domains_data: List[Dict], output_path: Path):
        """Save domains to CSV."""
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'domain', 'url', 'title', 'snippet', 'position', 'query'
            ])
            writer.writeheader()
            writer.writerows(domains_data)
