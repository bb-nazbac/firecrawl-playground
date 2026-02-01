#!/usr/bin/env python3
"""
Identify and re-scrape failed L2 cities (< 50% success rate)
"""
import json
import glob
import os
import subprocess
from datetime import datetime

# Find all L2 files with low success rates
failed_cities = []
outputs_dir = 'outputs'

print("=" * 70)
print("IDENTIFYING FAILED L2 SCRAPES")
print("=" * 70)

for l2_file in sorted(glob.glob(f'{outputs_dir}/l2_scraped_*.json')):
    try:
        with open(l2_file, 'r') as f:
            data = json.load(f)
            success = data['metadata']['successful_scrapes']
            total = data['metadata']['total_urls']
            pct = int(success * 100 / total) if total > 0 else 0

            if pct < 50:
                # Extract city name from filename
                basename = os.path.basename(l2_file)
                # l2_scraped_neurology_clinic_CITYNAME_TIMESTAMP.json
                parts = basename.replace('l2_scraped_neurology_clinic_', '').split('_2025')
                city = parts[0]

                # Find corresponding L1 file
                l1_pattern = f'{outputs_dir}/l1_search_neurology_clinic_{city}_*.json'
                l1_files = glob.glob(l1_pattern)

                if l1_files:
                    l1_file = l1_files[0]  # Take the first (latest) one
                    failed_cities.append({
                        'city': city,
                        'l1_file': l1_file,
                        'l2_file': l2_file,
                        'success_rate': f'{success}/{total} ({pct}%)'
                    })
                    print(f"❌ {city}: {success}/{total} ({pct}%) -> Will re-scrape from {os.path.basename(l1_file)}")
    except Exception as e:
        print(f"⚠️  Error processing {l2_file}: {e}")

print()
print(f"Total failed cities: {len(failed_cities)}")
print()

if not failed_cities:
    print("✅ No failed cities found! All L2 scrapes were successful.")
    exit(0)

# Create a temporary directory with symlinks to only the failed L1 files
temp_dir = 'outputs/temp_failed_l1'
os.makedirs(temp_dir, exist_ok=True)

# Clean temp dir
for f in glob.glob(f'{temp_dir}/*'):
    os.remove(f)

# Create symlinks
for city_data in failed_cities:
    src = os.path.abspath(city_data['l1_file'])
    dst = os.path.join(temp_dir, os.path.basename(city_data['l1_file']))
    os.symlink(src, dst)
    print(f"📎 Linked: {os.path.basename(city_data['l1_file'])}")

print()
print("=" * 70)
print("🚀 Ready to re-scrape failed cities")
print("=" * 70)
print(f"L1 files linked in: {temp_dir}")
print(f"Cities to re-scrape: {', '.join([c['city'] for c in failed_cities])}")
print()
print("Next step: Modify scrape script to process only files in temp_failed_l1/")
