#!/usr/bin/env python3
"""
L4: Merge Classifications, Clean Data, Export Companies
Input: 2,275 LLM response files from L3
Output: Clean CSV with all companies
"""

import json
import csv
import re
import os
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Get client, domain and timestamp from environment
CLIENT = os.getenv("CLIENT", "default")
DOMAIN = os.getenv("DOMAIN", "default")
TIMESTAMP = os.getenv("TIMESTAMP", datetime.now().strftime("%Y%m%d_%H%M%S"))

# Use relative paths with client/domain-specific folders
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
L3_RESPONSES = PROJECT_ROOT / "l3_llm_classify_extract" / "outputs" / CLIENT / DOMAIN / "llm_responses"
OUTPUT_DIR = SCRIPT_DIR / "outputs" / CLIENT / DOMAIN
LOG_DIR = SCRIPT_DIR / "logs" / CLIENT / DOMAIN

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = LOG_DIR / f"{DOMAIN}_{TIMESTAMP}.log"

def log(msg):
    with open(LOG_FILE, 'a') as f:
        f.write(f"[{datetime.now()}] {msg}\n")

def normalize_domain(website):
    """
    Normalize website to clean domain only
    Examples:
      http://www.copeland.com → copeland.com
      https://copeland.com/us → copeland.com
      www.example.com/path → example.com
    """
    if not website or website.strip() == "":
        return ""
    
    website = website.strip()
    
    # Remove protocol
    website = re.sub(r'^https?://', '', website)
    
    # Remove www.
    website = re.sub(r'^www\.', '', website)
    
    # Remove path (everything after first /)
    if '/' in website:
        website = website.split('/')[0]
    
    # Remove query params
    if '?' in website:
        website = website.split('?')[0]
    
    # Remove port
    if ':' in website:
        website = website.split(':')[0]
    
    return website.lower().strip()

def normalize_company_name(name):
    """Normalize company name for deduplication"""
    if not name:
        return ""
    
    # Remove extra whitespace
    name = re.sub(r'\s+', ' ', name.strip())
    
    # Remove trailing periods
    name = name.rstrip('.')
    
    # Normalize common suffixes for comparison
    # (but keep them in the actual name)
    normalized = name.lower()
    normalized = normalized.replace(' inc.', ' inc')
    normalized = normalized.replace(' llc.', ' llc')
    normalized = normalized.replace(' corp.', ' corp')
    normalized = normalized.replace(' co.', ' co')
    normalized = normalized.replace(' ltd.', ' ltd')
    
    return normalized.strip()

def clean_company_name(name):
    """Clean company name for display"""
    if not name:
        return ""
    
    # Remove extra whitespace
    name = re.sub(r'\s+', ' ', name.strip())
    
    return name

try:
    log("="*80)
    log("L4: MERGE, CLEAN & EXPORT")
    log("="*80)
    
    # Find all response files
    response_files = sorted(L3_RESPONSES.glob("response_chunk_*.json"))
    log(f"Found {len(response_files)} response files")
    
    # Collect all companies
    log("Parsing all responses...")
    all_companies = []
    stats = {
        'total_pages': 0,
        'company_individual': 0,
        'company_list': 0,
        'navigation': 0,
        'other': 0,
        'companies_extracted': 0
    }
    
    for i, response_file in enumerate(response_files, 1):
        if i % 500 == 0:
            log(f"  Processing response {i}/{len(response_files)}...")
        
        try:
            with open(response_file) as f:
                response_data = json.load(f)

            # Parse LLM response - handle both OpenAI and Claude formats
            content_text = None

            # Try OpenAI format first (GPT-4o with JSON Schema)
            if 'choices' in response_data:
                content_text = response_data.get('choices', [{}])[0].get('message', {}).get('content', '')
            # Fallback to Claude format
            elif 'content' in response_data:
                content_text = response_data.get('content', [{}])[0].get('text', '')

            if not content_text:
                continue

            # Strip markdown code blocks if present (Claude Sonnet 4.5 wraps JSON in ```json)
            import re
            content_text = content_text.strip()
            if content_text.startswith('```'):
                # Remove markdown code block delimiters
                content_text = re.sub(r'^```(?:json)?\s*\n', '', content_text)
                content_text = re.sub(r'\n```\s*$', '', content_text)
                content_text = content_text.strip()

            # Parse JSON from text
            result = json.loads(content_text)

            # Handle OpenAI format (new exhaustive extraction)
            if 'companies_extracted' in result and 'total_companies_counted' in result:
                companies = result.get('companies_extracted', [])
                total_counted = result.get('total_companies_counted', 0)
                extraction_complete = result.get('extraction_complete', False)

                # Log completeness info
                if total_counted != len(companies):
                    log(f"  ⚠️  {response_file.name}: Counted {total_counted} but extracted {len(companies)}")

                stats['total_pages'] += 1
                stats['company_list'] += 1  # OpenAI responses are list format

                # Extract companies
                for company in companies:
                    name = clean_company_name(company.get('name', ''))
                    website_raw = company.get('website', '')
                    website_normalized = normalize_domain(website_raw)

                    if name:  # Only add if has name
                        all_companies.append({
                            'name': name,
                            'website_original': website_raw,
                            'domain': website_normalized,
                            'classification_type': 'company_list',
                            'source_file': response_file.name
                        })
                        stats['companies_extracted'] += 1

            # Handle Claude format (legacy)
            elif 'classifications' in result:
                for classification in result.get('classifications', []):
                    page_id = classification.get('id')
                    class_type = classification.get('classification', 'other')
                    companies = classification.get('companies_extracted', [])
                    url = classification.get('url', '')  # May not be in response

                    # Update stats
                    stats['total_pages'] += 1
                    stats[class_type] = stats.get(class_type, 0) + 1

                    # Extract companies
                    for company in companies:
                        name = clean_company_name(company.get('name', ''))
                        website_raw = company.get('website', '')
                        website_normalized = normalize_domain(website_raw)

                        if name:  # Only add if has name
                            all_companies.append({
                                'name': name,
                                'website_original': website_raw,
                                'domain': website_normalized,
                                'classification_type': class_type,
                                'source_file': response_file.name
                            })
                            stats['companies_extracted'] += 1

        except Exception as e:
            log(f"  Error in {response_file.name}: {e}")
    
    log(f"\nParsing complete!")
    log(f"  Total pages classified: {stats['total_pages']}")
    log(f"  Company individuals: {stats.get('company_individual', 0)}")
    log(f"  Company lists: {stats.get('company_list', 0)}")
    log(f"  Navigation pages: {stats.get('navigation', 0)}")
    log(f"  Other: {stats.get('other', 0)}")
    log(f"  Companies extracted: {stats['companies_extracted']}")
    
    # Deduplicate: Prefer domain entries, remove name-only duplicates
    log("\nDeduplicating companies...")
    log("  Strategy: Keep domain entries, discard name-only duplicates")
    
    # Step 1: Find all company names that have domains (using normalized names)
    names_with_domains = set()
    for company in all_companies:
        if company['domain']:
            normalized = normalize_company_name(company['name'])
            names_with_domains.add(normalized)
    
    log(f"  Unique normalized names with domains: {len(names_with_domains)}")
    
    # Step 2: Dedupe by domain first, then by name (excluding names that have domains)
    by_domain = {}
    by_name_only = {}
    
    for company in all_companies:
        domain = company['domain'].lower().strip()
        normalized_name = normalize_company_name(company['name'])
        
        if domain:
            # Has domain - dedupe by domain
            if domain not in by_domain:
                by_domain[domain] = company
        else:
            # No domain - only keep if this normalized name NEVER has a domain
            if normalized_name not in names_with_domains:
                if normalized_name not in by_name_only:
                    by_name_only[normalized_name] = company
    
    # Combine
    unique_companies = list(by_domain.values()) + list(by_name_only.values())
    
    log(f"  Before dedup: {len(all_companies)}")
    log(f"  With domains (unique by domain): {len(by_domain)}")
    log(f"  Name-only (never have domain): {len(by_name_only)}")
    log(f"  After dedup total: {len(unique_companies)}")
    log(f"  Duplicates removed: {len(all_companies) - len(unique_companies)}")
    
    # Save JSON
    log("\nSaving JSON output...")
    json_output = OUTPUT_DIR / f"{DOMAIN}_{TIMESTAMP}.json"
    with open(json_output, 'w') as f:
        json.dump({
            'metadata': {
                'domain': DOMAIN,
                'timestamp': TIMESTAMP,
                'total_pages_classified': stats['total_pages'],
                'companies_found': len(unique_companies),
                'stats': stats
            },
            'companies': unique_companies
        }, f, indent=2)

    log(f"  ✅ JSON saved: {json_output.name}")

    # Save CSV
    log("\nSaving CSV output...")
    csv_output = OUTPUT_DIR / f"{DOMAIN}_{TIMESTAMP}.csv"
    with open(csv_output, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['name', 'domain', 'website_original', 'classification_type', 'source_file'])
        writer.writeheader()
        writer.writerows(unique_companies)
    
    log(f"  ✅ CSV saved: {csv_output.name}")
    
    # Summary
    log("\n" + "="*80)
    log("L4 COMPLETE!")
    log("="*80)
    log(f"Total companies exported: {len(unique_companies)}")
    log(f"Output files:")
    log(f"  - {json_output.name}")
    log(f"  - {csv_output.name}")
    
    # Final stats
    with_domains = sum(1 for c in unique_companies if c['domain'])
    log(f"\nFinal Statistics:")
    log(f"  Companies with domains: {with_domains} ({with_domains/len(unique_companies)*100:.1f}%)")
    log(f"  Companies without domains: {len(unique_companies) - with_domains}")
    
except Exception as e:
    log(f"ERROR: {e}")
    import traceback
    log(traceback.format_exc())

