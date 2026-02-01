#!/usr/bin/env python3
"""
MAP Endpoint Rate Limit Test Script

Tests the Firecrawl /v2/map endpoint at various concurrency levels
to discover rate limits and find optimal configuration for 99%+ success rate.

Usage:
    python map_rate_test.py --concurrency 5 --domains 50
    python map_rate_test.py -c 1 -d 50 --output results/test_c1.json
"""

import os
import sys
import json
import time
import argparse
import requests
import threading
import csv
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Optional

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════

SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent.parent

# Load environment
def load_env():
    """Load environment variables from .env file"""
    for env_path in [ROOT_DIR / ".env", ROOT_DIR.parent / ".env"]:
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        os.environ.setdefault(key.strip(), value.strip())
            break

load_env()
FIRECRAWL_API_KEY = os.environ.get('FIRECRAWL_API_KEY')

# ═══════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════

@dataclass
class MapResult:
    """Result of a single MAP request"""
    domain: str
    success: bool
    urls_found: int
    status_code: int
    error: Optional[str]
    attempts: int
    rate_limited_count: int
    duration_ms: int
    timestamp: str

@dataclass
class TestMetrics:
    """Aggregated metrics for the test run"""
    concurrency: int
    total_domains: int
    started_at: str
    completed_at: str = ""
    duration_seconds: float = 0.0

    # Success metrics
    successful: int = 0
    failed: int = 0
    success_rate: float = 0.0

    # Rate limit metrics
    total_rate_limits: int = 0
    domains_with_rate_limits: int = 0
    max_rate_limits_per_domain: int = 0

    # Retry distribution
    retry_distribution: Dict[int, int] = field(default_factory=dict)

    # Timing
    avg_duration_ms: float = 0.0
    min_duration_ms: int = 0
    max_duration_ms: int = 0
    requests_per_minute: float = 0.0

    # Error breakdown
    error_types: Dict[str, int] = field(default_factory=dict)

# ═══════════════════════════════════════════════════════════════
# MAP API CALL
# ═══════════════════════════════════════════════════════════════

def map_domain(domain: str, timeout: int = 60, max_retries: int = 7, limit: int = 100) -> MapResult:
    """
    Call the Firecrawl /v2/map endpoint for a single domain.
    Uses exponential backoff for retries.
    """
    url = f"https://{domain}" if not domain.startswith("http") else domain
    start_time = time.time()

    attempts = 0
    rate_limited_count = 0
    last_error = None
    last_status = 0

    for attempt in range(max_retries):
        attempts = attempt + 1

        try:
            response = requests.post(
                'https://api.firecrawl.dev/v2/map',
                headers={
                    'Authorization': f'Bearer {FIRECRAWL_API_KEY}',
                    'Content-Type': 'application/json'
                },
                json={'url': url, 'limit': limit},
                timeout=timeout
            )

            last_status = response.status_code

            if response.status_code == 429:
                rate_limited_count += 1
                delay = min(30.0, (2 ** attempt))
                time.sleep(delay)
                continue

            data = response.json()

            if data.get('success'):
                links = data.get('links', [])
                if links and isinstance(links[0], dict):
                    links = [link.get('url', '') for link in links]

                duration_ms = int((time.time() - start_time) * 1000)
                return MapResult(
                    domain=domain,
                    success=True,
                    urls_found=len(links),
                    status_code=response.status_code,
                    error=None,
                    attempts=attempts,
                    rate_limited_count=rate_limited_count,
                    duration_ms=duration_ms,
                    timestamp=datetime.now().isoformat()
                )
            else:
                last_error = data.get('error', 'Unknown API error')
                delay = min(30.0, (2 ** attempt))
                time.sleep(delay)

        except requests.exceptions.Timeout:
            last_error = "Timeout"
            delay = min(30.0, (2 ** attempt))
            time.sleep(delay)
        except requests.exceptions.RequestException as e:
            last_error = str(e)
            delay = min(30.0, (2 ** attempt))
            time.sleep(delay)
        except Exception as e:
            last_error = str(e)
            break

    duration_ms = int((time.time() - start_time) * 1000)
    return MapResult(
        domain=domain,
        success=False,
        urls_found=0,
        status_code=last_status,
        error=last_error or "Max retries exceeded",
        attempts=attempts,
        rate_limited_count=rate_limited_count,
        duration_ms=duration_ms,
        timestamp=datetime.now().isoformat()
    )

# ═══════════════════════════════════════════════════════════════
# TEST RUNNER
# ═══════════════════════════════════════════════════════════════

def load_domains(csv_path: str, limit: int = 50) -> List[str]:
    """Load domains from CSV file"""
    domains = []
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            domain = row.get('domain', row.get('Domain', ''))
            if domain:
                domains.append(domain)
            if len(domains) >= limit:
                break
    return domains

def run_test(domains: List[str], concurrency: int) -> tuple:
    """Run the MAP test with specified concurrency"""
    results: List[MapResult] = []
    lock = threading.Lock()
    completed = 0

    def process_domain(domain: str) -> MapResult:
        nonlocal completed
        result = map_domain(domain)
        with lock:
            completed += 1
            status = "✅" if result.success else "❌"
            print(f"[{completed}/{len(domains)}] {status} {domain} - {result.attempts} attempts, {result.rate_limited_count} rate limits, {result.duration_ms}ms", flush=True)
        return result

    metrics = TestMetrics(
        concurrency=concurrency,
        total_domains=len(domains),
        started_at=datetime.now().isoformat()
    )

    start_time = time.time()

    print(f"\n{'='*60}", flush=True)
    print(f"MAP RATE LIMIT TEST", flush=True)
    print(f"{'='*60}", flush=True)
    print(f"Concurrency: {concurrency}", flush=True)
    print(f"Domains: {len(domains)}", flush=True)
    print(f"Started: {metrics.started_at}", flush=True)
    print(f"{'='*60}\n", flush=True)

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {executor.submit(process_domain, d): d for d in domains}
        for future in as_completed(futures):
            results.append(future.result())

    end_time = time.time()
    metrics.completed_at = datetime.now().isoformat()
    metrics.duration_seconds = end_time - start_time

    # Calculate metrics
    metrics.successful = sum(1 for r in results if r.success)
    metrics.failed = sum(1 for r in results if not r.success)
    metrics.success_rate = (metrics.successful / len(results)) * 100 if results else 0

    # Rate limit metrics
    metrics.total_rate_limits = sum(r.rate_limited_count for r in results)
    metrics.domains_with_rate_limits = sum(1 for r in results if r.rate_limited_count > 0)
    metrics.max_rate_limits_per_domain = max((r.rate_limited_count for r in results), default=0)

    # Retry distribution
    for r in results:
        metrics.retry_distribution[r.attempts] = metrics.retry_distribution.get(r.attempts, 0) + 1

    # Timing
    durations = [r.duration_ms for r in results]
    metrics.avg_duration_ms = sum(durations) / len(durations) if durations else 0
    metrics.min_duration_ms = min(durations) if durations else 0
    metrics.max_duration_ms = max(durations) if durations else 0
    metrics.requests_per_minute = (len(results) / metrics.duration_seconds) * 60 if metrics.duration_seconds > 0 else 0

    # Error breakdown
    for r in results:
        if r.error:
            error_type = r.error.split(':')[0] if ':' in r.error else r.error[:50]
            metrics.error_types[error_type] = metrics.error_types.get(error_type, 0) + 1

    return results, metrics

def print_summary(metrics: TestMetrics):
    """Print test summary"""
    print(f"\n{'='*60}")
    print(f"TEST SUMMARY")
    print(f"{'='*60}")
    print(f"Concurrency:          {metrics.concurrency}")
    print(f"Total Domains:        {metrics.total_domains}")
    print(f"Duration:             {metrics.duration_seconds:.1f}s")
    print(f"")
    print(f"SUCCESS METRICS:")
    print(f"  Successful:         {metrics.successful}")
    print(f"  Failed:             {metrics.failed}")
    print(f"  Success Rate:       {metrics.success_rate:.1f}%")
    print(f"")
    print(f"RATE LIMIT METRICS:")
    print(f"  Total 429s:         {metrics.total_rate_limits}")
    print(f"  Domains w/ 429:     {metrics.domains_with_rate_limits}")
    print(f"  Max 429s/domain:    {metrics.max_rate_limits_per_domain}")
    print(f"")
    print(f"TIMING:")
    print(f"  Avg Duration:       {metrics.avg_duration_ms:.0f}ms")
    print(f"  Min Duration:       {metrics.min_duration_ms}ms")
    print(f"  Max Duration:       {metrics.max_duration_ms}ms")
    print(f"  Requests/min:       {metrics.requests_per_minute:.1f}")
    print(f"")
    print(f"RETRY DISTRIBUTION:")
    for attempts, count in sorted(metrics.retry_distribution.items()):
        print(f"  {attempts} attempt(s):     {count} domains")
    if metrics.error_types:
        print(f"")
        print(f"ERROR BREAKDOWN:")
        for error, count in sorted(metrics.error_types.items(), key=lambda x: -x[1]):
            print(f"  {error}: {count}")
    print(f"{'='*60}\n")

# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description='Test MAP endpoint rate limits')
    parser.add_argument('-c', '--concurrency', type=int, default=5, help='Number of concurrent requests')
    parser.add_argument('-d', '--domains', type=int, default=50, help='Number of domains to test')
    parser.add_argument('-i', '--input', type=str, default=str(ROOT_DIR / 'inputs' / 'test_250_domains.csv'), help='Input CSV file')
    parser.add_argument('-o', '--output', type=str, default=None, help='Output JSON file')
    args = parser.parse_args()

    if not FIRECRAWL_API_KEY:
        print("ERROR: FIRECRAWL_API_KEY not found in environment")
        sys.exit(1)

    # Load domains
    domains = load_domains(args.input, args.domains)
    if not domains:
        print(f"ERROR: No domains found in {args.input}")
        sys.exit(1)

    print(f"Loaded {len(domains)} domains from {args.input}")

    # Run test
    results, metrics = run_test(domains, args.concurrency)

    # Print summary
    print_summary(metrics)

    # Save results
    output_path = args.output or str(SCRIPT_DIR / 'results' / f'test_c{args.concurrency}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    output_data = {
        'metrics': asdict(metrics),
        'results': [asdict(r) for r in results]
    }

    with open(output_path, 'w') as f:
        json.dump(output_data, f, indent=2)

    print(f"Results saved to: {output_path}")

    # Return exit code based on success rate
    if metrics.success_rate >= 99:
        print(f"\n✅ SUCCESS: {metrics.success_rate:.1f}% success rate meets 99% target")
        return 0
    else:
        print(f"\n❌ BELOW TARGET: {metrics.success_rate:.1f}% success rate is below 99% target")
        return 1

if __name__ == '__main__':
    sys.exit(main())
