#!/usr/bin/env python3
"""
Split Erudus chunk into 10 smaller chunks to work around LLM token limit.
"""

import json
import re

# Read the original chunk
with open('l2_merge_and_chunk/outputs/openinfo/erudus/chunks/chunk_0001.json', 'r') as f:
    original_chunk = json.load(f)

markdown = original_chunk['pages'][0]['markdown']
url = original_chunk['pages'][0]['url']
title = original_chunk['pages'][0]['title']

# Split the markdown by sections
# Extract header and wholesalers section
header_match = re.search(r'(.*?## Wholesalers\n\n)', markdown, re.DOTALL)
header = header_match.group(1) if header_match else ""

# Extract wholesalers list (194 companies)
wholesalers_match = re.search(r'## Wholesalers\n\n(.*?)\n\n## Manufacturers', markdown, re.DOTALL)
wholesalers_text = wholesalers_match.group(1) if wholesalers_match else ""

# Extract manufacturers list (1,490 companies)
manufacturers_match = re.search(r'## Manufacturers\n\n(.*?)\n\n### Stay in the loop', markdown, re.DOTALL)
manufacturers_text = manufacturers_match.group(1) if manufacturers_match else ""

# Extract footer
footer_match = re.search(r'(### Stay in the loop.*)', markdown, re.DOTALL)
footer = footer_match.group(1) if footer_match else ""

# Parse company lists (they're in bullet format across multiple columns)
def extract_companies(text):
    # Split by bullets and filter empty
    companies = [line.strip() for line in text.split('\n- ') if line.strip()]
    # Remove the first "- " if present
    if companies and not companies[0].startswith('-'):
        companies[0] = companies[0].lstrip('- ')
    return companies

wholesalers = extract_companies(wholesalers_text)
manufacturers = extract_companies(manufacturers_text)

print(f"Found {len(wholesalers)} wholesalers and {len(manufacturers)} manufacturers")
print(f"Total: {len(wholesalers) + len(manufacturers)} companies")

# Split into 10 chunks
# Chunk 1: Header + all wholesalers (194)
# Chunks 2-10: Manufacturers split into 9 parts (~165 each)

chunks_data = []

# Chunk 1: Wholesalers
chunk1_md = header + "\n".join([f"- {w}" for w in wholesalers])
chunks_data.append({
    "chunk_id": 1,
    "page_count": 1,
    "pages": [{
        "id": 1,
        "url": url,
        "title": f"{title} - Part 1 (Wholesalers)",
        "markdown": chunk1_md,
        "markdown_length": len(chunk1_md)
    }]
})

# Chunks 2-10: Manufacturers split into 9 parts
manufacturers_per_chunk = len(manufacturers) // 9
remainder = len(manufacturers) % 9

start_idx = 0
for i in range(9):
    chunk_size = manufacturers_per_chunk + (1 if i < remainder else 0)
    end_idx = start_idx + chunk_size

    chunk_manufacturers = manufacturers[start_idx:end_idx]

    # Build markdown for this chunk
    chunk_md = header.replace("## Wholesalers", "## Manufacturers")
    chunk_md += "## Manufacturers\n\n"
    chunk_md += "\n".join([f"- {m}" for m in chunk_manufacturers])

    chunks_data.append({
        "chunk_id": i + 2,
        "page_count": 1,
        "pages": [{
            "id": 1,
            "url": url,
            "title": f"{title} - Part {i + 2} (Manufacturers {start_idx + 1}-{end_idx})",
            "markdown": chunk_md,
            "markdown_length": len(chunk_md)
        }]
    })

    start_idx = end_idx

# Write all chunks
for chunk in chunks_data:
    chunk_file = f"l2_merge_and_chunk/outputs/openinfo/erudus/chunks/chunk_{chunk['chunk_id']:04d}.json"
    with open(chunk_file, 'w') as f:
        json.dump(chunk, f, indent=2)
    print(f"Created {chunk_file} ({len(chunk['pages'][0]['markdown'])} chars, ~{len(chunk['pages'][0]['markdown'].split('- ')) - 1} companies)")

print(f"\nSuccessfully created {len(chunks_data)} chunks")
