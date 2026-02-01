#!/usr/bin/env python3
"""
L3: Split Merged Data into LLM-Sized Chunks
Input: Merged file from L2
Output: Multiple JSON chunks (max 2000 tokens each)
"""

import json
from pathlib import Path
from datetime import datetime

# Paths
BASE = Path("/Users/bahaa/Documents/Clients/Toolbx/firecrawl_playground/testing_and_learning/round8_crawl_with_markdown")
INPUT_DIR = BASE / "l2_merge_and_prepare" / "outputs"
OUTPUT_DIR = BASE / "l3_llm_classification" / "outputs"
LOG_DIR = BASE / "l3_llm_classification" / "logs"

OUTPUT_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE = LOG_DIR / f"split_{TIMESTAMP}.log"

# Config  
MAX_PAGES_PER_CHUNK = 1  # ONE PAGE PER CHUNK for better extraction
CHARS_PER_TOKEN = 4  # Rough estimate

def log(msg):
    with open(LOG_FILE, 'a') as f:
        f.write(f"[{datetime.now()}] {msg}\n")

def estimate_tokens(text):
    """Rough token estimation"""
    return len(text) // CHARS_PER_TOKEN

def create_chunk_for_llm(pages):
    """Format pages for LLM classification with FULL markdown"""
    formatted = []
    
    for i, page in enumerate(pages, 1):
        url = page.get('metadata', {}).get('sourceURL', 'N/A')
        title = page.get('metadata', {}).get('title', 'N/A')
        markdown = page.get('markdown', '')
        
        # Use FULL markdown - no preview limit!
        formatted.append({
            'id': i,
            'url': url,
            'title': title,
            'markdown': markdown,  # FULL content
            'markdown_length': len(markdown)
        })
    
    return formatted

try:
    log("="*80)
    log("L3: SPLITTING INTO LLM CHUNKS")
    log("="*80)
    
    # Find merged file
    merged_files = list(INPUT_DIR.glob("all_pages_merged_*.json"))
    if not merged_files:
        raise FileNotFoundError("No merged file found in L2 outputs!")
    
    input_file = merged_files[0]
    log(f"Loading merged file: {input_file.name}")
    
    with open(input_file) as f:
        data = json.load(f)
    
    all_pages = data.get('pages', [])
    log(f"Total pages to process: {len(all_pages)}")
    
    # Split into chunks - 1 page per chunk
    log(f"Splitting into chunks (1 page per chunk)...")
    
    chunks = []
    
    for page in all_pages:
        # Each page gets its own chunk
        chunks.append([page])
    
    log(f"Created {len(chunks)} chunks")
    
    # Save each chunk
    log("Saving chunks...")
    chunk_dir = OUTPUT_DIR / "chunks"
    chunk_dir.mkdir(exist_ok=True)
    
    for i, chunk_pages in enumerate(chunks, 1):
        formatted_chunk = create_chunk_for_llm(chunk_pages)
        
        chunk_file = chunk_dir / f"chunk_{i:04d}.json"
        with open(chunk_file, 'w') as f:
            json.dump({
                'chunk_id': i,
                'page_count': len(formatted_chunk),
                'pages': formatted_chunk
            }, f, indent=2)
        
        if i % 100 == 0:
            log(f"  Saved chunk {i}/{len(chunks)}")
    
    log(f"✅ All {len(chunks)} chunks saved to: chunks/")
    
    # Create summary
    summary = {
        'timestamp': TIMESTAMP,
        'total_pages': len(all_pages),
        'total_chunks': len(chunks),
        'pages_per_chunk': 1,
        'chunks_directory': str(chunk_dir)
    }
    
    summary_file = OUTPUT_DIR / f"split_summary_{TIMESTAMP}.json"
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    
    log(f"\nSummary:")
    log(f"  Total pages: {len(all_pages)}")
    log(f"  Total chunks: {len(chunks)}")
    log(f"  Pages per chunk: 1 (one page per chunk)")
    log(f"  Chunks saved to: {chunk_dir}")
    
    log("="*80)
    log("L3 SPLIT COMPLETE!")
    log("="*80)
    
except Exception as e:
    log(f"ERROR: {e}")
    import traceback
    log(traceback.format_exc())

