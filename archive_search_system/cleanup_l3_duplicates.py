#!/usr/bin/env python3
"""
L3 File Cleanup - Remove Duplicate Runs
OPTIMUS PRIME Protocol - Commandment #7 Compliant
Keeps only: Latest successful run (Nov 8, 23:12:25) + Today's re-run (Nov 9, 11:35:47)
"""

import os
import glob
from datetime import datetime
from threading import Lock


class Logger:
    """Thread-safe logger with unbuffered writes (Commandment #7)"""
    def __init__(self, log_path):
        self.log_path = log_path
        self.lock = Lock()
        os.makedirs(os.path.dirname(log_path), exist_ok=True)

        with open(log_path, 'w', encoding='utf-8') as f:
            f.write("=" * 70 + "\n")
            f.write("SCRIPT: cleanup_l3_duplicates.py\n")
            f.write("OPTIMUS PRIME PROTOCOL ACTIVE\n")
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


def main():
    # Initialize logger
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    log_path = f'logs/cleanup/l3_cleanup_{timestamp}.log'
    logger = Logger(log_path)

    logger.log("=" * 70)
    logger.log("PHASE 1: L3 FILE CLEANUP")
    logger.log("=" * 70)
    logger.log("Objective: Remove duplicate L3 runs, keep only best data")
    logger.log("Protocol: OPTIMUS PRIME COMMANDMENTS.yml")
    logger.log("")

    # Cities that succeeded on Nov 8 at 23:12:25 (keep these from that timestamp)
    successful_cities = [
        'Albuquerque', 'Arlington', 'Atlanta', 'Austin', 'Bakersfield',
        'Baltimore', 'Boston', 'Charlotte', 'Chicago'
    ]

    logger.log("RETENTION POLICY:")
    logger.log("  - Keep ALL files from 2025-11-09_11-35-47 (today's re-run of 33 failed cities)")
    logger.log(f"  - Keep {len(successful_cities)} files from 2025-11-08_23-12-25 (yesterday's successful cities)")
    logger.log("  - DELETE all other timestamps")
    logger.log("")

    # Find all L3 files
    l3_dir = 'l3_llm_classify/outputs/fuse'
    all_files = sorted(glob.glob(f'{l3_dir}/l3_classified_*.json'))

    logger.log(f"📊 Found {len(all_files)} total L3 files")
    logger.log("")

    # Categorize files
    files_to_keep = []
    files_to_delete = []

    for filepath in all_files:
        filename = os.path.basename(filepath)

        # Extract timestamp from filename
        # Format: l3_classified_neurology_clinic_CITY_TIMESTAMP1_TIMESTAMP2.json
        # We want TIMESTAMP2 (the classification timestamp)
        parts = filename.split('_')

        # Find the timestamp part (second-to-last before .json)
        # Pattern: l3_classified_neurology_clinic_{city}_{l2_timestamp}_{l3_timestamp}.json
        if len(parts) >= 3:
            # Get last two parts and remove .json
            timestamp_candidate = '_'.join(parts[-2:]).replace('.json', '')

            # Keep files from today's re-run
            if '2025-11-09_11-35-47' in filename:
                files_to_keep.append(filepath)
                continue

            # Keep specific cities from yesterday's successful run
            if '2025-11-08_23-12-25' in filename:
                # Check if this city is in our successful list
                city_match = False
                for city in successful_cities:
                    if f'_clinic_{city}_' in filename.lower() or f'_clinic_{city.lower()}_' in filename:
                        city_match = True
                        break

                if city_match:
                    files_to_keep.append(filepath)
                    continue

            # Everything else gets deleted
            files_to_delete.append(filepath)

    logger.log("=" * 70)
    logger.log("FILE CATEGORIZATION COMPLETE")
    logger.log("=" * 70)
    logger.log(f"Files to KEEP: {len(files_to_keep)}")
    logger.log(f"Files to DELETE: {len(files_to_delete)}")
    logger.log("")

    # Show breakdown of files to keep
    keep_today = [f for f in files_to_keep if '2025-11-09_11-35-47' in f]
    keep_yesterday = [f for f in files_to_keep if '2025-11-08_23-12-25' in f]

    logger.log(f"✅ Keeping {len(keep_today)} files from today's re-run (2025-11-09_11-35-47)")
    logger.log(f"✅ Keeping {len(keep_yesterday)} files from yesterday's successful run (2025-11-08_23-12-25)")
    logger.log("")

    # Log files to delete by timestamp
    logger.log("🗑️  Files to delete by timestamp:")
    delete_by_timestamp = {}
    for filepath in files_to_delete:
        filename = os.path.basename(filepath)
        # Find timestamp in filename
        for ts in ['2025-11-08_19-22-18', '2025-11-08_14-25-17', '2025-11-08_12-47-04',
                   '2025-11-07_20-15-33', '2025-11-07_20-19-38', '2025-11-07_14-42-56',
                   '2025-11-08_23-12-25']:  # Include old successful run files
            if ts in filename:
                if ts not in delete_by_timestamp:
                    delete_by_timestamp[ts] = []
                delete_by_timestamp[ts].append(filepath)
                break

    for ts in sorted(delete_by_timestamp.keys()):
        logger.log(f"   {ts}: {len(delete_by_timestamp[ts])} files")
    logger.log("")

    # Execute deletion
    logger.log("=" * 70)
    logger.log("EXECUTING DELETION")
    logger.log("=" * 70)

    deleted_count = 0
    for filepath in files_to_delete:
        try:
            os.remove(filepath)
            deleted_count += 1
            logger.log(f"🗑️  Deleted: {os.path.basename(filepath)}", to_console=False)
        except Exception as e:
            logger.log(f"❌ ERROR deleting {filepath}: {e}")

    logger.log("")
    logger.log(f"✅ Successfully deleted {deleted_count} files")
    logger.log("")

    # Validate results
    remaining_files = sorted(glob.glob(f'{l3_dir}/l3_classified_*.json'))
    logger.log("=" * 70)
    logger.log("VALIDATION")
    logger.log("=" * 70)
    logger.log(f"Files remaining: {len(remaining_files)}")
    logger.log(f"Expected: {len(files_to_keep)}")

    if len(remaining_files) == len(files_to_keep):
        logger.log("✅ VALIDATION PASSED - File count matches expectation")
    else:
        logger.log("⚠️  WARNING - File count mismatch!")
    logger.log("")

    # Log remaining files
    logger.log("Remaining files by timestamp:")
    remaining_today = [f for f in remaining_files if '2025-11-09_11-35-47' in f]
    remaining_yesterday = [f for f in remaining_files if '2025-11-08_23-12-25' in f]
    logger.log(f"  - 2025-11-09_11-35-47: {len(remaining_today)} files")
    logger.log(f"  - 2025-11-08_23-12-25: {len(remaining_yesterday)} files")
    logger.log("")

    # Final summary
    logger.log("=" * 70)
    logger.log("PHASE 1 COMPLETE - L3 CLEANUP")
    logger.log("=" * 70)
    logger.log(f"Started with: {len(all_files)} files")
    logger.log(f"Deleted: {deleted_count} files")
    logger.log(f"Remaining: {len(remaining_files)} files")
    logger.log(f"Log file: {log_path}")
    logger.log("")
    logger.log("Next: PHASE 2 - Run L4 CSV Export")
    logger.log("=" * 70)
    logger.log(f"COMPLETED: {datetime.now().isoformat()}")
    logger.log("=" * 70)

    return {
        'total_files': len(all_files),
        'deleted': deleted_count,
        'remaining': len(remaining_files),
        'expected': len(files_to_keep),
        'validation': len(remaining_files) == len(files_to_keep)
    }


if __name__ == '__main__':
    result = main()
    exit(0 if result['validation'] else 1)
