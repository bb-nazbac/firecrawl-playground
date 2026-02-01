#!/usr/bin/env python3
"""
L2: Merge All Segments into Single Organized File
Input: 308 segment JSON files from L1
Output: Single merged file with all pages
"""

import json
from pathlib import Path
from datetime import datetime

# Paths
BASE = Path("/Users/bahaa/Documents/Clients/Toolbx/firecrawl_playground/testing_and_learning/round8_crawl_with_markdown")
SEGMENTS_DIR = BASE / "l1_crawl_with_markdown" / "outputs" / "segments"
OUTPUT_DIR = BASE / "l2_merge_and_prepare" / "outputs"
LOG_DIR = BASE / "l2_merge_and_prepare" / "logs"

OUTPUT_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE = LOG_DIR / f"merge_{TIMESTAMP}.log"

def log(msg):
    with open(LOG_FILE, 'a') as f:
        f.write(f"[{datetime.now()}] {msg}\n")

try:
    log("="*80)
    log("L2: MERGING ALL SEGMENTS")
    log("="*80)
    
    # Find all segment files
    segment_files = sorted(SEGMENTS_DIR.glob("segment_*.json"))
    log(f"Found {len(segment_files)} segment files")
    
    # Merge all pages
    all_pages = []
    
    for i, seg_file in enumerate(segment_files, 1):
        if i % 50 == 0:
            log(f"Processing segment {i}/{len(segment_files)}...")
        
        with open(seg_file) as f:
            data = json.load(f)
            pages = data.get('data', [])
            all_pages.extend(pages)
    
    log(f"Total pages merged: {len(all_pages)}")
    
    # Organize data
    log("Organizing merged data...")
    organized_data = {
        'metadata': {
            'source': 'ACHR Directory - Complete Crawl with Markdown',
            'timestamp': TIMESTAMP,
            'total_pages': len(all_pages),
            'segments_processed': len(segment_files)
        },
        'pages': all_pages
    }
    
    # Save merged file
    output_file = OUTPUT_DIR / f"all_pages_merged_{TIMESTAMP}.json"
    log(f"Saving merged file to: {output_file}")
    
    with open(output_file, 'w') as f:
        json.dump(organized_data, f, indent=2)
    
    file_size_mb = output_file.stat().st_size / (1024 * 1024)
    log(f"✅ Merged file saved!")
    log(f"   File size: {file_size_mb:.2f} MB")
    log(f"   Total pages: {len(all_pages)}")
    
    # Calculate statistics
    log("\nCalculating statistics...")
    total_markdown_chars = sum(len(page.get('markdown', '')) for page in all_pages)
    avg_markdown_size = total_markdown_chars / len(all_pages) if all_pages else 0
    
    log(f"   Total markdown characters: {total_markdown_chars:,}")
    log(f"   Average markdown per page: {avg_markdown_size:.0f} chars")
    log(f"   Estimated tokens (÷4): {total_markdown_chars // 4:,}")
    
    log("="*80)
    log("L2 COMPLETE!")
    log("="*80)
    
except Exception as e:
    log(f"ERROR: {e}")
    import traceback
    log(traceback.format_exc())

