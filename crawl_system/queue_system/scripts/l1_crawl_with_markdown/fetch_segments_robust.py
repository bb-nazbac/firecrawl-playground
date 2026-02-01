#!/usr/bin/env python3
"""
L1: Fetch All Segments from Firecrawl Crawl Job (ROBUST VERSION)
- Comprehensive retry logic for all API calls
- Rate limit handling with exponential backoff
- Validates all responses
- Graceful degradation on partial failures
"""
import os
import sys
import json
import time
import requests
from pathlib import Path

def log(msg):
    """Print with flush for real-time logging"""
    print(msg, flush=True)

def retry_api_call(func, max_retries=10, initial_delay=2):
    """
    Retry an API call with exponential backoff
    Returns: (success: bool, data: dict/None, error: str/None)
    """
    retries = 0
    delay = initial_delay

    while retries < max_retries:
        try:
            resp = func()

            # Check HTTP status
            if resp.status_code == 429:
                # Rate limit - always retry
                log(f"  ⚠️  Rate limit hit, retrying in {delay}s... (attempt {retries+1}/{max_retries})")
                time.sleep(delay)
                retries += 1
                delay = min(delay * 2, 60)  # Cap at 60 seconds
                continue

            if resp.status_code == 200:
                try:
                    data = resp.json()
                    return (True, data, None)
                except json.JSONDecodeError as e:
                    log(f"  ⚠️  Invalid JSON response: {e}")
                    if retries < max_retries - 1:
                        log(f"  Retrying in {delay}s...")
                        time.sleep(delay)
                        retries += 1
                        delay = min(delay * 2, 60)
                        continue
                    return (False, None, f"Invalid JSON: {e}")

            # Other HTTP errors
            log(f"  ⚠️  HTTP {resp.status_code}: {resp.text[:200]}")
            if retries < max_retries - 1:
                log(f"  Retrying in {delay}s... (attempt {retries+1}/{max_retries})")
                time.sleep(delay)
                retries += 1
                delay = min(delay * 2, 60)
                continue

            return (False, None, f"HTTP {resp.status_code}: {resp.text[:200]}")

        except requests.exceptions.Timeout:
            log(f"  ⚠️  Request timeout")
            if retries < max_retries - 1:
                log(f"  Retrying in {delay}s... (attempt {retries+1}/{max_retries})")
                time.sleep(delay)
                retries += 1
                delay = min(delay * 2, 60)
                continue
            return (False, None, "Request timeout after retries")

        except requests.exceptions.RequestException as e:
            log(f"  ⚠️  Network error: {e}")
            if retries < max_retries - 1:
                log(f"  Retrying in {delay}s... (attempt {retries+1}/{max_retries})")
                time.sleep(delay)
                retries += 1
                delay = min(delay * 2, 60)
                continue
            return (False, None, f"Network error: {e}")

    return (False, None, "Max retries exceeded")

def main():
    if len(sys.argv) < 2:
        log("Usage: fetch_segments_robust.py <crawl_id>")
        sys.exit(1)

    CRAWL_ID = sys.argv[1]
    FIRECRAWL_KEY = os.getenv("FIRECRAWL_API_KEY")
    CLIENT = os.getenv("CLIENT", "default")
    DOMAIN = os.getenv("DOMAIN", "default")

    if not FIRECRAWL_KEY:
        log("❌ ERROR: FIRECRAWL_API_KEY not set in environment")
        sys.exit(1)

    # Use queue_system outputs directory
    SCRIPT_DIR = Path(__file__).parent.parent.parent
    SEGMENTS_DIR = SCRIPT_DIR / "outputs" / CLIENT / DOMAIN / "segments"
    SEGMENTS_DIR.mkdir(parents=True, exist_ok=True)

    log(f"🔍 Fetching segments for crawl: {CRAWL_ID}")
    log(f"   Output: {SEGMENTS_DIR}")

    # ============================================================================
    # PHASE 1: Poll until crawl completes
    # ============================================================================
    log("\n[PHASE 1] Polling crawl status...")

    poll_retries = 0
    max_poll_attempts = 360  # 30 minutes at 5s intervals

    while poll_retries < max_poll_attempts:
        def poll_status():
            return requests.get(
                f"https://api.firecrawl.dev/v2/crawl/{CRAWL_ID}",
                headers={"Authorization": f"Bearer {FIRECRAWL_KEY}"},
                timeout=30
            )

        success, data, error = retry_api_call(poll_status, max_retries=10)

        if not success:
            log(f"❌ Failed to poll crawl status: {error}")
            sys.exit(1)

        status = data.get('status', 'unknown')
        completed = data.get('completed', 0)
        total = data.get('total', 0)

        log(f"  Status: {status} - {completed}/{total} pages")

        if status == 'completed':
            log(f"✅ Crawl completed: {completed} pages")
            break

        if status == 'failed':
            log(f"❌ Crawl failed")
            sys.exit(1)

        time.sleep(5)
        poll_retries += 1

    if poll_retries >= max_poll_attempts:
        log(f"❌ Crawl did not complete within 30 minutes")
        sys.exit(1)

    # ============================================================================
    # PHASE 2: Fetch all segments with retry
    # ============================================================================
    log("\n[PHASE 2] Fetching all segments...")

    segment_num = 0
    skip = 0
    total_pages = 0
    failed_segments = []

    while True:
        segment_num += 1

        if segment_num == 1:
            url = f"https://api.firecrawl.dev/v2/crawl/{CRAWL_ID}"
        else:
            url = f"https://api.firecrawl.dev/v2/crawl/{CRAWL_ID}?skip={skip}"

        def fetch_segment():
            return requests.get(
                url,
                headers={"Authorization": f"Bearer {FIRECRAWL_KEY}"},
                timeout=30
            )

        success, data, error = retry_api_call(fetch_segment, max_retries=10)

        if not success:
            log(f"  ❌ Segment {segment_num} failed after retries: {error}")
            failed_segments.append(segment_num)
            # Don't exit - try to continue with next segment
            # But if we have too many failures, abort
            if len(failed_segments) > 5:
                log(f"❌ Too many segment failures ({len(failed_segments)}), aborting")
                sys.exit(1)
            break  # Can't continue if we don't know skip count

        # Save segment
        segment_file = SEGMENTS_DIR / f"segment_{segment_num:03d}.json"
        try:
            with open(segment_file, 'w') as f:
                json.dump(data, f, indent=2)
        except IOError as e:
            log(f"  ❌ Failed to write segment file: {e}")
            sys.exit(1)

        data_count = len(data.get('data', []))
        total_pages += data_count
        log(f"  Segment {segment_num}: {data_count} pages (total: {total_pages})")

        skip += data_count

        # Check if there's more data
        if not data.get('next'):
            break

    # ============================================================================
    # PHASE 3: Validate results
    # ============================================================================
    log("\n[PHASE 3] Validation...")

    if total_pages == 0:
        log(f"❌ No pages fetched")
        sys.exit(1)

    if failed_segments:
        log(f"⚠️  {len(failed_segments)} segments failed: {failed_segments}")
        log(f"   Continuing with {total_pages} pages from {segment_num - len(failed_segments)} successful segments")

    log(f"\n✅ L1 COMPLETE")
    log(f"   Segments: {segment_num - len(failed_segments)}/{segment_num}")
    log(f"   Pages: {total_pages}")
    log(f"   Location: {SEGMENTS_DIR}")

    return 0

if __name__ == "__main__":
    sys.exit(main())
