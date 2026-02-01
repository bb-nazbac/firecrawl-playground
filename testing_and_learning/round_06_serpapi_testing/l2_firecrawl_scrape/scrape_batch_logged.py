#!/usr/bin/env python3
"""
Batch L2 Scraping Script with PROPER LOGGING
COMMANDMENTS #7 Compliant: Logs to /logs/l2_firecrawl_scrape/
"""

import os
import json
import time
import sys
from datetime import datetime
import requests
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import glob

load_dotenv('../../../.env')
FIRECRAWL_API_KEY = os.getenv('FIRECRAWL_API_KEY')

if not FIRECRAWL_API_KEY:
    print("❌ ERROR: FIRECRAWL_API_KEY not found in .env")
    exit(1)


# ═══════════════════════════════════════════════════════════════════
# LOGGING UTILITY (COMMANDMENTS #7)
# ═══════════════════════════════════════════════════════════════════

class Logger:
    def __init__(self, log_path):
        self.log_path = log_path
        self.lock = Lock()

        # Create log directory
        os.makedirs(os.path.dirname(log_path), exist_ok=True)

        # Initialize log file with header
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write("═" * 70 + "\n")
            f.write("SCRIPT: scrape_batch_logged.py\n")
            f.write("ROUND: 06 - Serper.dev Production Pipeline\n")
            f.write("LAYER: L2 - Firecrawl Concurrent Scraper (50 threads)\n")
            f.write(f"STARTED: {datetime.now().isoformat()}\n")
            f.write("═" * 70 + "\n\n")
            f.flush()

    def log(self, message, to_console=True):
        """Write to both log file and console"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_line = f"[{timestamp}] {message}\n"

        with self.lock:
            # Write to file (unbuffered)
            with open(self.log_path, 'a', encoding='utf-8') as f:
                f.write(log_line)
                f.flush()
                os.fsync(f.fileno())  # Force write to disk

            # Write to console
            if to_console:
                print(message, flush=True)

    def section(self, title):
        """Log a section header"""
        self.log("=" * 70)
        self.log(title)
        self.log("=" * 70)

    def summary(self, title, metrics):
        """Log final summary with metrics"""
        self.log("")
        self.log("=" * 70)
        self.log(title)
        self.log("=" * 70)
        for key, value in metrics.items():
            self.log(f"   {key}: {value}")
        self.log("=" * 70)


# Global logger instance
logger = None


def scrape_url(url):
    """Scrape a single URL with Firecrawl API"""

    api_url = "https://api.firecrawl.dev/v2/scrape"
    headers = {
        "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "url": url,
        "formats": ["markdown", "links"]
    }

    max_retries = 10
    retry_delay = 2

    for attempt in range(max_retries):
        try:
            response = requests.post(api_url, json=payload, headers=headers, timeout=60)

            if response.status_code == 429:
                logger.log(f"      ⚠️  Rate limited on {url[:50]}... (attempt {attempt+1}/{max_retries})")
                time.sleep(retry_delay * (attempt + 1))
                continue

            if response.status_code == 200:
                data = response.json()

                if data.get('success'):
                    markdown = data.get('data', {}).get('markdown', '')
                    links = data.get('data', {}).get('links', [])

                    return {
                        "url": url,
                        "success": True,
                        "markdown": markdown,
                        "links": links,
                        "scraped_at": datetime.now().isoformat()
                    }

            # Other HTTP errors
            if attempt < max_retries - 1:
                logger.log(f"      ⚠️  HTTP {response.status_code} on {url[:50]}...")
                time.sleep(retry_delay)
                continue

            return {
                "url": url,
                "success": False,
                "error": f"HTTP {response.status_code}"
            }

        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                logger.log(f"      ⚠️  Timeout on {url[:50]}... (attempt {attempt+1})")
                time.sleep(retry_delay)
                continue
            return {
                "url": url,
                "success": False,
                "error": "Timeout after retries"
            }

        except Exception as e:
            logger.log(f"      ❌ Exception on {url[:50]}...: {e}")
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


def scrape_concurrent(urls, max_workers=50):
    """Scrape URLs concurrently"""

    scraped_pages = []
    success_count = 0
    error_count = 0
    completed_count = 0
    start_time = datetime.now()

    lock = Lock()

    def scrape_with_index(url_tuple):
        idx, url = url_tuple
        page_data = scrape_url(url)
        return (idx, page_data)

    logger.log(f"Starting concurrent scraping with {max_workers} threads...")
    logger.log("")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {
            executor.submit(scrape_with_index, (i, url)): (i, url)
            for i, url in enumerate(urls)
        }

        for future in as_completed(future_to_url):
            idx, url = future_to_url[future]

            try:
                result_idx, page_data = future.result()

                with lock:
                    completed_count += 1

                    if page_data.get('success'):
                        success_count += 1
                        markdown_len = len(page_data.get('markdown', ''))
                        links_count = len(page_data.get('links', []))
                        logger.log(f"[{completed_count}/{len(urls)}] ✅ {url[:50]}... ({markdown_len:,} chars, {links_count} links)")
                    else:
                        error_count += 1
                        logger.log(f"[{completed_count}/{len(urls)}] ❌ {url[:50]}... ({page_data.get('error', 'Unknown error')})")

                    scraped_pages.append((result_idx, page_data))

            except Exception as e:
                with lock:
                    completed_count += 1
                    error_count += 1
                    logger.log(f"[{completed_count}/{len(urls)}] ❌ {url[:50]}... (Exception: {e})")
                    scraped_pages.append((idx, {
                        "url": url,
                        "success": False,
                        "error": str(e)
                    }))

    # Sort by original index
    scraped_pages.sort(key=lambda x: x[0])
    scraped_pages = [page for idx, page in scraped_pages]

    total_time = (datetime.now() - start_time).total_seconds()

    return scraped_pages, success_count, error_count, total_time


def process_l1_file(l1_file_path):
    """Process a single L1 output file"""

    logger.section(f"Processing: {os.path.basename(l1_file_path)}")

    with open(l1_file_path, 'r', encoding='utf-8') as f:
        l1_data = json.load(f)

    urls = [r['link'] for r in l1_data['results'] if r.get('link')]
    query = l1_data['query']

    logger.log(f"Query: {query}")
    logger.log(f"URLs to scrape: {len(urls)}")
    logger.log("")

    scraped_pages, success_count, error_count, total_time = scrape_concurrent(urls, max_workers=50)

    logger.log("")
    logger.summary("✅ SCRAPING COMPLETE", {
        "Total URLs": len(urls),
        "Successful": success_count,
        "Failed": error_count,
        f"Time": f"{total_time:.1f}s ({total_time/60:.1f} minutes)",
        "Avg per page": f"{total_time/len(urls):.2f}s"
    })
    logger.log("")

    # Save results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    basename = os.path.basename(l1_file_path).replace('l1_search_', 'l2_scraped_')
    basename = basename.replace('.json', f'_{timestamp}.json')

    output_data = {
        'metadata': {
            'source_file': l1_file_path,
            'query': query,
            'timestamp': datetime.now().isoformat(),
            'total_urls': len(urls),
            'successful_scrapes': success_count,
            'failed_scrapes': error_count,
            'scrape_time_seconds': total_time
        },
        'pages': scraped_pages
    }

    # Save to outputs
    output_dir = '../outputs'
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, basename)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    logger.log(f"💾 Saved to: {output_path}")

    # Save to client folder
    client_dir = '../../../search_system/client_outputs/fuse/outputs/l2_scrape'
    os.makedirs(client_dir, exist_ok=True)
    client_path = os.path.join(client_dir, basename)

    with open(client_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    logger.log(f"💾 Saved to client folder: {client_path}")
    logger.log("")

    return {
        'file': basename,
        'query': query,
        'urls': len(urls),
        'success': success_count,
        'failed': error_count,
        'time': total_time,
        'output_path': output_path
    }


def main():
    global logger

    # Initialize logger (COMMANDMENTS #7)
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    log_path = f'../logs/l2_firecrawl_scrape/scrape_batch_{timestamp}.log'
    logger = Logger(log_path)

    logger.section("ROUND 06: BATCH L2 SCRAPING")
    logger.log("Client: Fuse")
    logger.log("API: Firecrawl (50 concurrent threads)")
    logger.log(f"Log file: {log_path}")
    logger.log("")

    # Find all L1 output files from today's batch
    l1_pattern = '../outputs/l1_search_neurology_*_20251107_*.json'
    l1_files = sorted(glob.glob(l1_pattern))

    if not l1_files:
        logger.log("❌ No L1 files found matching pattern")
        return

    logger.log(f"📊 Found {len(l1_files)} L1 files to process:")
    for f in l1_files:
        logger.log(f"   - {os.path.basename(f)}")
    logger.log("")

    batch_start = datetime.now()
    results_summary = []

    for i, l1_file in enumerate(l1_files, 1):
        logger.log("")
        logger.section(f"FILE {i}/{len(l1_files)}")
        logger.log("")

        result = process_l1_file(l1_file)
        results_summary.append(result)

    batch_elapsed = (datetime.now() - batch_start).total_seconds()

    # Final Summary
    total_urls = sum(r['urls'] for r in results_summary)
    total_success = sum(r['success'] for r in results_summary)
    total_failed = sum(r['failed'] for r in results_summary)

    logger.log("")
    logger.summary("🎉 BATCH L2 SCRAPING COMPLETE!", {
        "Files processed": len(results_summary),
        "Total URLs": f"{total_urls:,}",
        "Successful": f"{total_success:,} ({100*total_success/total_urls:.1f}%)",
        "Failed": f"{total_failed:,} ({100*total_failed/total_urls:.1f}%)",
        "Total time": f"{batch_elapsed:.1f}s ({batch_elapsed/60:.1f} minutes)",
        "Avg per page": f"{batch_elapsed/total_urls:.2f}s",
        "Estimated cost": f"${total_urls * 0.001:.3f}"
    })

    logger.log("")
    logger.log("Per-Query Results:")
    for r in results_summary:
        success_rate = 100 * r['success'] / r['urls'] if r['urls'] > 0 else 0
        logger.log(f"   {r['query'][:40]}: {r['success']}/{r['urls']} ({success_rate:.1f}%) in {r['time']/60:.1f}min")

    logger.log("")
    logger.log("Next Step: Run L3 classification on all scraped pages")
    logger.log("=" * 70)
    logger.log(f"COMPLETED: {datetime.now().isoformat()}")
    logger.log(f"DURATION: {batch_elapsed:.1f} seconds")
    logger.log(f"LOG FILE: {log_path}")
    logger.log("=" * 70)


if __name__ == '__main__':
    main()
