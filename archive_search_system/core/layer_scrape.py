"""
Layer 2: Scrape Implementation

Integrates Firecrawl API with production tracking systems and domain deduplication.
"""

import os
import time
import requests
import json
from datetime import datetime
from typing import List, Dict, Any
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock


class ScrapeLayer:
    """
    Layer 2: Scrape using Firecrawl API

    Scrapes URLs from L1 with concurrent processing and domain deduplication.
    """

    def __init__(self, config, progress, costs, diagnostics, domain_cache, logger, output_dir):
        """
        Initialize scrape layer

        Args:
            config: RunConfig object
            progress: ProgressTracker instance
            costs: CostTracker instance
            diagnostics: DiagnosticsManager instance
            domain_cache: DomainCache instance
            logger: Logger instance
            output_dir: Output directory path
        """
        self.config = config
        self.progress = progress
        self.costs = costs
        self.diagnostics = diagnostics
        self.domain_cache = domain_cache
        self.logger = logger
        self.output_dir = Path(output_dir)

        # Get API key
        self.api_key = os.getenv('FIRECRAWL_API_KEY')
        if not self.api_key:
            raise ValueError("FIRECRAWL_API_KEY not found in environment variables")

        # Setup layer diagnostics
        self.layer_diag = self.diagnostics.get_layer("scrape", 2)

        # Thread lock for progress updates
        self.lock = Lock()

    def run(self) -> Dict[str, Any]:
        """
        Execute scrape layer

        Returns:
            Dictionary with scrape results and metadata
        """
        # Load L1 results
        l1_file = self.output_dir / "l1_search_results.json"
        if not l1_file.exists():
            raise FileNotFoundError(f"L1 results not found: {l1_file}")

        with open(l1_file, 'r') as f:
            l1_data = json.load(f)

        urls = [r['url'] for r in l1_data['results'] if r.get('url')]

        # Apply test mode limit
        if self.config.test_mode:
            self.logger.info(f"Test mode: limiting to first {self.config.test_mode} URLs")
            urls = urls[:self.config.test_mode]

        self.logger.info(f"Scraping {len(urls)} URLs...")
        self.logger.info(f"Concurrency: {self.config.concurrency} threads")
        self.logger.info(f"Domain deduplication: enabled")
        self.logger.info("")

        # Check domain cache
        urls_to_scrape = []
        cached_count = 0

        for url in urls:
            if self.domain_cache.contains(url):
                cached_count += 1
                self.layer_diag.record_cache_hit(url)
            else:
                urls_to_scrape.append(url)
                self.domain_cache.add(url, metadata={"added_by": "l2_scrape"})
                self.layer_diag.record_cache_miss()

        self.logger.info(f"Cache check: {cached_count} URLs already scraped, {len(urls_to_scrape)} new")
        self.logger.info("")

        # Setup progress
        total_items = len(urls)
        self.layer_diag.set_total_items(total_items)
        self.progress.start_layer("l2_scrape", total_items=total_items)

        # Update for cached items
        if cached_count > 0:
            self.progress.increment_progress("l2_scrape", skipped_cached=cached_count)

        # Scrape URLs concurrently
        scraped_pages = self._scrape_concurrent(urls_to_scrape)

        # Complete layer
        self.layer_diag.complete()
        self.progress.complete_layer("l2_scrape")

        # Save results
        results_file = self.output_dir / "l2_scraped_pages.json"
        with open(results_file, 'w') as f:
            json.dump({
                "metadata": {
                    "total_urls": len(urls),
                    "scraped": len(scraped_pages),
                    "cached": cached_count
                },
                "pages": scraped_pages
            }, f, indent=2)

        self.logger.info(f"✓ Layer 2 complete: {len(scraped_pages)} pages scraped")
        self.logger.info(f"  Saved to: {results_file}")
        self.logger.info("")

        return {
            "total_pages": len(scraped_pages),
            "results_file": str(results_file)
        }

    def _scrape_concurrent(self, urls: List[str]) -> List[Dict[str, Any]]:
        """
        Scrape URLs concurrently

        Args:
            urls: List of URLs to scrape

        Returns:
            List of scraped page data
        """
        if not urls:
            return []

        scraped_pages = []
        start_time = datetime.now()

        def scrape_with_index(url_tuple):
            idx, url = url_tuple
            result = self._scrape_url(url)
            return (idx, result)

        with ThreadPoolExecutor(max_workers=self.config.concurrency) as executor:
            futures = {
                executor.submit(scrape_with_index, (i, url)): (i, url)
                for i, url in enumerate(urls)
            }

            for future in as_completed(futures):
                idx, url = futures[future]

                try:
                    result_idx, page_data = future.result()

                    with self.lock:
                        if page_data.get('success'):
                            self.progress.increment_progress("l2_scrape", completed=1)
                            markdown_len = len(page_data.get('markdown', ''))
                            self.logger.info(f"  ✓ [{result_idx+1}/{len(urls)}] {url[:60]}... ({markdown_len:,} chars)")
                        else:
                            self.progress.increment_progress("l2_scrape", failed=1)
                            self.logger.error(f"  ✗ [{result_idx+1}/{len(urls)}] {url[:60]}... ({page_data.get('error')})")

                        scraped_pages.append((result_idx, page_data))

                except Exception as e:
                    with self.lock:
                        self.progress.increment_progress("l2_scrape", failed=1)
                        self.logger.error(f"  ✗ Exception: {e}")
                        scraped_pages.append((idx, {
                            "url": url,
                            "success": False,
                            "error": str(e)
                        }))

        # Sort by original index
        scraped_pages.sort(key=lambda x: x[0])
        return [page for idx, page in scraped_pages]

    def _scrape_url(self, url: str) -> Dict[str, Any]:
        """
        Scrape a single URL with retries

        Args:
            url: URL to scrape

        Returns:
            Scraped page data or error info
        """
        api_url = "https://api.firecrawl.dev/v2/scrape"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "url": url,
            "formats": ["markdown", "links"]
        }

        max_retries = 10
        retry_delay = 2
        scrape_start = datetime.now()

        for attempt in range(max_retries):
            try:
                response = requests.post(api_url, json=payload, headers=headers, timeout=30)

                if response.status_code == 429:
                    time.sleep(retry_delay * (attempt + 1))
                    self.layer_diag.record_retry(succeeded=False)
                    continue

                if response.status_code == 200:
                    data = response.json()

                    if data.get('success'):
                        markdown = data.get('data', {}).get('markdown', '')
                        links = data.get('data', {}).get('links', [])

                        # Record cost
                        self.costs.record_firecrawl_scrape(1)

                        # Record success
                        duration = (datetime.now() - scrape_start).total_seconds()
                        self.layer_diag.record_success(
                            item_id=url,
                            duration_seconds=duration
                        )

                        if attempt > 0:
                            self.layer_diag.record_retry(succeeded=True)

                        return {
                            "url": url,
                            "success": True,
                            "markdown": markdown,
                            "links": links,
                            "scraped_at": datetime.now().isoformat()
                        }

                # Other HTTP errors
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    self.layer_diag.record_retry(succeeded=False)
                    continue

                # Final failure
                duration = (datetime.now() - scrape_start).total_seconds()
                self.layer_diag.record_failure(
                    item_id=url,
                    error_type=f"http_{response.status_code}",
                    error_message=f"HTTP {response.status_code}",
                    retry_count=attempt + 1,
                    can_retry=True,
                    duration_seconds=duration
                )

                return {
                    "url": url,
                    "success": False,
                    "error": f"HTTP {response.status_code}"
                }

            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    self.layer_diag.record_retry(succeeded=False)
                    continue

                duration = (datetime.now() - scrape_start).total_seconds()
                self.layer_diag.record_failure(
                    item_id=url,
                    error_type="timeout",
                    error_message="Timeout after retries",
                    retry_count=max_retries,
                    can_retry=True,
                    duration_seconds=duration
                )

                return {
                    "url": url,
                    "success": False,
                    "error": "Timeout after retries"
                }

            except Exception as e:
                duration = (datetime.now() - scrape_start).total_seconds()
                self.layer_diag.record_failure(
                    item_id=url,
                    error_type="exception",
                    error_message=str(e),
                    retry_count=attempt + 1,
                    can_retry=False,
                    duration_seconds=duration
                )

                return {
                    "url": url,
                    "success": False,
                    "error": str(e)
                }

        return {
            "url": url,
            "success": False,
            "error": "Max retries exceeded"
        }
