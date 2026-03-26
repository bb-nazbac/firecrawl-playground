import os
import csv
import time
import json
import requests
import threading
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

from stages.base import BaseStage


class SearchStage(BaseStage):
    STAGE_NAME = "search"

    def __init__(self, config, spec, analytics, output, logger, queue=None):
        super().__init__(config, spec, analytics, output, logger)
        self.queue = queue  # Optional StageQueue for streaming mode
        self.api_key = os.environ.get('SERP_API_KEY')
        if not self.api_key:
            raise ValueError("SERP_API_KEY not found")

    def run(self, input_data=None) -> Dict[str, Any]:
        """Execute search. input_data is ignored (config drives everything)."""
        mode = self.config.get('mode', 'query_list')

        if mode == 'geo':
            queries = self._expand_geo_queries()
        else:
            queries = self.config.get('queries', [])

        results_per = self.config.get('results_per_query') or self.config.get('results_per_city', 100)
        concurrency = self.config.get('concurrency', 30)
        gl = self.config.get('gl', 'us')

        self.analytics.start_stage("search", total_items=len(queries))

        # Run parallel searches
        all_results = []
        completed = 0
        log_lock = threading.Lock()
        api_calls = 0
        api_lock = threading.Lock()

        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = {}
            for idx, query in enumerate(queries, 1):
                future = executor.submit(
                    self._search_query, query, results_per, gl
                )
                futures[future] = query

            for future in as_completed(futures):
                query = futures[future]
                completed += 1
                try:
                    result = future.result()
                    all_results.extend(result['results'])

                    with api_lock:
                        api_calls += result['api_calls']

                    # Record cost
                    self.analytics.record_api_cost("serper", credits=result['api_calls'])
                    self.analytics.increment_progress("search", completed=1)
                    self.analytics.record_success("search", query[:60], result['duration'])

                    with log_lock:
                        self.logger.info(
                            f"[{completed}/{len(queries)}] {query[:60]}... -> {len(result['results'])} results"
                        )

                    # If streaming, feed domains to queue immediately
                    if self.queue:
                        domains = self._extract_domains(result['results'])
                        self.queue.put_batch([d for d in domains])

                except Exception as e:
                    self.analytics.increment_progress("search", failed=1)
                    self.analytics.record_failure("search", query[:60], "search_error", str(e), 0)
                    with log_lock:
                        self.logger.error(f"[{completed}/{len(queries)}] FAILED: {query[:60]}... -> {e}")

        self.analytics.complete_stage("search")

        # Extract all unique domains
        domains = self._extract_domains(all_results)

        # Save outputs
        self.output.save_stage_output("search_results", {
            "metadata": {
                "queries_count": len(queries),
                "total_results": len(all_results),
                "unique_domains": len(domains),
                "api_calls": api_calls,
            },
            "results": all_results
        })
        self.output.save_domains_csv(domains)

        self.logger.info(f"Search complete: {len(all_results)} results, {len(domains)} unique domains")

        return {
            "domains": domains,
            "total_results": len(all_results),
            "unique_domains": len(domains),
        }

    def _expand_geo_queries(self) -> List[str]:
        template = self.config.get('query_template', '')
        cities = self.config.get('cities', [])
        return [template.replace('{city}', city) for city in cities]

    def _search_query(self, query, num_results, gl) -> dict:
        start = time.time()
        results = []
        page = 1
        pages_needed = min((num_results + 9) // 10, 25)
        calls = 0

        while page <= pages_needed and len(results) < num_results:
            try:
                response = requests.post(
                    "https://google.serper.dev/search",
                    headers={"X-API-KEY": self.api_key, "Content-Type": "application/json"},
                    json={"q": query, "gl": gl, "hl": "en", "num": 10, "page": page},
                    timeout=10
                )
                if response.status_code != 200:
                    raise Exception(f"HTTP {response.status_code}")
                data = response.json()
                if 'error' in data:
                    raise Exception(f"API Error: {data['error']}")
                organic = data.get('organic', [])
                if not organic:
                    break
                calls += 1
                for item in organic:
                    results.append({
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

        return {
            'results': results[:num_results],
            'duration': time.time() - start,
            'api_calls': calls,
        }

    def _extract_domains(self, results) -> List[dict]:
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
                    'query': r.get('query', ''),
                })
            except Exception:
                continue
        return domains
