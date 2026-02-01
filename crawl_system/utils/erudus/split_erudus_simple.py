#!/usr/bin/env python3
"""
Split Erudus chunk into 10 smaller chunks - simple line-based approach
"""

import json

# Read the original chunk
with open('l2_merge_and_chunk/outputs/openinfo/erudus/chunks/chunk_0001.json', 'r') as f:
    original_chunk = json.load(f)

markdown = original_chunk['pages'][0]['markdown']
url = original_chunk['pages'][0]['url']
title = original_chunk['pages'][0]['title']

print(f"Original markdown length: {len(markdown)} characters")

# Split markdown by company entries
# The wholesalers section has 194 companies
# The manufacturers section has 1,490 companies
# Total: 1,684 companies

# Let's split by looking for bullet points
lines = markdown.split('\n')
print(f"Total lines: {len(lines)}")

# Find where sections start
wholesalers_start = None
manufacturers_start = None
footer_start = None

for i, line in enumerate(lines):
    if line == "## Wholesalers":
        wholesalers_start = i
        print(f"Wholesalers start at line {i}")
    elif line == "## Manufacturers":
        manufacturers_start = i
        print(f"Manufacturers start at line {i}")
    elif line.startswith("### Stay in the loop"):
        footer_start = i
        print(f"Footer starts at line {i}")

if not all([wholesalers_start, manufacturers_start, footer_start]):
    print("ERROR: Could not find all sections!")
    exit(1)

# Extract sections
header_lines = lines[:wholesalers_start]
wholesalers_lines = lines[wholesalers_start:manufacturers_start]
manufacturers_lines = lines[manufacturers_start:footer_start]

# Count actual company entries (lines starting with "- ")
wholesalers_companies = [l for l in wholesalers_lines if l.startswith("- ")]
manufacturers_companies = [l for l in manufacturers_lines if l.startswith("- ")]

print(f"Wholesalers: {len(wholesalers_companies)} companies")
print(f"Manufacturers: {len(manufacturers_companies)} companies")
print(f"Total: {len(wholesalers_companies) + len(manufacturers_companies)} companies")

# Create 10 chunks:
# Chunk 1: Header + all wholesalers (194 companies)
# Chunks 2-10: Manufacturers split into 9 parts (~165 each)

chunks_data = []

# Chunk 1: Header + Wholesalers
chunk1_lines = header_lines + wholesalers_lines
chunk1_md = '\n'.join(chunk1_lines)
chunks_data.append({
    "chunk_id": 1,
    "page_count": 1,
    "pages": [{
        "id": 1,
        "url": url,
        "title": f"{title} - Part 1/10 (Wholesalers)",
        "markdown": chunk1_md,
        "markdown_length": len(chunk1_md)
    }]
})
print(f"Chunk 1: {len(wholesalers_companies)} companies, {len(chunk1_md)} chars")

# Split manufacturers into 9 chunks
manufacturers_per_chunk = len(manufacturers_companies) // 9
remainder = len(manufacturers_companies) % 9

start_idx = 0
for i in range(9):
    chunk_size = manufacturers_per_chunk + (1 if i < remainder else 0)
    end_idx = start_idx + chunk_size

    chunk_companies = manufacturers_companies[start_idx:end_idx]

    # Build markdown for this chunk
    # Include header (minus the "Wholesalers" text) + this slice of manufacturers
    chunk_header = []
    for line in header_lines:
        if "Wholesalers" not in line:
            chunk_header.append(line)

    chunk_lines = chunk_header + ["## Manufacturers", ""] + chunk_companies
    chunk_md = '\n'.join(chunk_lines)

    chunks_data.append({
        "chunk_id": i + 2,
        "page_count": 1,
        "pages": [{
            "id": 1,
            "url": url,
            "title": f"{title} - Part {i + 2}/10 (Manufacturers {start_idx + 1}-{end_idx})",
            "markdown": chunk_md,
            "markdown_length": len(chunk_md)
        }]
    })

    print(f"Chunk {i + 2}: {len(chunk_companies)} companies, {len(chunk_md)} chars")
    start_idx = end_idx

# Write all chunks
for chunk in chunks_data:
    chunk_file = f"l2_merge_and_chunk/outputs/openinfo/erudus/chunks/chunk_{chunk['chunk_id']:04d}.json"
    with open(chunk_file, 'w') as f:
        json.dump(chunk, f, indent=2)
    print(f"Created {chunk_file}")

print(f"\nSuccessfully created {len(chunks_data)} chunks!")
