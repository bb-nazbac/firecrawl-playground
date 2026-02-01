#!/usr/bin/env python3
"""
PHASE 3: Error Tracking & Final Summary
OPTIMUS PRIME Protocol - Full Pipeline Audit
"""

import json
import glob
import os
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
            f.write("OPTIMUS PRIME PROTOCOL - PHASE 3 ERROR TRACKING\n")
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
    log_path = f'logs/error_tracking/phase3_final_audit_{timestamp}.log'
    logger = Logger(log_path)

    logger.log("=" * 70)
    logger.log("PHASE 3: ERROR TRACKING & FINAL SUMMARY")
    logger.log("=" * 70)
    logger.log("Protocol: OPTIMUS PRIME COMMANDMENTS.yml")
    logger.log("Objective: Full pipeline audit - L1 through L4")
    logger.log("")

    # Track errors across all layers
    errors = {
        'l1_search': [],
        'l2_scrape': [],
        'l3_classify': [],
        'l4_export': []
    }

    stats = {
        'l1_files': 0,
        'l2_files': 0,
        'l3_files': 0,
        'l4_files': 0,
        'total_searches': 0,
        'total_urls': 0,
        'successful_scrapes': 0,
        'failed_scrapes': 0,
        'total_classifications': 0,
        'classification_errors': 0,
        'individual_clinics': 0,
        'group_clinics': 0,
        'directories': 0,
        'other': 0,
        'final_exported_clinics': 0
    }

    # ========================================================================
    # LAYER 1: Search Results Analysis
    # ========================================================================
    logger.log("=" * 70)
    logger.log("LAYER 1: SEARCH RESULTS (L1)")
    logger.log("=" * 70)

    l1_files = sorted(glob.glob('outputs/l1_search_*.json'))
    stats['l1_files'] = len(l1_files)

    for l1_file in l1_files:
        try:
            with open(l1_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                stats['total_searches'] += 1
                stats['total_urls'] += len(data.get('results', []))
        except Exception as e:
            errors['l1_search'].append({
                'file': l1_file,
                'error': str(e)
            })

    logger.log(f"L1 Files: {stats['l1_files']}")
    logger.log(f"Total Searches: {stats['total_searches']}")
    logger.log(f"Total URLs Found: {stats['total_urls']}")
    logger.log(f"L1 Errors: {len(errors['l1_search'])}")
    logger.log("")

    # ========================================================================
    # LAYER 2: Scraping Results Analysis
    # ========================================================================
    logger.log("=" * 70)
    logger.log("LAYER 2: SCRAPING RESULTS (L2)")
    logger.log("=" * 70)

    l2_files = sorted(glob.glob('outputs/l2_scraped_*.json'))
    stats['l2_files'] = len(l2_files)

    for l2_file in l2_files:
        try:
            with open(l2_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                metadata = data.get('metadata', {})
                stats['successful_scrapes'] += metadata.get('successful_scrapes', 0)
                stats['failed_scrapes'] += metadata.get('failed_scrapes', 0)

                # Check for low success rates
                total = metadata.get('total_urls', 0)
                success = metadata.get('successful_scrapes', 0)
                if total > 0:
                    success_rate = success / total
                    if success_rate < 0.5:  # < 50% success rate
                        errors['l2_scrape'].append({
                            'file': os.path.basename(l2_file),
                            'query': metadata.get('query', 'Unknown'),
                            'success_rate': f"{success}/{total} ({success_rate*100:.1f}%)"
                        })
        except Exception as e:
            errors['l2_scrape'].append({
                'file': l2_file,
                'error': str(e)
            })

    logger.log(f"L2 Files: {stats['l2_files']}")
    logger.log(f"Successful Scrapes: {stats['successful_scrapes']:,}")
    logger.log(f"Failed Scrapes: {stats['failed_scrapes']:,}")
    if stats['successful_scrapes'] + stats['failed_scrapes'] > 0:
        total_scrapes = stats['successful_scrapes'] + stats['failed_scrapes']
        logger.log(f"L2 Success Rate: {stats['successful_scrapes']/total_scrapes*100:.1f}%")
    logger.log(f"L2 Low Success Rate Cities: {len(errors['l2_scrape'])}")
    logger.log("")

    # ========================================================================
    # LAYER 3: Classification Results Analysis
    # ========================================================================
    logger.log("=" * 70)
    logger.log("LAYER 3: CLASSIFICATION RESULTS (L3)")
    logger.log("=" * 70)

    l3_files = sorted(glob.glob('l3_llm_classify/outputs/fuse/l3_classified_*.json'))
    stats['l3_files'] = len(l3_files)

    for l3_file in l3_files:
        try:
            with open(l3_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                pages = data.get('pages', [])
                stats['total_classifications'] += len(pages)

                for page in pages:
                    classification = page.get('classification', '')
                    if classification == 'neurology_clinic_individual':
                        stats['individual_clinics'] += 1
                    elif classification == 'neurology_clinic_group':
                        stats['group_clinics'] += 1
                    elif classification == 'directory':
                        stats['directories'] += 1
                    elif classification == 'error':
                        stats['classification_errors'] += 1
                        errors['l3_classify'].append({
                            'file': os.path.basename(l3_file),
                            'url': page.get('url', 'Unknown')[:80],
                            'error': page.get('reasoning', 'Unknown error')
                        })
                    else:
                        stats['other'] += 1
        except Exception as e:
            errors['l3_classify'].append({
                'file': l3_file,
                'error': str(e)
            })

    logger.log(f"L3 Files: {stats['l3_files']}")
    logger.log(f"Total Pages Classified: {stats['total_classifications']:,}")
    logger.log(f"  - Individual Clinics: {stats['individual_clinics']:,}")
    logger.log(f"  - Group Clinics: {stats['group_clinics']:,}")
    logger.log(f"  - Directories: {stats['directories']:,}")
    logger.log(f"  - Other: {stats['other']:,}")
    logger.log(f"  - Errors: {stats['classification_errors']:,}")
    if stats['total_classifications'] > 0:
        logger.log(f"L3 Error Rate: {stats['classification_errors']/stats['total_classifications']*100:.2f}%")
    logger.log("")

    # ========================================================================
    # LAYER 4: Export Results Analysis
    # ========================================================================
    logger.log("=" * 70)
    logger.log("LAYER 4: CSV EXPORT (L4)")
    logger.log("=" * 70)

    l4_files = sorted(glob.glob('l4_csv_export/outputs/fuse/*.csv'))
    stats['l4_files'] = len(l4_files)

    if l4_files:
        latest_csv = l4_files[-1]
        logger.log(f"Latest CSV Export: {os.path.basename(latest_csv)}")

        # Count rows in CSV
        try:
            with open(latest_csv, 'r', encoding='utf-8') as f:
                # Subtract 1 for header row
                stats['final_exported_clinics'] = sum(1 for line in f) - 1

            file_size_kb = os.path.getsize(latest_csv) / 1024

            logger.log(f"Exported Clinics: {stats['final_exported_clinics']:,}")
            logger.log(f"File Size: {file_size_kb:.1f} KB")
        except Exception as e:
            errors['l4_export'].append({
                'file': latest_csv,
                'error': str(e)
            })
    else:
        logger.log("⚠️  WARNING: No L4 CSV files found!")

    logger.log("")

    # ========================================================================
    # ERROR SUMMARY
    # ========================================================================
    logger.log("=" * 70)
    logger.log("ERROR SUMMARY")
    logger.log("=" * 70)

    total_errors = sum(len(e) for e in errors.values())
    logger.log(f"Total Errors Across Pipeline: {total_errors}")
    logger.log("")

    for layer, layer_errors in errors.items():
        logger.log(f"{layer.upper()}: {len(layer_errors)} errors")
        if layer_errors:
            for i, err in enumerate(layer_errors[:5], 1):  # Show first 5
                logger.log(f"  {i}. {err}")
            if len(layer_errors) > 5:
                logger.log(f"  ... and {len(layer_errors) - 5} more")
        logger.log("")

    # ========================================================================
    # PRIME DIRECTIVE ASSESSMENT
    # ========================================================================
    logger.log("=" * 70)
    logger.log("PRIME DIRECTIVE: 95% CONFIDENCE ASSESSMENT")
    logger.log("=" * 70)

    # Calculate confidence metrics
    l2_success_rate = stats['successful_scrapes'] / (stats['successful_scrapes'] + stats['failed_scrapes']) if (stats['successful_scrapes'] + stats['failed_scrapes']) > 0 else 0
    l3_success_rate = 1 - (stats['classification_errors'] / stats['total_classifications']) if stats['total_classifications'] > 0 else 0
    l4_success = stats['final_exported_clinics'] > 0

    logger.log(f"L2 Scraping Success Rate: {l2_success_rate*100:.1f}%")
    logger.log(f"L3 Classification Success Rate: {l3_success_rate*100:.2f}%")
    logger.log(f"L4 Export Success: {'YES' if l4_success else 'NO'}")
    logger.log("")

    # Overall confidence
    overall_confidence = (l2_success_rate + l3_success_rate + (1 if l4_success else 0)) / 3 * 100

    logger.log(f"OVERALL PIPELINE CONFIDENCE: {overall_confidence:.1f}%")

    if overall_confidence >= 95:
        logger.log("✅ PRIME DIRECTIVE MET - Pipeline operating at ≥95% confidence")
    else:
        logger.log(f"⚠️  BELOW PRIME DIRECTIVE - {95 - overall_confidence:.1f}% short of 95% target")

    logger.log("")

    # ========================================================================
    # FINAL SUMMARY
    # ========================================================================
    logger.log("=" * 70)
    logger.log("FINAL SUMMARY - OPTIMUS PRIME PROTOCOL")
    logger.log("=" * 70)
    logger.log(f"L1 Searches: {stats['total_searches']} searches → {stats['total_urls']:,} URLs")
    logger.log(f"L2 Scraping: {stats['successful_scrapes']:,}/{stats['successful_scrapes']+stats['failed_scrapes']:,} successful ({l2_success_rate*100:.1f}%)")
    logger.log(f"L3 Classification: {stats['total_classifications']:,} pages → {stats['individual_clinics']+stats['group_clinics']:,} clinics ({l3_success_rate*100:.2f}% success)")
    logger.log(f"L4 Export: {stats['final_exported_clinics']:,} independent clinics exported")
    logger.log("")
    logger.log(f"Total Errors: {total_errors}")
    logger.log(f"Pipeline Confidence: {overall_confidence:.1f}%")
    logger.log("")
    logger.log("=" * 70)
    logger.log(f"COMPLETED: {datetime.now().isoformat()}")
    logger.log(f"LOG FILE: {log_path}")
    logger.log("=" * 70)

    return {
        'stats': stats,
        'errors': errors,
        'confidence': overall_confidence,
        'meets_prime_directive': overall_confidence >= 95
    }


if __name__ == '__main__':
    result = main()
    exit(0 if result['meets_prime_directive'] else 1)
