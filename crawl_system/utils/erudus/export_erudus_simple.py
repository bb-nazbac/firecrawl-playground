#!/usr/bin/env python3
"""
Simple export script for Erudus companies
"""
import json
import csv
from pathlib import Path

# Paths
L3_RESPONSES = Path("l3_llm_classify_extract/outputs/openinfo/erudus/llm_responses")
OUTPUT_DIR = Path("l4_dedupe_and_export/outputs/openinfo/erudus")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Find all response files
response_files = sorted(L3_RESPONSES.glob("response_chunk_*.json"))
print(f"Found {len(response_files)} response files")

# Collect all companies
all_companies = []

for response_file in response_files:
    with open(response_file) as f:
        response_data = json.load(f)

    # Get content text
    content_text = response_data.get('content', [{}])[0].get('text', '')

    # Strip markdown code blocks
    import re
    content_text = content_text.strip()
    if content_text.startswith('```'):
        content_text = re.sub(r'^```(?:json)?\s*\n', '', content_text)
        content_text = re.sub(r'\n```\s*$', '', content_text)
        content_text = content_text.strip()

    # Parse JSON
    result = json.loads(content_text)

    # Extract companies
    for classification in result.get('classifications', []):
        companies = classification.get('companies_extracted', [])
        print(f"{response_file.name}: {len(companies)} companies")

        for company in companies:
            all_companies.append({
                'name': company.get('name', ''),
                'website': company.get('website', ''),
                'source_file': response_file.name
            })

print(f"\nTotal companies: {len(all_companies)}")

# Save CSV
csv_output = OUTPUT_DIR / "erudus_companies.csv"
with open(csv_output, 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=['name', 'website', 'source_file'])
    writer.writeheader()
    writer.writerows(all_companies)

print(f"✅ CSV saved: {csv_output}")
print(f"   Total companies exported: {len(all_companies)}")
