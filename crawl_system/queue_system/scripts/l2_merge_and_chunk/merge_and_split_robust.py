#!/usr/bin/env python3
"""
L2: Merge Segments and Split into 1-Page Chunks (ROBUST VERSION)
- Validates segment files before processing
- Handles malformed JSON gracefully
- Checks for empty/invalid content
- Validates disk space before writing
"""
import json
import os
import sys
import shutil
from pathlib import Path

def log(msg):
    """Print with flush for real-time logging"""
    print(msg, flush=True)

def check_disk_space(path, required_mb=100):
    """
    Check if there's enough disk space
    Returns: (bool, int) - (has_space, available_mb)
    """
    stat = shutil.disk_usage(path)
    available_mb = stat.free / (1024 * 1024)
    return (available_mb >= required_mb, int(available_mb))

def validate_segment_file(seg_file):
    """
    Validate a segment file
    Returns: (success: bool, pages: list, error: str/None)
    """
    try:
        with open(seg_file) as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return (False, [], f"Invalid format: not a dict")

        pages = data.get('data', [])
        if not isinstance(pages, list):
            return (False, [], f"Invalid format: 'data' is not a list")

        return (True, pages, None)

    except json.JSONDecodeError as e:
        return (False, [], f"JSON decode error: {e}")
    except IOError as e:
        return (False, [], f"File read error: {e}")

def main():
    # Get client and domain from environment
    CLIENT = os.getenv("CLIENT", "default")
    DOMAIN = os.getenv("DOMAIN", "default")

    # Use queue_system directory structure
    SCRIPT_DIR = Path(__file__).parent.parent.parent
    SEGMENTS_DIR = SCRIPT_DIR / "outputs" / CLIENT / DOMAIN / "segments"
    OUTPUT_DIR = SCRIPT_DIR / "outputs" / CLIENT / DOMAIN
    CHUNKS_DIR = OUTPUT_DIR / "chunks"

    log(f"🔧 L2: Merging segments and creating chunks...")
    log(f"   Client: {CLIENT}")
    log(f"   Domain: {DOMAIN}")
    log(f"   Segments: {SEGMENTS_DIR}")

    # ============================================================================
    # PHASE 1: Validate inputs
    # ============================================================================
    log("\n[PHASE 1] Validating inputs...")

    # Check if segments directory exists
    if not SEGMENTS_DIR.exists():
        log(f"❌ Segments directory not found: {SEGMENTS_DIR}")
        log(f"   L1 may have failed or not run yet")
        sys.exit(1)

    # Find segment files
    segment_files = sorted(SEGMENTS_DIR.glob("segment_*.json"))

    if not segment_files:
        log(f"❌ No segment files found in {SEGMENTS_DIR}")
        log(f"   L1 may have failed")
        sys.exit(1)

    log(f"✅ Found {len(segment_files)} segment files")

    # Check disk space (require at least 100MB free)
    has_space, available_mb = check_disk_space(SEGMENTS_DIR.parent)
    if not has_space:
        log(f"❌ Insufficient disk space: {available_mb}MB available (need 100MB)")
        sys.exit(1)

    log(f"✅ Disk space: {available_mb}MB available")

    # ============================================================================
    # PHASE 2: Merge segments with validation
    # ============================================================================
    log("\n[PHASE 2] Merging segments...")

    all_pages = []
    failed_segments = []

    for seg_file in segment_files:
        success, pages, error = validate_segment_file(seg_file)

        if not success:
            log(f"  ⚠️  Failed to parse {seg_file.name}: {error}")
            failed_segments.append(seg_file.name)
            continue

        all_pages.extend(pages)
        log(f"  {seg_file.name}: {len(pages)} pages")

    if failed_segments:
        log(f"\n⚠️  {len(failed_segments)} segments failed to parse:")
        for seg in failed_segments:
            log(f"     - {seg}")

    if not all_pages:
        log(f"\n❌ No pages extracted from segments")
        sys.exit(1)

    log(f"\n✅ Merged {len(all_pages)} pages from {len(segment_files) - len(failed_segments)}/{len(segment_files)} segments")

    # ============================================================================
    # PHASE 3: Create chunks with validation
    # ============================================================================
    log("\n[PHASE 3] Creating chunks...")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)

    chunks_created = 0
    chunks_failed = 0
    empty_pages = 0

    for i, page in enumerate(all_pages, 1):
        # Validate page has content
        markdown = page.get('markdown', '')

        if not markdown or len(markdown.strip()) == 0:
            empty_pages += 1
            # Skip empty pages but don't fail
            continue

        chunk_data = {
            'chunk_id': i,
            'page_count': 1,
            'pages': [{
                'id': 1,
                'url': page.get('metadata', {}).get('sourceURL', ''),
                'title': page.get('metadata', {}).get('title', ''),
                'markdown': markdown,
                'markdown_length': len(markdown)
            }]
        }

        chunk_file = CHUNKS_DIR / f"chunk_{i:04d}.json"

        try:
            with open(chunk_file, 'w') as f:
                json.dump(chunk_data, f, indent=2)
            chunks_created += 1

            if chunks_created % 1000 == 0:
                log(f"  Created {chunks_created} chunks...")

        except IOError as e:
            log(f"  ⚠️  Failed to write chunk {i}: {e}")
            chunks_failed += 1

            # If too many write failures, disk might be full
            if chunks_failed > 10:
                log(f"❌ Too many write failures ({chunks_failed}), aborting")
                log(f"   Check disk space and permissions")
                sys.exit(1)

    # ============================================================================
    # PHASE 4: Validate results
    # ============================================================================
    log("\n[PHASE 4] Validation...")

    if chunks_created == 0:
        log(f"❌ No chunks created")
        sys.exit(1)

    if empty_pages > 0:
        log(f"⚠️  Skipped {empty_pages} empty pages")

    if chunks_failed > 0:
        log(f"⚠️  {chunks_failed} chunks failed to write")

    log(f"\n✅ L2 COMPLETE")
    log(f"   Chunks: {chunks_created}")
    log(f"   Empty pages skipped: {empty_pages}")
    log(f"   Failed: {chunks_failed}")
    log(f"   Location: {CHUNKS_DIR}")

    return 0

if __name__ == "__main__":
    sys.exit(main())
