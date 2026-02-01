#!/usr/bin/env python3
"""
L5 Domain Deduplication
Normalize domains and deduplicate L4 CSV by domain
"""

import pandas as pd
import os
import glob
import argparse
from datetime import datetime
from threading import Lock
from urllib.parse import urlparse


class Logger:
    """Thread-safe logger with unbuffered writes"""
    def __init__(self, log_path):
        self.log_path = log_path
        self.lock = Lock()
        os.makedirs(os.path.dirname(log_path), exist_ok=True)

        with open(log_path, 'w', encoding='utf-8') as f:
            f.write("=" * 70 + "\n")
            f.write("SCRIPT: deduplicate_domains.py\n")
            f.write(f"STARTED: {datetime.now().isoformat()}\n")
            f.write("=" * 70 + "\n\n")
            f.flush()

    def log(self, message, to_console=True):
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_line = f"[{timestamp}] {message}\n"

        with self.lock:
            with open(self.log_path, 'a', encoding='utf-8') as f:
                f.write(log_line)
                f.flush()
                os.fsync(f.fileno())

            if to_console:
                print(message, flush=True)


def normalize_domain(url):
    """
    Normalize URL to domain (keep subdomains, remove protocol/path/query)

    Examples:
        https://www.Mayo.com/clinic?x=1 → www.mayo.com
        http://blog.mayo.com/path       → blog.mayo.com
        HTTPS://Example.COM/            → example.com
    """
    if not url or pd.isna(url) or url == '':
        return None

    # Convert to string and strip whitespace
    url = str(url).strip()

    if not url:
        return None

    # Remove protocol
    if '://' in url:
        url = url.split('://', 1)[1]

    # Remove path, query params, fragments
    domain = url.split('/')[0]
    domain = domain.split('?')[0]
    domain = domain.split('#')[0]

    # Remove port if present
    if ':' in domain:
        domain = domain.split(':')[0]

    # Lowercase
    domain = domain.lower().strip()

    return domain if domain else None


def main():
    parser = argparse.ArgumentParser(description='L5 Domain Deduplication')
    parser.add_argument('--client', required=True, help='Client name (e.g., fuse)')
    parser.add_argument('--filter', default='independent', help='L4 filter type (independent, all, hospital, university)')
    args = parser.parse_args()

    # Initialize logger
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    log_path = f'../logs/l5_domain_dedup/deduplicate_{args.client}_{args.filter}_{timestamp}.log'
    logger = Logger(log_path)

    logger.log("=" * 70)
    logger.log("L5 DOMAIN DEDUPLICATION")
    logger.log("=" * 70)
    logger.log(f"Client: {args.client}")
    logger.log(f"Filter: {args.filter}")
    logger.log(f"Log file: {log_path}")
    logger.log("")

    # Find L4 CSV files for this client
    l4_pattern = f'../l4_csv_export/outputs/{args.client}/{args.filter}_clinics_*.csv'
    l4_files = sorted(glob.glob(l4_pattern))

    if not l4_files:
        logger.log(f"❌ ERROR: No L4 CSV files found for client '{args.client}' with filter '{args.filter}'")
        logger.log(f"   Pattern: {l4_pattern}")
        return

    logger.log(f"📊 Found {len(l4_files)} L4 CSV file(s) to process:")
    for f in l4_files:
        logger.log(f"   - {os.path.basename(f)}")
    logger.log("")

    # Process each L4 file
    for idx, l4_file in enumerate(l4_files, 1):
        logger.log("=" * 70)
        logger.log(f"FILE {idx}/{len(l4_files)}")
        logger.log("=" * 70)
        logger.log("")

        logger.log(f"Processing: {os.path.basename(l4_file)}")

        # Read L4 CSV
        try:
            df = pd.read_csv(l4_file)
            logger.log(f"   Loaded {len(df)} rows")
        except Exception as e:
            logger.log(f"❌ ERROR reading CSV: {e}")
            continue

        # Check columns
        if 'website' not in df.columns:
            logger.log(f"⚠️  WARNING: 'website' column not found. Available columns: {list(df.columns)}")
            if 'source_url' in df.columns:
                logger.log(f"   Using 'source_url' as fallback")
                df['website'] = df['source_url']
            else:
                logger.log(f"❌ ERROR: Neither 'website' nor 'source_url' column found. Skipping file.")
                continue

        # Normalize domains
        logger.log("")
        logger.log("Normalizing domains...")
        df['domain_normalized'] = df['website'].apply(normalize_domain)

        # Stats
        total_rows = len(df)
        rows_with_domain = df['domain_normalized'].notna().sum()
        rows_missing_domain = total_rows - rows_with_domain

        logger.log(f"   Total rows: {total_rows}")
        logger.log(f"   Rows with valid domain: {rows_with_domain}")
        logger.log(f"   Rows with missing domain: {rows_missing_domain}")

        if rows_missing_domain > 0:
            logger.log(f"   ⚠️  {rows_missing_domain} rows will be excluded (missing/invalid domains)")

        # Deduplicate by domain (keep first occurrence)
        logger.log("")
        logger.log("Deduplicating by domain...")
        df_deduped = df.dropna(subset=['domain_normalized']).drop_duplicates(subset='domain_normalized', keep='first')

        duplicates_removed = rows_with_domain - len(df_deduped)

        logger.log(f"   Unique domains: {len(df_deduped)}")
        logger.log(f"   Duplicate domains removed: {duplicates_removed}")

        if duplicates_removed > 0:
            logger.log(f"   Deduplication rate: {100 * duplicates_removed / rows_with_domain:.1f}%")

        # Save deduplicated CSV
        output_dir = f'outputs/{args.client}'
        os.makedirs(output_dir, exist_ok=True)

        # Build output filename
        l4_basename = os.path.basename(l4_file).replace(f'{args.filter}_clinics_', f'{args.filter}_clinics_deduped_')
        l4_basename = l4_basename.replace('.csv', f'_{timestamp}.csv')
        output_filename = f"{output_dir}/{l4_basename}"

        df_deduped.to_csv(output_filename, index=False)

        logger.log("")
        logger.log(f"💾 Saved to: {output_filename}")
        logger.log(f"   File size: {os.path.getsize(output_filename) / 1024:.1f} KB")
        logger.log("")

        # Sample output
        logger.log("Sample normalized domains (first 10):")
        for i, domain in enumerate(df_deduped['domain_normalized'].head(10), 1):
            logger.log(f"   {i}. {domain}")

    logger.log("")
    logger.log("=" * 70)
    logger.log("✅ DEDUPLICATION COMPLETE")
    logger.log("=" * 70)
    logger.log(f"COMPLETED: {datetime.now().isoformat()}")
    logger.log("=" * 70)


if __name__ == '__main__':
    main()
