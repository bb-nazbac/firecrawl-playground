"""
Firecrawl API Client

Wraps the Firecrawl v2 API for scraping and mapping operations.
Includes retry logic with exponential backoff for rate limits,
timeouts, and connection errors.
"""

import os
import time
import threading
import requests
from typing import Tuple, Optional

from core.retry import (
    MAX_RETRIES,
    calculate_retry_delay,
    classify_error,
)
from core.markdown_cleaner import strip_markdown


class FirecrawlClient:
    """
    Firecrawl API client for scraping web pages and mapping domains.

    Uses the v2 API at https://api.firecrawl.dev/v2.
    All methods include retry logic with exponential backoff.
    """

    def __init__(self, api_key: str = None):
        """
        Initialize Firecrawl client.

        Args:
            api_key: Firecrawl API key. Falls back to FIRECRAWL_API_KEY env var.
        """
        self.api_key = api_key or os.environ.get('FIRECRAWL_API_KEY')
        if not self.api_key:
            raise ValueError("FIRECRAWL_API_KEY not found in environment variables")

        self.base_url = 'https://api.firecrawl.dev/v2'

    def _headers(self) -> dict:
        """Build standard request headers."""
        return {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }

    def scrape(
        self,
        url: str,
        semaphore: threading.Semaphore = None,
        timeout: int = 30000,
        request_timeout: int = 60,
    ) -> Tuple[bool, str, str, dict]:
        """
        Scrape a single URL using Firecrawl.

        Args:
            url: URL to scrape
            semaphore: Optional semaphore for rate limiting concurrency
            timeout: Firecrawl-side timeout in milliseconds
            request_timeout: HTTP request timeout in seconds

        Returns:
            Tuple of (success, markdown_content, error_message, stats)
            stats contains: attempts, retries, duration_seconds
        """
        # Ensure URL has protocol
        if not url.startswith('http'):
            url = f'https://{url}'

        stats = {"attempts": 0, "retries": 0, "duration_seconds": 0}
        start_time = time.time()

        def _do_scrape():
            for attempt in range(MAX_RETRIES):
                stats["attempts"] = attempt + 1

                try:
                    response = requests.post(
                        f'{self.base_url}/scrape',
                        headers=self._headers(),
                        json={
                            'url': url,
                            'formats': ['markdown'],
                            'onlyMainContent': True,
                            'timeout': timeout,
                        },
                        timeout=request_timeout,
                    )

                    # Rate limited - retry with backoff
                    if response.status_code == 429:
                        if attempt < MAX_RETRIES - 1:
                            delay = calculate_retry_delay(attempt)
                            stats["retries"] += 1
                            time.sleep(delay)
                            continue

                        stats["duration_seconds"] = time.time() - start_time
                        return False, '', 'Rate limited after max retries', stats

                    # Server error - retry
                    if 500 <= response.status_code < 600:
                        if attempt < MAX_RETRIES - 1:
                            delay = calculate_retry_delay(attempt)
                            stats["retries"] += 1
                            time.sleep(delay)
                            continue

                        stats["duration_seconds"] = time.time() - start_time
                        return False, '', f'HTTP {response.status_code}', stats

                    data = response.json()

                    if data.get('success'):
                        raw_markdown = data.get('data', {}).get('markdown', '')
                        # Strip useless content (images, SVGs, social links, etc.)
                        markdown = strip_markdown(raw_markdown)
                        stats["duration_seconds"] = time.time() - start_time
                        return True, markdown, None, stats
                    else:
                        error = data.get('error', 'Unknown API error')
                        error_type, can_retry = classify_error(Exception(error), response)

                        if can_retry and attempt < MAX_RETRIES - 1:
                            delay = calculate_retry_delay(attempt)
                            stats["retries"] += 1
                            time.sleep(delay)
                            continue

                        stats["duration_seconds"] = time.time() - start_time
                        return False, '', error, stats

                except requests.exceptions.Timeout:
                    if attempt < MAX_RETRIES - 1:
                        delay = calculate_retry_delay(attempt)
                        stats["retries"] += 1
                        time.sleep(delay)
                        continue

                    stats["duration_seconds"] = time.time() - start_time
                    return False, '', f'Timeout after {MAX_RETRIES} attempts', stats

                except requests.exceptions.ConnectionError as e:
                    if attempt < MAX_RETRIES - 1:
                        delay = calculate_retry_delay(attempt)
                        stats["retries"] += 1
                        time.sleep(delay)
                        continue

                    stats["duration_seconds"] = time.time() - start_time
                    return False, '', f'Connection error: {e}', stats

                except Exception as e:
                    error_type, can_retry = classify_error(e)

                    if can_retry and attempt < MAX_RETRIES - 1:
                        delay = calculate_retry_delay(attempt)
                        stats["retries"] += 1
                        time.sleep(delay)
                        continue

                    stats["duration_seconds"] = time.time() - start_time
                    return False, '', str(e), stats

            stats["duration_seconds"] = time.time() - start_time
            return False, '', 'Max retries exceeded', stats

        # Execute with semaphore if provided
        if semaphore:
            with semaphore:
                return _do_scrape()
        else:
            return _do_scrape()

    def map(
        self,
        domain: str,
        semaphore: threading.Semaphore = None,
        limit: int = 100,
        request_timeout: int = 30,
    ) -> Tuple[bool, list, str, dict]:
        """
        Map a domain to discover its URLs using Firecrawl.

        Args:
            domain: Domain to map (e.g. "example.com")
            semaphore: Optional semaphore for rate limiting concurrency
            limit: Maximum number of URLs to return
            request_timeout: HTTP request timeout in seconds

        Returns:
            Tuple of (success, urls_list, error_message, stats)
            stats contains: attempts, retries, duration_seconds
        """
        # Ensure URL has protocol
        url = f'https://{domain}' if not domain.startswith('http') else domain

        stats = {"attempts": 0, "retries": 0, "duration_seconds": 0}
        start_time = time.time()

        def _do_map():
            for attempt in range(MAX_RETRIES):
                stats["attempts"] = attempt + 1

                try:
                    response = requests.post(
                        f'{self.base_url}/map',
                        headers=self._headers(),
                        json={
                            'url': url,
                            'limit': limit,
                        },
                        timeout=request_timeout,
                    )

                    # Rate limited - retry with backoff
                    if response.status_code == 429:
                        if attempt < MAX_RETRIES - 1:
                            delay = calculate_retry_delay(attempt)
                            stats["retries"] += 1
                            time.sleep(delay)
                            continue

                        stats["duration_seconds"] = time.time() - start_time
                        return False, [], 'Rate limited after max retries', stats

                    # Server error - retry
                    if 500 <= response.status_code < 600:
                        if attempt < MAX_RETRIES - 1:
                            delay = calculate_retry_delay(attempt)
                            stats["retries"] += 1
                            time.sleep(delay)
                            continue

                        stats["duration_seconds"] = time.time() - start_time
                        return False, [], f'HTTP {response.status_code}', stats

                    data = response.json()

                    if data.get('success'):
                        urls = data.get('links', [])
                        stats["duration_seconds"] = time.time() - start_time
                        return True, urls, None, stats
                    else:
                        error = data.get('error', 'Unknown API error')
                        error_type, can_retry = classify_error(Exception(error), response)

                        if can_retry and attempt < MAX_RETRIES - 1:
                            delay = calculate_retry_delay(attempt)
                            stats["retries"] += 1
                            time.sleep(delay)
                            continue

                        stats["duration_seconds"] = time.time() - start_time
                        return False, [], error, stats

                except requests.exceptions.Timeout:
                    if attempt < MAX_RETRIES - 1:
                        delay = calculate_retry_delay(attempt)
                        stats["retries"] += 1
                        time.sleep(delay)
                        continue

                    stats["duration_seconds"] = time.time() - start_time
                    return False, [], f'Timeout after {MAX_RETRIES} attempts', stats

                except requests.exceptions.ConnectionError as e:
                    if attempt < MAX_RETRIES - 1:
                        delay = calculate_retry_delay(attempt)
                        stats["retries"] += 1
                        time.sleep(delay)
                        continue

                    stats["duration_seconds"] = time.time() - start_time
                    return False, [], f'Connection error: {e}', stats

                except Exception as e:
                    error_type, can_retry = classify_error(e)

                    if can_retry and attempt < MAX_RETRIES - 1:
                        delay = calculate_retry_delay(attempt)
                        stats["retries"] += 1
                        time.sleep(delay)
                        continue

                    stats["duration_seconds"] = time.time() - start_time
                    return False, [], str(e), stats

            stats["duration_seconds"] = time.time() - start_time
            return False, [], 'Max retries exceeded', stats

        # Execute with semaphore if provided
        if semaphore:
            with semaphore:
                return _do_map()
        else:
            return _do_map()
