#!/usr/bin/env python3
"""
L4: Merge Classifications, Clean Data, Export Companies (ROBUST VERSION)
- Validates L3 responses exist
- Handles partial/incomplete data gracefully
- Continues even if some responses are malformed
- Validates disk space before writing
"""

import json
import csv
import re
import os
import sys
import shutil
from pathlib import Path
from datetime import datetime
from collections import defaultdict

def log(msg):
    """Print with flush for real-time logging"""
    print(msg, flush=True)

def check_disk_space(path, required_mb=50):
    """Check if there's enough disk space"""
    stat = shutil.disk_usage(path)
    available_mb = stat.free / (1024 * 1024)
    return (available_mb >= required_mb, int(available_mb))

def normalize_domain(website):
    """Normalize website to clean domain only"""
    if not website or website.strip() == "":
        return ""

    website = website.strip()
    website = re.sub(r'^https?://', '', website)
    website = re.sub(r'^www\.', '', website)

    if '/' in website:
        website = website.split('/')[0]
    if '?' in website:
        website = website.split('?')[0]
    if ':' in website:
        website = website.split(':')[0]

    return website.lower().strip()

def normalize_company_name(name):
    """Normalize company name for deduplication"""
    if not name:
        return ""

    name = re.sub(r'\s+', ' ', name.strip())
    name = name.rstrip('.')

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
    return re.sub(r'\s+', ' ', name.strip())

def parse_llm_response(response_data, response_file_name):
    """
    Parse LLM response and extract companies
    Returns: (success: bool, companies: list, error: str/None)
    """
    try:
        # Parse LLM response - handle both OpenAI and Claude formats
        content_text = None

        # Try OpenAI format
        if 'choices' in response_data:
            content_text = response_data.get('choices', [{}])[0].get('message', {}).get('content', '')
        # Try Claude format
        elif 'content' in response_data:
            content_text = response_data.get('content', [{}])[0].get('text', '')

        if not content_text:
            return (False, [], "No content text found")

        # Strip markdown code blocks
        content_text = content_text.strip()
        if content_text.startswith('```'):
            content_text = re.sub(r'^```(?:json)?\s*\n', '', content_text)
            content_text = re.sub(r'\n```\s*$', '', content_text)
            content_text = content_text.strip()

        # Parse JSON
        result = json.loads(content_text)

        companies = []

        # Handle OpenAI format
        if 'companies_extracted' in result and 'total_companies_counted' in result:
            for company in result.get('companies_extracted', []):
                name = clean_company_name(company.get('name', ''))
                website_raw = company.get('website', '')
                website_normalized = normalize_domain(website_raw)

                if name:
                    companies.append({
                        'name': name,
                        'website_original': website_raw,
                        'domain': website_normalized,
                        'classification_type': 'company_list',
                        'source_file': response_file_name
                    })

        # Handle Claude format
        elif 'classifications' in result:
            for classification in result.get('classifications', []):
                class_type = classification.get('classification', 'other')

                for company in classification.get('companies_extracted', []):
                    name = clean_company_name(company.get('name', ''))
                    website_raw = company.get('website', '')
                    website_normalized = normalize_domain(website_raw)

                    if name:
                        companies.append({
                            'name': name,
                            'website_original': website_raw,
                            'domain': website_normalized,
                            'classification_type': class_type,
                            'source_file': response_file_name
                        })

        return (True, companies, None)

    except json.JSONDecodeError as e:
        return (False, [], f"JSON decode error: {e}")
    except Exception as e:
        return (False, [], f"Parse error: {e}")

def main():
    # Get client, domain and timestamp from environment
    CLIENT = os.getenv("CLIENT", "default")
    DOMAIN = os.getenv("DOMAIN", "default")
    TIMESTAMP = os.getenv("TIMESTAMP", datetime.now().strftime("%Y%m%d_%H%M%S"))

    # Use queue_system directory structure
    SCRIPT_DIR = Path(__file__).parent.parent.parent
    L3_RESPONSES = SCRIPT_DIR / "outputs" / CLIENT / DOMAIN / "llm_responses"
    OUTPUT_DIR = SCRIPT_DIR / "outputs" / CLIENT / DOMAIN
    LOG_DIR = SCRIPT_DIR / "logs" / CLIENT / DOMAIN

    log(f"📤 L4: DEDUPE AND EXPORT")
    log(f"   Client: {CLIENT}")
    log(f"   Domain: {DOMAIN}")
    log(f"   LLM Responses: {L3_RESPONSES}")

    # ============================================================================
    # PHASE 1: Validate inputs
    # ============================================================================
    log("\n[PHASE 1] Validating inputs...")

    if not L3_RESPONSES.exists():
        log(f"❌ LLM responses directory not found: {L3_RESPONSES}")
        log(f"   L3 may have failed")
        sys.exit(1)

    response_files = sorted(L3_RESPONSES.glob("response_chunk_*.json"))

    if not response_files:
        log(f"❌ No response files found in {L3_RESPONSES}")
        log(f"   L3 may have failed")
        sys.exit(1)

    log(f"✅ Found {len(response_files)} response files")

    # Check disk space
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    has_space, available_mb = check_disk_space(OUTPUT_DIR)
    if not has_space:
        log(f"❌ Insufficient disk space: {available_mb}MB available (need 50MB)")
        sys.exit(1)

    log(f"✅ Disk space: {available_mb}MB available")

    # ============================================================================
    # PHASE 2: Parse responses with error handling
    # ============================================================================
    log("\n[PHASE 2] Parsing LLM responses...")

    all_companies = []
    parse_failures = []
    parse_successes = 0

    for i, response_file in enumerate(response_files, 1):
        if i % 500 == 0:
            log(f"  Processed {i}/{len(response_files)} responses...")

        try:
            with open(response_file) as f:
                response_data = json.load(f)

            success, companies, error = parse_llm_response(response_data, response_file.name)

            if success:
                all_companies.extend(companies)
                parse_successes += 1
            else:
                parse_failures.append((response_file.name, error))

        except IOError as e:
            parse_failures.append((response_file.name, f"File read error: {e}"))
        except Exception as e:
            parse_failures.append((response_file.name, f"Unexpected error: {e}"))

    success_rate = (parse_successes / len(response_files) * 100) if response_files else 0

    log(f"\n✅ Parsing complete")
    log(f"   Successful: {parse_successes}/{len(response_files)} ({success_rate:.1f}%)")
    log(f"   Failed: {len(parse_failures)}")
    log(f"   Companies extracted: {len(all_companies)}")

    if parse_failures and len(parse_failures) <= 10:
        log(f"\n⚠️  Parse failures:")
        for filename, error in parse_failures[:10]:
            log(f"     {filename}: {error}")

    if not all_companies:
        log(f"\n❌ No companies extracted")
        sys.exit(1)

    # ============================================================================
    # PHASE 3: Deduplication
    # ============================================================================
    log("\n[PHASE 3] Deduplicating...")

    # Find normalized names with domains
    names_with_domains = set()
    for company in all_companies:
        if company['domain']:
            normalized = normalize_company_name(company['name'])
            names_with_domains.add(normalized)

    # Dedupe by domain, then by name
    by_domain = {}
    by_name_only = {}

    for company in all_companies:
        domain = company['domain'].lower().strip()
        normalized_name = normalize_company_name(company['name'])

        if domain:
            if domain not in by_domain:
                by_domain[domain] = company
        else:
            if normalized_name not in names_with_domains:
                if normalized_name not in by_name_only:
                    by_name_only[normalized_name] = company

    unique_companies = list(by_domain.values()) + list(by_name_only.values())

    log(f"✅ Deduplication complete")
    log(f"   Before: {len(all_companies)}")
    log(f"   With domains: {len(by_domain)}")
    log(f"   Name-only: {len(by_name_only)}")
    log(f"   After: {len(unique_companies)}")
    log(f"   Removed: {len(all_companies) - len(unique_companies)}")

    # ============================================================================
    # PHASE 4: Export results
    # ============================================================================
    log("\n[PHASE 4] Exporting...")

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Save JSON
    json_output = OUTPUT_DIR / f"{DOMAIN}_{TIMESTAMP}.json"
    try:
        with open(json_output, 'w') as f:
            json.dump({
                'metadata': {
                    'domain': DOMAIN,
                    'timestamp': TIMESTAMP,
                    'total_responses': len(response_files),
                    'successful_parses': parse_successes,
                    'companies_found': len(unique_companies)
                },
                'companies': unique_companies
            }, f, indent=2)
        log(f"✅ JSON: {json_output.name}")
    except IOError as e:
        log(f"❌ Failed to write JSON: {e}")
        sys.exit(1)

    # Save CSV
    csv_output = OUTPUT_DIR / f"{DOMAIN}_{TIMESTAMP}.csv"
    try:
        with open(csv_output, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['name', 'domain', 'website_original', 'classification_type', 'source_file'])
            writer.writeheader()
            writer.writerows(unique_companies)
        log(f"✅ CSV: {csv_output.name}")
    except IOError as e:
        log(f"❌ Failed to write CSV: {e}")
        sys.exit(1)

    # Copy CSV to consolidated project folder
    PROJECT_DIR = SCRIPT_DIR / "outputs" / "Food Distributors USA"
    PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    consolidated_csv = PROJECT_DIR / f"{DOMAIN}_{TIMESTAMP}.csv"

    try:
        import shutil
        shutil.copy2(csv_output, consolidated_csv)
        log(f"✅ Consolidated CSV: Food Distributors USA/{consolidated_csv.name}")
    except IOError as e:
        log(f"⚠️  Warning: Could not copy to consolidated folder: {e}")
        # Don't fail the pipeline, just warn

    # ============================================================================
    # PHASE 5: Final statistics
    # ============================================================================
    with_domains = sum(1 for c in unique_companies if c['domain'])
    without_domains = len(unique_companies) - with_domains

    log(f"\n✅ L4 COMPLETE")
    log(f"   Total companies: {len(unique_companies)}")
    log(f"   With domains: {with_domains} ({with_domains/len(unique_companies)*100:.1f}%)")
    log(f"   Without domains: {without_domains}")
    log(f"   Output: {OUTPUT_DIR}")

    return 0

if __name__ == "__main__":
    sys.exit(main())
