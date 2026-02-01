#!/usr/bin/env python3
"""
L3: Claude LLM Classification

Input: L2 scraped pages JSON (from Firecrawl)
Output: L3 classified pages JSON (with structured data)

Process:
1. Read L2 scraped pages
2. For each page:
   - Build classification prompt with full markdown
   - Call Claude API with retry logic
   - Parse JSON response with classification
   - Extract structured data
3. Save L3 output JSON
"""

import os
import json
import time
import requests
from datetime import datetime
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

# Load environment
load_dotenv('../../../.env')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')

if not ANTHROPIC_API_KEY:
    print("❌ ERROR: ANTHROPIC_API_KEY not found in .env")
    exit(1)


def retry_api_call(func, max_retries=10, initial_delay=2):
    """
    Retry an API call with exponential backoff

    Returns: (success: bool, data: dict/None, error: str/None)
    """
    retries = 0
    delay = initial_delay

    while retries < max_retries:
        try:
            resp = func()

            # Check HTTP status
            if resp.status_code == 429:
                print(f"      ⚠️  Rate limited, waiting {delay}s... (attempt {retries+1}/{max_retries})")
                time.sleep(delay)
                retries += 1
                delay = min(delay * 2, 60)
                continue

            if resp.status_code == 200:
                try:
                    data = resp.json()
                    return (True, data, None)
                except json.JSONDecodeError as e:
                    print(f"      ⚠️  Invalid JSON: {e}")
                    if retries < max_retries - 1:
                        time.sleep(delay)
                        retries += 1
                        delay = min(delay * 2, 60)
                        continue
                    return (False, None, f"Invalid JSON: {e}")

            # Other HTTP errors
            print(f"      ⚠️  HTTP {resp.status_code}")
            if retries < max_retries - 1:
                time.sleep(delay)
                retries += 1
                delay = min(delay * 2, 60)
                continue

            return (False, None, f"HTTP {resp.status_code}")

        except requests.exceptions.Timeout:
            print(f"      ⚠️  Timeout")
            if retries < max_retries - 1:
                time.sleep(delay)
                retries += 1
                delay = min(delay * 2, 60)
                continue
            return (False, None, "Timeout after retries")

        except Exception as e:
            print(f"      ❌ Error: {e}")
            if retries < max_retries - 1:
                time.sleep(delay)
                retries += 1
                delay = min(delay * 2, 60)
                continue
            return (False, None, str(e))

    return (False, None, "Max retries exceeded")


def build_classification_prompt(page):
    """Build classification prompt for Claude"""

    url = page.get('url', 'Unknown')
    markdown = page.get('markdown', '')
    links = page.get('links', [])

    # Truncate markdown if too long (keep first 50k chars to stay within context)
    if len(markdown) > 50000:
        markdown = markdown[:50000] + "\n\n[... content truncated ...]"

    # Format links
    links_text = "\n".join(links[:20])  # First 20 links
    if len(links) > 20:
        links_text += f"\n... and {len(links) - 20} more links"

    prompt = f"""TASK: Classify this webpage as a neurology clinic, medical directory, or other.

URL: {url}

SCRAPED CONTENT (MARKDOWN):
{markdown}

LINKS FOUND ON PAGE:
{links_text}

CLASSIFICATION OPTIONS:
1. **neurology_clinic_individual** - Single neurology clinic or practice
   - Has clinic name, location
   - Offers neurology services
   - NOT a directory, NOT insurance site

2. **neurology_clinic_group** - Multi-location neurology group
   - Multiple clinic locations
   - Corporate structure
   - Neurology services across locations

3. **directory** - Clinic directory/listing site
   - Lists multiple unrelated clinics
   - Examples: Yelp, insurance directories, healthgrades

4. **other** - Not a neurology clinic
   - Insurance sites, news articles
   - Social media pages
   - Non-medical businesses

EXTRACTION RULES:
If classification = "neurology_clinic_individual" or "neurology_clinic_group":
  - Extract: clinic name, location(s), phone, website
  - Verify it's a real neurology clinic

If classification = "directory" or "other":
  - No extraction needed

RESPOND IN JSON ONLY (no markdown, no code blocks):
{{
  "classification": "neurology_clinic_individual|neurology_clinic_group|directory|other",
  "confidence": "high|medium|low",
  "reasoning": "Brief explanation (1-2 sentences)",
  "extracted_data": {{
    "clinic_name": "Name of clinic/group or null",
    "locations": ["City1", "City2"] or [],
    "phone": "+1... or null",
    "website": "https://... or null"
  }}
}}"""

    return prompt


def classify_page(page, model="claude-sonnet-4-5-20250929"):
    """
    Classify a single page using Claude

    Returns:
        dict: Classification result or error info
    """

    prompt = build_classification_prompt(page)

    def make_request():
        return requests.post(
            "https://api.anthropic.com/v1/messages",
            json={
                "model": model,
                "max_tokens": 1000,
                "temperature": 0,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            },
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            timeout=60
        )

    # Retry API call
    success, data, error = retry_api_call(make_request, max_retries=10)

    if not success:
        return {
            "url": page.get('url'),
            "classification": "error",
            "error": error
        }

    # Extract Claude response
    try:
        content = data['content'][0]['text']

        # Remove markdown code blocks if present
        content = content.strip()
        if content.startswith('```'):
            # Remove first and last lines (markdown fences)
            lines = content.split('\n')
            content = '\n'.join(lines[1:-1])

        # Parse JSON
        result = json.loads(content)

        # Add URL and usage info
        result['url'] = page.get('url')
        result['tokens_input'] = data.get('usage', {}).get('input_tokens', 0)
        result['tokens_output'] = data.get('usage', {}).get('output_tokens', 0)

        return result

    except Exception as e:
        return {
            "url": page.get('url'),
            "classification": "error",
            "error": f"Failed to parse Claude response: {e}"
        }


def classify_l2_results(l2_file, client='fuse', limit=None):
    """
    Classify all pages from L2 scrape results

    Args:
        l2_file: Path to L2 scraped pages JSON
        client: Client name for folder structure
        limit: Optional limit on number of pages to classify (for testing)

    Returns:
        dict: Complete L3 output with metadata and classified pages
    """

    print("=" * 70)
    print("L3: CLAUDE LLM CLASSIFICATION")
    print("=" * 70)
    print(f"Input: {l2_file}")
    print(f"Client: {client}")
    print(f"Model: claude-sonnet-4-5-20250929")
    print()

    # Read L2 results
    with open(l2_file, 'r', encoding='utf-8') as f:
        l2_data = json.load(f)

    # Extract pages
    pages = l2_data['pages']
    total_pages = len(pages)

    # Filter to only successful scrapes
    pages = [p for p in pages if p.get('success', False)]
    print(f"Total pages: {total_pages}")
    print(f"Successfully scraped: {len(pages)}")
    print()

    if limit:
        pages = pages[:limit]
        print(f"⚠️  Limiting to first {limit} pages (testing mode)")

    print(f"Concurrency: 30 threads")
    print()

    # Classify with concurrent requests (30 threads)
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

    # Thread-safe counter
    lock = Lock()

    def classify_with_index(page_tuple):
        """Classify page and return with original index"""
        idx, page = page_tuple
        result = classify_page(page)
        return (idx, result)

    print("Starting concurrent classification...")
    print()

    # Use ThreadPoolExecutor with 30 workers (safe for Claude API limits)
    with ThreadPoolExecutor(max_workers=30) as executor:
        # Submit all tasks
        future_to_page = {
            executor.submit(classify_with_index, (i, page)): (i, page)
            for i, page in enumerate(pages)
        }

        # Collect results as they complete
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

                    print(f"[{completed_count}/{len(pages)}] ✅ {url}... → {classification} ({confidence}) [{tokens_in} in, {tokens_out} out]")

                    classified_pages.append((result_idx, result))

            except Exception as e:
                with lock:
                    completed_count += 1
                    classification_counts["error"] += 1
                    print(f"[{completed_count}/{len(pages)}] ❌ {url}... (Exception: {e})")
                    classified_pages.append((idx, {
                        "url": page.get('url'),
                        "classification": "error",
                        "error": str(e)
                    }))

    # Sort by original index to maintain order
    classified_pages.sort(key=lambda x: x[0])
    classified_pages = [page for idx, page in classified_pages]

    total_time = (datetime.now() - start_time).total_seconds()

    print()
    print("=" * 70)
    print("✅ CLASSIFICATION COMPLETE")
    print("=" * 70)
    print(f"Total pages: {len(pages)}")
    print()
    print("Classification Breakdown:")
    for cls, count in classification_counts.items():
        pct = (count / len(pages) * 100) if pages else 0
        print(f"  {cls:30s}: {count:3d} ({pct:5.1f}%)")
    print()
    print(f"Time: {total_time:.1f}s ({total_time/60:.1f} minutes)")
    print(f"Avg: {total_time/len(pages):.2f}s per page")
    print()

    # Calculate cost
    # Claude 3.5 Sonnet: $3/MTok input, $15/MTok output
    cost_input = (total_input_tokens / 1_000_000) * 3
    cost_output = (total_output_tokens / 1_000_000) * 15
    cost_total = cost_input + cost_output

    print("Token Usage:")
    print(f"  Input tokens:  {total_input_tokens:,}")
    print(f"  Output tokens: {total_output_tokens:,}")
    print(f"  Total tokens:  {total_input_tokens + total_output_tokens:,}")
    print()
    print(f"💰 Estimated cost: ${cost_total:.3f}")
    print(f"   (Input: ${cost_input:.3f}, Output: ${cost_output:.3f})")
    print()

    # Prepare output
    output = {
        'metadata': {
            'layer': 'l3_classify',
            'source_file': os.path.basename(l2_file),
            'source_query': l2_data['metadata'].get('source_query', ''),
            'source_location': l2_data['metadata'].get('source_location', ''),
            'total_pages': len(pages),
            'classification_counts': classification_counts,
            'timestamp': datetime.now().isoformat(),
            'classify_time_seconds': total_time,
            'tokens_input': total_input_tokens,
            'tokens_output': total_output_tokens,
            'cost_estimate_usd': cost_total
        },
        'pages': classified_pages
    }

    return output


def save_results(output, filename, client='fuse'):
    """Save results to client folder"""

    # Save to round outputs
    output_dir = '../outputs'
    os.makedirs(output_dir, exist_ok=True)
    round_path = os.path.join(output_dir, filename)

    with open(round_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"💾 Saved to: {round_path}")

    # Also save to client folder
    client_dir = f'../../../search_system/client_outputs/{client}/outputs/l3_classify'
    os.makedirs(client_dir, exist_ok=True)
    client_path = os.path.join(client_dir, filename)

    with open(client_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"💾 Saved to client folder: {client_path}")
    print()


def main():
    import sys

    if len(sys.argv) < 2:
        print("Usage: python3 classify_pages.py <l2_file> [limit]")
        print()
        print("Examples:")
        print("  python3 classify_pages.py ../outputs/l2_scraped_neurology_la_*.json")
        print("  python3 classify_pages.py ../outputs/l2_scraped_neurology_la_*.json 10")
        exit(1)

    l2_file = sys.argv[1]
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else None

    if not os.path.exists(l2_file):
        print(f"❌ ERROR: File not found: {l2_file}")
        exit(1)

    # Classify all pages
    output = classify_l2_results(l2_file, client='fuse', limit=limit)

    # Generate filename
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # Extract city name from L2 filename
    l2_basename = os.path.basename(l2_file)
    parts = l2_basename.replace('l2_scraped_', '').replace('.json', '').split('_')
    # Take everything except last 3 parts (date, time)
    city_name = '_'.join(parts[:-2]) if len(parts) > 2 else 'unknown'

    filename = f'l3_classified_{city_name}_{timestamp}.json'

    save_results(output, filename, client='fuse')

    print("=" * 70)
    print("Pipeline Complete! 🎉")
    print("=" * 70)
    print()
    print("Results Summary:")
    print(f"  L1 Search:   {output['metadata']['source_query']}")
    print(f"  L2 Scraped:  {output['metadata']['total_pages']} pages")
    print(f"  L3 Classified: {output['metadata']['total_pages']} pages")
    print()
    print("Classification Breakdown:")
    for cls, count in output['metadata']['classification_counts'].items():
        print(f"  {cls:30s}: {count}")
    print()


if __name__ == '__main__':
    main()
