#!/usr/bin/env python3
"""
L4 CSV Export: Independent Clinics Filter & Export
Filters L3 classified clinics for independent practices (neither hospital nor university)
and exports to business-actionable CSV format.
"""

import json
import csv
import glob
import os
from datetime import datetime
from threading import Lock


class Logger:
    """Thread-safe logger with unbuffered writes"""
    def __init__(self, log_path):
        self.log_path = log_path
        self.lock = Lock()
        os.makedirs(os.path.dirname(log_path), exist_ok=True)

        # Initialize log file with header
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write("=" * 70 + "\n")
            f.write("SCRIPT: export_independent_clinics.py\n")
            f.write("ROUND: 06 - SerpAPI Testing\n")
            f.write("LAYER: L4 - CSV Export (Independent Clinics Filter)\n")
            f.write(f"STARTED: {datetime.now().isoformat()}\n")
            f.write("=" * 70 + "\n\n")
            f.flush()

    def log(self, message, to_console=True):
        """Write log message with timestamp"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_line = f"[{timestamp}] {message}\n"

        with self.lock:
            with open(self.log_path, 'a', encoding='utf-8') as f:
                f.write(log_line)
                f.flush()
                os.fsync(f.fileno())  # Force write to disk

            if to_console:
                print(message, flush=True)


def main():
    # Initialize logger
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    log_path = f'../logs/l4_csv_export/export_independent_clinics_{timestamp}.log'
    logger = Logger(log_path)

    logger.log("=" * 70)
    logger.log("ROUND 06: L4 CSV EXPORT - INDEPENDENT CLINICS")
    logger.log("=" * 70)
    logger.log("Client: Fuse")
    logger.log("Filter: is_hospital_or_dept='no' AND university_affiliated='no'")
    logger.log(f"Log file: {log_path}")
    logger.log("")

    # Find all L3 classified files (latest versions only)
    l3_pattern = '../l3_llm_classify/outputs/l3_classified_*_20251106_13[2-3]*.json'
    l3_files = sorted(glob.glob(l3_pattern))

    if not l3_files:
        logger.log("❌ ERROR: No L3 files found matching pattern")
        logger.log(f"   Pattern: {l3_pattern}")
        return

    logger.log(f"📊 Found {len(l3_files)} L3 files to process:")
    for f in l3_files:
        logger.log(f"   - {os.path.basename(f)}")
    logger.log("")

    # Collect independent clinics
    independent_clinics = []
    stats = {
        'total_clinics': 0,
        'hospital_only': 0,
        'university_only': 0,
        'both': 0,
        'independent': 0,
        'individual_clinics': 0,
        'group_clinics': 0
    }

    logger.log("Processing L3 files...")
    logger.log("")

    for l3_file in l3_files:
        with open(l3_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        query = data.get('metadata', {}).get('query', 'Unknown')
        logger.log(f"📄 Processing: {query}")

        for page in data.get('pages', []):
            classification = page.get('classification', '')

            # Only process actual clinics
            if classification not in ['neurology_clinic_individual', 'neurology_clinic_group']:
                continue

            stats['total_clinics'] += 1

            # Get affiliation data
            is_hospital = page.get('is_hospital_or_dept', {}).get('answer', 'no') == 'yes'
            is_university = page.get('university_affiliated', {}).get('answer', 'no') == 'yes'

            # Count categories
            if is_hospital and is_university:
                stats['both'] += 1
            elif is_hospital:
                stats['hospital_only'] += 1
            elif is_university:
                stats['university_only'] += 1
            else:
                stats['independent'] += 1

                # This is an independent clinic - extract for CSV
                extracted = page.get('extracted_data', {})

                clinic_record = {
                    'clinic_name': extracted.get('clinic_name', 'Unknown'),
                    'clinic_type': 'Individual' if classification == 'neurology_clinic_individual' else 'Group',
                    'phone': extracted.get('phone') or '',
                    'website': extracted.get('website') or '',
                    'locations': ', '.join(extracted.get('locations', [])),
                    'source_url': page.get('url', ''),
                    'confidence': page.get('confidence', 'unknown')
                }

                independent_clinics.append(clinic_record)

                if classification == 'neurology_clinic_individual':
                    stats['individual_clinics'] += 1
                else:
                    stats['group_clinics'] += 1

        logger.log(f"   Processed {stats['total_clinics']} clinics so far...")

    logger.log("")
    logger.log("=" * 70)
    logger.log("FILTERING RESULTS")
    logger.log("=" * 70)
    logger.log(f"Total Clinics Processed: {stats['total_clinics']}")
    logger.log(f"  - Hospital/Dept ONLY: {stats['hospital_only']}")
    logger.log(f"  - University ONLY: {stats['university_only']}")
    logger.log(f"  - BOTH Hospital & University: {stats['both']}")
    logger.log(f"  - INDEPENDENT (NEITHER): {stats['independent']}")
    logger.log("")
    logger.log(f"Independent Clinic Breakdown:")
    logger.log(f"  - Individual practices: {stats['individual_clinics']}")
    logger.log(f"  - Group practices: {stats['group_clinics']}")
    logger.log("")

    # Export to CSV
    output_dir = 'outputs'
    os.makedirs(output_dir, exist_ok=True)

    csv_filename = f'{output_dir}/independent_clinics_filtered.csv'

    logger.log(f"💾 Exporting to CSV: {csv_filename}")
    logger.log("")

    with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['clinic_name', 'clinic_type', 'phone', 'website', 'locations', 'source_url', 'confidence']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        writer.writerows(independent_clinics)

    logger.log("=" * 70)
    logger.log("EXPORT COMPLETE")
    logger.log("=" * 70)
    logger.log(f"✅ Exported {len(independent_clinics)} independent clinics")
    logger.log(f"📁 Output file: {csv_filename}")
    logger.log(f"📊 File size: {os.path.getsize(csv_filename) / 1024:.1f} KB")
    logger.log("")

    # Sample preview
    logger.log("Sample records (first 5):")
    for i, clinic in enumerate(independent_clinics[:5], 1):
        logger.log(f"  {i}. {clinic['clinic_name']} ({clinic['clinic_type']})")
        if clinic['phone']:
            logger.log(f"     Phone: {clinic['phone']}")
        if clinic['website']:
            logger.log(f"     Website: {clinic['website']}")
        if clinic['locations']:
            logger.log(f"     Locations: {clinic['locations']}")

    logger.log("")
    logger.log("=" * 70)
    logger.log("PERFORMANCE METRICS")
    logger.log("=" * 70)
    logger.log(f"- L3 Files Processed: {len(l3_files)}")
    logger.log(f"- Total Clinics: {stats['total_clinics']}")
    logger.log(f"- Independent Clinics Exported: {stats['independent']}")
    logger.log(f"- Filter Rate: {100*stats['independent']/stats['total_clinics']:.1f}%")
    logger.log("=" * 70)
    logger.log("")
    logger.log(f"✅ COMPLETED: {datetime.now().isoformat()}")
    logger.log("=" * 70)


if __name__ == '__main__':
    main()
