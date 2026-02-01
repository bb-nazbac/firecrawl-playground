#!/usr/bin/env python3
"""
L4 CSV Export with Client Support
Exports filtered clinic data to client-specific CSV outputs
"""

import json
import csv
import glob
import os
import argparse
from datetime import datetime
from threading import Lock


class Logger:
    """Thread-safe logger with unbuffered writes"""
    def __init__(self, log_path):
        self.log_path = log_path
        self.lock = Lock()
        os.makedirs(os.path.dirname(log_path), exist_ok=True)

        with open(log_path, 'w', encoding='utf-8') as f:
            f.write("=" * 70 + "\n")
            f.write("SCRIPT: export_with_client.py\n")
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
    parser = argparse.ArgumentParser(description='L4 CSV Export with Client Support')
    parser.add_argument('--client', required=True, help='Client name (e.g., fuse)')
    parser.add_argument('--filter', default='independent', choices=['independent', 'all', 'hospital', 'university'],
                       help='Filter type: independent (neither hospital nor university), all, hospital, university')
    args = parser.parse_args()

    # Initialize logger
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    log_path = f'../logs/l4_csv_export/export_{args.client}_{args.filter}_{timestamp}.log'
    logger = Logger(log_path)

    logger.log("=" * 70)
    logger.log("ROUND 06: CLIENT-AWARE L4 CSV EXPORT")
    logger.log("=" * 70)
    logger.log(f"Client: {args.client}")
    logger.log(f"Filter: {args.filter}")
    logger.log(f"Log file: {log_path}")
    logger.log("")

    # Find L3 files for this client
    l3_pattern = f'../l3_llm_classify/outputs/{args.client}/l3_classified_*.json'
    l3_files = sorted(glob.glob(l3_pattern))

    if not l3_files:
        logger.log(f"❌ ERROR: No L3 files found for client '{args.client}'")
        logger.log(f"   Pattern: {l3_pattern}")
        return

    logger.log(f"📊 Found {len(l3_files)} L3 files to process:")
    for f in l3_files:
        logger.log(f"   - {os.path.basename(f)}")
    logger.log("")

    # Collect clinics based on filter
    clinics = []
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

        # Extract city from query (e.g., "Neurology clinic in Boston" -> "Boston")
        city_searched = "Unknown"
        if " in " in query:
            city_searched = query.split(" in ")[-1].strip()

        logger.log(f"📄 Processing: {query} (City: {city_searched})")

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

            # Apply filter
            include = False
            if args.filter == 'all':
                include = True
            elif args.filter == 'independent':
                include = (not is_hospital and not is_university)
            elif args.filter == 'hospital':
                include = is_hospital
            elif args.filter == 'university':
                include = is_university

            if not include:
                continue

            # Extract clinic data
            extracted = page.get('extracted_data', {})

            clinic_record = {
                'clinic_name': extracted.get('clinic_name', 'Unknown'),
                'city_searched': city_searched,
                'clinic_type': 'Individual' if classification == 'neurology_clinic_individual' else 'Group',
                'phone': extracted.get('phone') or '',
                'website': extracted.get('website') or '',
                'locations': ', '.join(extracted.get('locations', [])),
                'source_url': page.get('url', ''),
                'confidence': page.get('confidence', 'unknown'),
                'is_hospital': 'Yes' if is_hospital else 'No',
                'is_university': 'Yes' if is_university else 'No'
            }

            clinics.append(clinic_record)

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
    logger.log(f"Clinics matching filter '{args.filter}': {len(clinics)}")
    logger.log("")

    # Export to CSV
    output_dir = f'outputs/{args.client}'
    os.makedirs(output_dir, exist_ok=True)

    csv_filename = f'{output_dir}/{args.filter}_clinics_{timestamp}.csv'

    logger.log(f"💾 Exporting to CSV: {csv_filename}")
    logger.log("")

    fieldnames = ['clinic_name', 'city_searched', 'clinic_type', 'phone', 'website', 'locations',
                  'source_url', 'confidence', 'is_hospital', 'is_university']

    with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(clinics)

    logger.log("=" * 70)
    logger.log("EXPORT COMPLETE")
    logger.log("=" * 70)
    logger.log(f"✅ Exported {len(clinics)} clinics")
    logger.log(f"📁 Output file: {csv_filename}")
    logger.log(f"📊 File size: {os.path.getsize(csv_filename) / 1024:.1f} KB")
    logger.log("")

    # Sample preview
    if len(clinics) > 0:
        logger.log("Sample records (first 5):")
        for i, clinic in enumerate(clinics[:5], 1):
            logger.log(f"  {i}. {clinic['clinic_name']} ({clinic['clinic_type']})")
            if clinic['phone']:
                logger.log(f"     Phone: {clinic['phone']}")
            if clinic['website']:
                logger.log(f"     Website: {clinic['website']}")
            if clinic['locations']:
                logger.log(f"     Locations: {clinic['locations']}")

    logger.log("")
    logger.log("=" * 70)
    logger.log(f"✅ COMPLETED: {datetime.now().isoformat()}")
    logger.log("=" * 70)


if __name__ == '__main__':
    main()
