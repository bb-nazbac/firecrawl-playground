"""
Serper.dev Search Client

Wraps the Serper.dev API for Google Search results.
Supports paginated search with automatic chunking (10 results per page).
Includes retry logic for transient failures.
"""

import os
import time
import requests
from typing import List, Tuple

from core.retry import (
    MAX_RETRIES,
    calculate_retry_delay,
    classify_error,
)


class SerperClient:
    """
    Serper.dev API client for performing Google searches.

    Handles pagination automatically since Serper returns max 10 results per request.
    Each page request counts as one API call for cost tracking purposes.
    """

    API_URL = "https://google.serper.dev/search"
    MAX_PER_PAGE = 10  # Serper max results per request

    def __init__(self, api_key: str = None):
        """
        Initialize Serper client.

        Args:
            api_key: Serper API key. Falls back to SERP_API_KEY env var.
        """
        self.api_key = api_key or os.environ.get('SERP_API_KEY')
        if not self.api_key:
            raise ValueError("SERP_API_KEY not found in environment variables")

    def _headers(self) -> dict:
        """Build standard request headers."""
        return {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json",
        }

    def search(
        self,
        query: str,
        num_results: int = 100,
        gl: str = 'us',
        hl: str = 'en',
        request_timeout: int = 10,
    ) -> Tuple[List[dict], int]:
        """
        Perform a paginated search.

        Automatically paginates through results in chunks of 10 (Serper max).
        Each page counts as one API call.

        Args:
            query: Search query string
            num_results: Total number of results desired
            gl: Geolocation country code (default: 'us')
            hl: Language code (default: 'en')
            request_timeout: HTTP request timeout in seconds

        Returns:
            Tuple of (results_list, api_calls_count)
            Each result dict has: position, title, url, snippet, query
        """
        all_results = []
        api_calls = 0
        pages_needed = min((num_results + self.MAX_PER_PAGE - 1) // self.MAX_PER_PAGE, 25)
        page = 1

        while page <= pages_needed and len(all_results) < num_results:
            page_results, success = self._search_page(
                query=query,
                page=page,
                gl=gl,
                hl=hl,
                request_timeout=request_timeout,
            )
            api_calls += 1

            if not success or not page_results:
                # No more results available
                break

            for item in page_results:
                all_results.append({
                    'position': item.get('position', len(all_results) + 1),
                    'title': item.get('title', ''),
                    'url': item.get('link', ''),
                    'snippet': item.get('snippet', ''),
                    'query': query,
                })

            page += 1

        # Trim to requested count
        return all_results[:num_results], api_calls

    def search_batch(
        self,
        queries: List[str],
        num_results_per_query: int = 100,
        gl: str = 'us',
        hl: str = 'en',
    ) -> Tuple[List[dict], int]:
        """
        Search multiple queries sequentially.

        Args:
            queries: List of search query strings
            num_results_per_query: Results desired per query
            gl: Geolocation country code
            hl: Language code

        Returns:
            Tuple of (all_results_list, total_api_calls)
        """
        all_results = []
        total_api_calls = 0

        for query in queries:
            results, calls = self.search(
                query=query,
                num_results=num_results_per_query,
                gl=gl,
                hl=hl,
            )
            all_results.extend(results)
            total_api_calls += calls

        return all_results, total_api_calls

    def _search_page(
        self,
        query: str,
        page: int = 1,
        gl: str = 'us',
        hl: str = 'en',
        request_timeout: int = 10,
    ) -> Tuple[list, bool]:
        """
        Fetch a single page of search results with retry logic.

        Args:
            query: Search query
            page: Page number (1-indexed)
            gl: Geolocation country code
            hl: Language code
            request_timeout: HTTP timeout

        Returns:
            Tuple of (organic_results_list, success_bool)
        """
        payload = {
            "q": query,
            "gl": gl,
            "hl": hl,
            "num": self.MAX_PER_PAGE,
            "page": page,
        }

        for attempt in range(MAX_RETRIES):
            try:
                response = requests.post(
                    self.API_URL,
                    json=payload,
                    headers=self._headers(),
                    timeout=request_timeout,
                )

                # Rate limited - retry
                if response.status_code == 429:
                    if attempt < MAX_RETRIES - 1:
                        delay = calculate_retry_delay(attempt)
                        time.sleep(delay)
                        continue
                    return [], False

                # Server error - retry
                if 500 <= response.status_code < 600:
                    if attempt < MAX_RETRIES - 1:
                        delay = calculate_retry_delay(attempt)
                        time.sleep(delay)
                        continue
                    return [], False

                if response.status_code != 200:
                    return [], False

                data = response.json()

                if 'error' in data:
                    error_type, can_retry = classify_error(Exception(data['error']))
                    if can_retry and attempt < MAX_RETRIES - 1:
                        delay = calculate_retry_delay(attempt)
                        time.sleep(delay)
                        continue
                    return [], False

                organic = data.get('organic', [])
                return organic, True

            except requests.exceptions.Timeout:
                if attempt < MAX_RETRIES - 1:
                    delay = calculate_retry_delay(attempt)
                    time.sleep(delay)
                    continue
                return [], False

            except requests.exceptions.ConnectionError:
                if attempt < MAX_RETRIES - 1:
                    delay = calculate_retry_delay(attempt)
                    time.sleep(delay)
                    continue
                return [], False

            except Exception as e:
                error_type, can_retry = classify_error(e)
                if can_retry and attempt < MAX_RETRIES - 1:
                    delay = calculate_retry_delay(attempt)
                    time.sleep(delay)
                    continue
                return [], False

        return [], False
