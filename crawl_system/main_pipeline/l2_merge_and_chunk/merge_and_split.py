#!/usr/bin/env python3
"""
L2: Merge Segments and Split into 1-Page Chunks
Combines merge_segments.py and split_into_chunks.py from Round 8
"""
import json
import os
from pathlib import Path
from datetime import datetime

# Get client and domain from environment
CLIENT = os.getenv("CLIENT", "default")
DOMAIN = os.getenv("DOMAIN", "default")

# Use relative paths with client/domain-specific folders
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
SEGMENTS_DIR = PROJECT_ROOT / "l1_crawl_with_markdown" / "outputs" / CLIENT / DOMAIN / "segments"
OUTPUT_DIR = SCRIPT_DIR / "outputs" / CLIENT / DOMAIN
CHUNKS_DIR = OUTPUT_DIR / "chunks"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
CHUNKS_DIR.mkdir(parents=True, exist_ok=True)

print("L2: Merging segments and creating chunks...")

# Merge all segments
segment_files = sorted(SEGMENTS_DIR.glob("segment_*.json"))
print(f"Found {len(segment_files)} segments")

all_pages = []
for seg_file in segment_files:
    with open(seg_file) as f:
        data = json.load(f)
        all_pages.extend(data.get('data', []))

print(f"Total pages: {len(all_pages)}")

# Create 1-page chunks
print("Creating chunks (1 page per chunk)...")

for i, page in enumerate(all_pages, 1):
    chunk_data = {
        'chunk_id': i,
        'page_count': 1,
        'pages': [{
            'id': 1,
            'url': page.get('metadata', {}).get('sourceURL', ''),
            'title': page.get('metadata', {}).get('title', ''),
            'markdown': page.get('markdown', ''),
            'markdown_length': len(page.get('markdown', ''))
        }]
    }
    
    chunk_file = CHUNKS_DIR / f"chunk_{i:04d}.json"
    with open(chunk_file, 'w') as f:
        json.dump(chunk_data, f)
    
    if i % 1000 == 0:
        print(f"  Created {i}/{len(all_pages)} chunks...")

print(f"✅ Created {len(all_pages)} chunks")
print(f"   Saved to: {CHUNKS_DIR}")

