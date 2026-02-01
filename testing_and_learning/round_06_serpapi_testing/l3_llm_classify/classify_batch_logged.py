#!/usr/bin/env python3
"""
Batch L3 Classification Script with PROPER LOGGING
COMMANDMENTS #7 Compliant: Logs to /logs/l3_llm_classify/
"""

import os
import json
import time
import sys
from datetime import datetime
import requests
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import glob

load_dotenv('../../../.env')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')

if not ANTHROPIC_API_KEY:
    print("❌ ERROR: ANTHROPIC_API_KEY not found in .env")
    exit(1)


# ═══════════════════════════════════════════════════════════════════
# LOGGING UTILITY (COMMANDMENTS #7)
# ═══════════════════════════════════════════════════════════════════

class Logger:
    def __init__(self, log_path):
        self.log_path = log_path
        self.lock = Lock()

        # Create log directory
        os.makedirs(os.path.dirname(log_path), exist_ok=True)

        # Initialize log file with header
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write("═" * 70 + "\n")
            f.write("SCRIPT: classify_batch_logged.py\n")
            f.write("ROUND: 06 - Serper.dev Production Pipeline\n")
            f.write("LAYER: L3 - Claude Concurrent Classifier (30 threads)\n")
            f.write(f"STARTED: {datetime.now().isoformat()}\n")
            f.write("═" * 70 + "\n\n")
            f.flush()

    def log(self, message, to_console=True):
        """Write to both log file and console"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_line = f"[{timestamp}] {message}\n"

        with self.lock:
            # Write to file (unbuffered)
            with open(self.log_path, 'a', encoding='utf-8') as f:
                f.write(log_line)
                f.flush()
                os.fsync(f.fileno())  # Force write to disk

            # Write to console
            if to_console:
                print(message, flush=True)

    def section(self, title):
        """Log a section header"""
        self.log("=" * 70)
        self.log(title)
        self.log("=" * 70)

    def summary(self, title, metrics):
        """Log final summary with metrics"""
        self.log("")
        self.log("=" * 70)
        self.log(title)
        self.log("=" * 70)
        for key, value in metrics.items():
            self.log(f"   {key}: {value}")
        self.log("=" * 70)


# Global logger instance
logger = None


def build_classification_prompt(page):
    """Build Claude prompt for neurology clinic classification"""

    url = page.get('url', 'Unknown')
    markdown = page.get('markdown', '')[:50000]  # Limit to 50k chars
    links = page.get('links', [])[:100]  # Limit to 100 links

    links_text = '\n'.join(links) if links else '(No links extracted)'

    prompt = f"""TASK: Classify this webpage as a neurology clinic, medical directory, or other.

<critical_instruction>
CRITICAL: Respond with PURE JSON ONLY.
- NO markdown code blocks (no ```json)
- NO explanatory text before or after
- ONLY the JSON object as specified below
</critical_instruction>

URL: {url}

SCRAPED CONTENT (MARKDOWN):
{markdown}

LINKS FOUND ON PAGE:
{links_text}

CLASSIFICATION OPTIONS:
1. **neurology_clinic_individual** - Single neurology clinic or practice
2. **neurology_clinic_group** - Multi-location neurology group
3. **directory** - Clinic directory/listing site
4. **other** - Not a neurology clinic

EXTRACTION RULES:
- If "neurology_clinic_individual" or "neurology_clinic_group": Extract clinic name, locations, phone, website
- If "directory" or "other": Set all extracted_data fields to null/empty
- Look for clinic names (e.g., "NYC Neurology Associates", "Brain Health Center")
- Look for locations (cities mentioned in address or "Locations:" section)
- Look for phone numbers (format: +1-XXX-XXX-XXXX)
- Look for website URLs (company's own domain, not the directory site)

<critical_instruction>
RESPOND WITH THIS EXACT JSON STRUCTURE (pure JSON, no markdown):
{{
  "classification": "neurology_clinic_individual|neurology_clinic_group|directory|other",
  "confidence": "high|medium|low",
  "reasoning": "Brief explanation (1-2 sentences)",
  "extracted_data": {{
    "clinic_name": "Name of clinic/group or null",
    "locations": ["City1", "City2"] or [],
    "phone": "+1... or null",
    "website": "https://... or null"
  }},
  "is_hospital_or_dept": {{
    "answer": "yes|no",
    "confidence": "high|medium|low",
    "reasoning": "Is this a hospital or a neurology department within a hospital?"
  }},
  "university_affiliated": {{
    "answer": "yes|no",
    "confidence": "high|medium|low",
    "reasoning": "Is this clinic/hospital affiliated with a university? (e.g., NYU, UCLA, Harvard)"
  }}
}}
</critical_instruction>"""

    return prompt


def classify_page(page, model="claude-sonnet-4-5-20250929"):
    """Classify a single page using Claude"""

    prompt = build_classification_prompt(page)

    def make_request():
        return requests.post(
            "https://api.anthropic.com/v1/messages",
            json={
                "model": model,
                "max_tokens": 1000,
                "temperature": 0,
                "messages": [{"role": "user", "content": prompt}]
            },
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            timeout=60
        )

    # Retry logic
    max_retries = 10
    retry_delay = 2

    for attempt in range(max_retries):
        try:
            response = make_request()

            if response.status_code == 429:
                logger.log(f"      ⚠️  Rate limited on {page.get('url', '')[:50]}... (attempt {attempt+1})")
                time.sleep(retry_delay * (attempt + 1))
                continue

            if response.status_code == 200:
                data = response.json()
                content = data['content'][0]['text']

                # Parse JSON response (strip markdown code blocks if present)
                try:
                    # Remove markdown code blocks (```json ... ```)
                    cleaned_content = content.strip()
                    if cleaned_content.startswith('```'):
                        # Find the first newline after opening ```
                        first_newline = cleaned_content.find('\n')
                        if first_newline != -1:
                            cleaned_content = cleaned_content[first_newline+1:]
                        # Remove closing ```
                        if cleaned_content.endswith('```'):
                            cleaned_content = cleaned_content[:-3]
                        cleaned_content = cleaned_content.strip()

                    result = json.loads(cleaned_content)

                    return {
                        "url": page.get('url'),
                        "classification": result.get('classification', 'error'),
                        "confidence": result.get('confidence', 'unknown'),
                        "reasoning": result.get('reasoning', ''),
                        "extracted_data": result.get('extracted_data', {}),
                        "is_hospital_or_dept": result.get('is_hospital_or_dept', {}),
                        "university_affiliated": result.get('university_affiliated', {}),
                        "tokens_input": data.get('usage', {}).get('input_tokens', 0),
                        "tokens_output": data.get('usage', {}).get('output_tokens', 0)
                    }
                except json.JSONDecodeError as e:
                    logger.log(f"      ⚠️  JSON parse error on {page.get('url', '')[:50]}... ({str(e)[:50]})")
                    return {
                        "url": page.get('url'),
                        "classification": "error",
                        "error": f"JSON parse error: {str(e)[:100]}"
                    }

            # Other HTTP errors
            if attempt < max_retries - 1:
                logger.log(f"      ⚠️  HTTP {response.status_code} on {page.get('url', '')[:50]}...")
                time.sleep(retry_delay)
                continue

            return {
                "url": page.get('url'),
                "classification": "error",
                "error": f"HTTP {response.status_code}"
            }

        except Exception as e:
            if attempt < max_retries - 1:
                logger.log(f"      ⚠️  Exception on {page.get('url', '')[:50]}...: {e}")
                time.sleep(retry_delay)
                continue

            return {
                "url": page.get('url'),
                "classification": "error",
                "error": str(e)
            }

    return {
        "url": page.get('url'),
        "classification": "error",
        "error": "Max retries exceeded"
    }


def classify_concurrent(pages, max_workers=30):
    """Classify pages concurrently"""

    classified_pages = []
    classification_counts = {
        "neurology_clinic_individual": 0,
        "neurology_clinic_group": 0,
        "directory": 0,
        "other": 0,
        "error": 0
    }
    total_input_tokens = 0
    total_output_tokens = 0
    completed_count = 0
    start_time = datetime.now()

    lock = Lock()

    def classify_with_index(page_tuple):
        idx, page = page_tuple
        result = classify_page(page)
        return (idx, result)

    logger.log(f"Starting concurrent classification with {max_workers} threads...")
    logger.log("")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_page = {
            executor.submit(classify_with_index, (i, page)): (i, page)
            for i, page in enumerate(pages)
        }

        for future in as_completed(future_to_page):
            idx, page = future_to_page[future]
            url = page.get('url', 'Unknown')[:50]

            try:
                result_idx, result = future.result()

                with lock:
                    completed_count += 1

                    # Update counts
                    classification = result.get('classification', 'error')
                    classification_counts[classification] = classification_counts.get(classification, 0) + 1

                    # Track tokens
                    total_input_tokens += result.get('tokens_input', 0)
                    total_output_tokens += result.get('tokens_output', 0)

                    # Show result
                    confidence = result.get('confidence', 'N/A')
                    tokens_in = result.get('tokens_input', 0)
                    tokens_out = result.get('tokens_output', 0)

                    logger.log(f"[{completed_count}/{len(pages)}] ✅ {url}... → {classification} ({confidence}) [{tokens_in} in, {tokens_out} out]")

                    classified_pages.append((result_idx, result))

            except Exception as e:
                with lock:
                    completed_count += 1
                    classification_counts["error"] += 1
                    logger.log(f"[{completed_count}/{len(pages)}] ❌ {url}... (Exception: {e})")
                    classified_pages.append((idx, {
                        "url": page.get('url'),
                        "classification": "error",
                        "error": str(e)
                    }))

    # Sort by original index
    classified_pages.sort(key=lambda x: x[0])
    classified_pages = [page for idx, page in classified_pages]

    total_time = (datetime.now() - start_time).total_seconds()

    return classified_pages, classification_counts, total_input_tokens, total_output_tokens, total_time


def process_l2_file(l2_file_path):
    """Process a single L2 output file"""

    logger.section(f"Processing: {os.path.basename(l2_file_path)}")

    with open(l2_file_path, 'r', encoding='utf-8') as f:
        l2_data = json.load(f)

    pages = [p for p in l2_data.get('pages', []) if p.get('success')]
    query = l2_data.get('metadata', {}).get('query', 'Unknown')

    logger.log(f"Query: {query}")
    logger.log(f"Pages to classify: {len(pages)}")
    logger.log("")

    classified_pages, counts, input_tokens, output_tokens, total_time = classify_concurrent(pages, max_workers=30)

    logger.log("")
    logger.summary("✅ CLASSIFICATION COMPLETE", {
        "Total pages": len(pages),
        "Individual clinics": f"{counts.get('neurology_clinic_individual', 0)} ({100*counts.get('neurology_clinic_individual', 0)/len(pages):.1f}%)",
        "Clinic groups": f"{counts.get('neurology_clinic_group', 0)} ({100*counts.get('neurology_clinic_group', 0)/len(pages):.1f}%)",
        "Directories": f"{counts.get('directory', 0)} ({100*counts.get('directory', 0)/len(pages):.1f}%)",
        "Other": f"{counts.get('other', 0)} ({100*counts.get('other', 0)/len(pages):.1f}%)",
        "Errors": f"{counts.get('error', 0)} ({100*counts.get('error', 0)/len(pages):.1f}%)",
        "Time": f"{total_time:.1f}s ({total_time/60:.1f} minutes)",
        "Avg per page": f"{total_time/len(pages):.2f}s",
        "Input tokens": f"{input_tokens:,}",
        "Output tokens": f"{output_tokens:,}",
        "Cost": f"${(input_tokens/1000000*3 + output_tokens/1000000*15):.3f}"
    })
    logger.log("")

    # Save results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    basename = os.path.basename(l2_file_path).replace('l2_scraped_', 'l3_classified_')
    basename = basename.replace('.json', f'_{timestamp}.json')

    output_data = {
        'metadata': {
            'source_file': l2_file_path,
            'query': query,
            'timestamp': datetime.now().isoformat(),
            'total_pages': len(pages),
            'classification_counts': counts,
            'classification_time_seconds': total_time,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'cost_usd': input_tokens/1000000*3 + output_tokens/1000000*15
        },
        'pages': classified_pages
    }

    # Save to outputs (layer-specific outputs folder)
    output_dir = 'outputs'
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, basename)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    logger.log(f"💾 Saved to: {output_path}")

    # Save to client folder
    client_dir = '../../../search_system/client_outputs/fuse/outputs/l3_classify'
    os.makedirs(client_dir, exist_ok=True)
    client_path = os.path.join(client_dir, basename)

    with open(client_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    logger.log(f"💾 Saved to client folder: {client_path}")
    logger.log("")

    return {
        'file': basename,
        'query': query,
        'pages': len(pages),
        'counts': counts,
        'time': total_time,
        'cost': output_data['metadata']['cost_usd'],
        'output_path': output_path
    }


def main():
    global logger

    # Initialize logger (COMMANDMENTS #7)
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    log_path = f'../logs/l3_llm_classify/classify_batch_{timestamp}.log'
    logger = Logger(log_path)

    logger.section("ROUND 06: BATCH L3 CLASSIFICATION")
    logger.log("Client: Fuse")
    logger.log("API: Claude Sonnet 4.5 (30 concurrent threads)")
    logger.log(f"Log file: {log_path}")
    logger.log("")

    # Find all L2 output files from today's batch
    l2_pattern = '../l2_firecrawl_scrape/outputs/l2_scraped_neurology_*.json'
    l2_files = sorted(glob.glob(l2_pattern))

    if not l2_files:
        logger.log("❌ No L2 files found matching pattern")
        return

    logger.log(f"📊 Found {len(l2_files)} L2 files to process:")
    for f in l2_files:
        logger.log(f"   - {os.path.basename(f)}")
    logger.log("")

    batch_start = datetime.now()
    results_summary = []

    for i, l2_file in enumerate(l2_files, 1):
        logger.log("")
        logger.section(f"FILE {i}/{len(l2_files)}")
        logger.log("")

        result = process_l2_file(l2_file)
        results_summary.append(result)

    batch_elapsed = (datetime.now() - batch_start).total_seconds()

    # Final Summary
    total_pages = sum(r['pages'] for r in results_summary)
    total_cost = sum(r['cost'] for r in results_summary)

    # Aggregate counts
    aggregate_counts = {
        "neurology_clinic_individual": 0,
        "neurology_clinic_group": 0,
        "directory": 0,
        "other": 0,
        "error": 0
    }
    for r in results_summary:
        for k, v in r['counts'].items():
            aggregate_counts[k] = aggregate_counts.get(k, 0) + v

    logger.log("")
    logger.summary("🎉 BATCH L3 CLASSIFICATION COMPLETE!", {
        "Files processed": len(results_summary),
        "Total pages": f"{total_pages:,}",
        "Individual clinics": f"{aggregate_counts['neurology_clinic_individual']} ({100*aggregate_counts['neurology_clinic_individual']/total_pages:.1f}%)",
        "Clinic groups": f"{aggregate_counts['neurology_clinic_group']} ({100*aggregate_counts['neurology_clinic_group']/total_pages:.1f}%)",
        "Directories": f"{aggregate_counts['directory']} ({100*aggregate_counts['directory']/total_pages:.1f}%)",
        "Other": f"{aggregate_counts['other']} ({100*aggregate_counts['other']/total_pages:.1f}%)",
        "Errors": f"{aggregate_counts['error']} ({100*aggregate_counts['error']/total_pages:.1f}%)",
        "Total time": f"{batch_elapsed:.1f}s ({batch_elapsed/60:.1f} minutes)",
        "Avg per page": f"{batch_elapsed/total_pages:.2f}s",
        "Total cost": f"${total_cost:.2f}"
    })

    logger.log("")
    logger.log("Per-Query Results:")
    for r in results_summary:
        indiv = r['counts'].get('neurology_clinic_individual', 0)
        group = r['counts'].get('neurology_clinic_group', 0)
        logger.log(f"   {r['query'][:40]}: {indiv} indiv + {group} groups = {indiv+group} clinics in {r['time']/60:.1f}min")

    logger.log("")
    logger.log("=" * 70)
    logger.log(f"COMPLETED: {datetime.now().isoformat()}")
    logger.log(f"DURATION: {batch_elapsed:.1f} seconds")
    logger.log(f"LOG FILE: {log_path}")
    logger.log("=" * 70)


if __name__ == '__main__':
    main()
