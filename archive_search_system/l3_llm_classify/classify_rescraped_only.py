#!/usr/bin/env python3
"""
L3 Classification for Re-scraped Cities Only
Processes only the 33 cities that were re-scraped after L2 failures
"""

import json
import os
import glob
import argparse
from datetime import datetime
from threading import Lock
from concurrent.futures import ThreadPoolExecutor, as_completed
import anthropic
from dotenv import load_dotenv

# Load environment variables
load_dotenv('../../../.env')


class Logger:
    """Thread-safe logger with unbuffered writes"""
    def __init__(self, log_path):
        self.log_path = log_path
        self.lock = Lock()
        os.makedirs(os.path.dirname(log_path), exist_ok=True)

        with open(log_path, 'w', encoding='utf-8') as f:
            f.write("=" * 70 + "\n")
            f.write("SCRIPT: classify_rescraped_only.py\n")
            f.write(f"STARTED: {datetime.now().isoformat()}\n")
            f.write("=" * 70 + "\n\n")
            f.flush()

    def log(self, message, to_console=True):
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_line = f"[{timestamp}] {message}\n"

        with self.lock:
            with open(self.log_path, 'a', encoding='utf-8') as f:
                f.write(log_line)
                f.flush()
                os.fsync(f.fileno())

            if to_console:
                print(message, flush=True)


class SpecLoader:
    """Loads and validates client spec files"""

    @staticmethod
    def load_spec(client, spec_name):
        """Load spec file for given client"""
        spec_path = f'specs/{client}/{spec_name}.json'

        if not os.path.exists(spec_path):
            raise FileNotFoundError(f"Spec not found: {spec_path}")

        with open(spec_path, 'r', encoding='utf-8') as f:
            spec = json.load(f)

        return spec

    @staticmethod
    def build_prompt(spec, markdown, links):
        """Build classification prompt from spec"""

        # Build categories list
        categories = ', '.join([cat['id'] for cat in spec['classification_task']['categories']])

        # Build extraction fields description
        extraction_desc = []
        for field, rules in spec['extraction_rules'].items():
            extraction_desc.append(f"- {field}: {rules['instructions']}")

        # Build additional questions
        questions_desc = []
        for q in spec['additional_questions']:
            questions_desc.append(f"- {q['question']}")

        # Build complete prompt
        prompt = f"""TASK: Classify this webpage and extract relevant information about neurology clinics.

<critical_instruction>
CRITICAL: Respond with PURE JSON ONLY.
- NO markdown code blocks (no ```json)
- NO explanatory text before or after
- ONLY the JSON object as specified below
</critical_instruction>

CLASSIFICATION:
Classify the webpage as one of: {categories}

CATEGORIES:
"""
        for cat in spec['classification_task']['categories']:
            prompt += f"- {cat['id']}: {cat['description']}\n"

        prompt += f"""
EXTRACTION RULES (if this is a clinic):
"""
        prompt += '\n'.join(extraction_desc)

        prompt += f"""

ADDITIONAL QUESTIONS:
"""
        prompt += '\n'.join(questions_desc)

        prompt += f"""

WEBPAGE CONTENT:

Title: {{title from markdown}}

Markdown:
{markdown}

Links found on page:
{chr(10).join(links[:100])}

<critical_instruction>
RESPOND WITH THIS EXACT JSON STRUCTURE (pure JSON, no markdown):
{json.dumps(spec['output_schema'], indent=2)}
</critical_instruction>
"""

        return prompt


class SpecDrivenClassifier:
    """Classifier that uses client spec files"""

    def __init__(self, client, spec_name, logger):
        self.client = client
        self.spec_name = spec_name
        self.logger = logger

        # Load spec
        self.spec = SpecLoader.load_spec(client, spec_name)
        self.logger.log(f"✅ Loaded spec: {client}/{spec_name}")
        self.logger.log(f"   Description: {self.spec['description']}")

        # Initialize Anthropic client
        self.api_key = os.getenv('ANTHROPIC_API_KEY')
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")

        self.anthropic = anthropic.Anthropic(api_key=self.api_key)

    def classify_page(self, page):
        """Classify a single page using spec"""
        url = page.get('url', 'unknown')

        # Truncate inputs per spec limits
        markdown = page.get('markdown', '')[:self.spec['input_limits']['markdown_max_chars']]
        links = page.get('links', [])[:self.spec['input_limits']['links_max_count']]

        # Build prompt from spec
        prompt = SpecLoader.build_prompt(self.spec, markdown, links)

        # Call Claude API
        try:
            api_settings = self.spec['api_settings']
            message = self.anthropic.messages.create(
                model=api_settings['model'],
                max_tokens=api_settings['max_tokens'],
                temperature=api_settings['temperature'],
                messages=[{"role": "user", "content": prompt}],
                timeout=api_settings['timeout_seconds']
            )

            content = message.content[0].text

            # Strip markdown code blocks if present
            cleaned_content = content.strip()
            if cleaned_content.startswith('```'):
                first_newline = cleaned_content.find('\n')
                if first_newline != -1:
                    cleaned_content = cleaned_content[first_newline+1:]
                if cleaned_content.endswith('```'):
                    cleaned_content = cleaned_content[:-3]
                cleaned_content = cleaned_content.strip()

            # Parse JSON
            result = json.loads(cleaned_content)

            # Build response with all spec fields
            response = {
                'url': url,
                'classification': result.get('classification', 'error'),
                'confidence': result.get('confidence', 'unknown'),
                'reasoning': result.get('reasoning', ''),
                'extracted_data': result.get('extracted_data', {}),
                'tokens_input': message.usage.input_tokens,
                'tokens_output': message.usage.output_tokens
            }

            # Add additional question fields dynamically
            for q in self.spec['additional_questions']:
                field = q['field']
                response[field] = result.get(field, {})

            return response

        except json.JSONDecodeError as e:
            self.logger.log(f"⚠️  JSON parse error on {url}")
            return {
                'url': url,
                'classification': 'error',
                'confidence': 'N/A',
                'reasoning': f'JSON parse error: {str(e)}',
                'extracted_data': {},
                'tokens_input': 0,
                'tokens_output': 0
            }
        except Exception as e:
            self.logger.log(f"⚠️  Error classifying {url}: {str(e)}")
            return {
                'url': url,
                'classification': 'error',
                'confidence': 'N/A',
                'reasoning': f'Error: {str(e)}',
                'extracted_data': {},
                'tokens_input': 0,
                'tokens_output': 0
            }


def main():
    parser = argparse.ArgumentParser(description='L3 Classification for Re-scraped Cities')
    parser.add_argument('--client', required=True, help='Client name (e.g., fuse)')
    parser.add_argument('--spec', required=True, help='Spec name (e.g., spec_v2_hospital_university)')
    parser.add_argument('--concurrency', type=int, default=30, help='Number of concurrent threads')
    args = parser.parse_args()

    # Initialize logger
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    log_path = f'../logs/l3_llm_classify/classify_rescraped_{args.client}_{timestamp}.log'
    logger = Logger(log_path)

    logger.log("=" * 70)
    logger.log("L3 CLASSIFICATION - RE-SCRAPED CITIES ONLY")
    logger.log("=" * 70)
    logger.log(f"Client: {args.client}")
    logger.log(f"Spec: {args.spec}")
    logger.log(f"API: Claude Sonnet 4.5 ({args.concurrency} concurrent threads)")
    logger.log(f"Log file: {log_path}")
    logger.log("")

    # Initialize classifier
    classifier = SpecDrivenClassifier(args.client, args.spec, logger)

    # Find L2 files - ONLY RE-SCRAPED ONES (Nov 8, 2025, timestamp 21xxxx+)
    l2_pattern = '../outputs/l2_scraped_*_20251108_2*.json'
    l2_files = sorted(glob.glob(l2_pattern))

    if not l2_files:
        logger.log(f"❌ ERROR: No re-scraped L2 files found matching: {l2_pattern}")
        return

    logger.log(f"📊 Found {len(l2_files)} re-scraped L2 files to process:")
    for f in l2_files:
        logger.log(f"   - {os.path.basename(f)}")
    logger.log("")

    # Process each L2 file
    batch_stats = {'individual': 0, 'group': 0, 'directory': 0, 'other': 0, 'errors': 0}
    total_input_tokens = 0
    total_output_tokens = 0

    for idx, l2_file in enumerate(l2_files, 1):
        logger.log("=" * 70)
        logger.log(f"FILE {idx}/{len(l2_files)}")
        logger.log("=" * 70)
        logger.log("")

        with open(l2_file, 'r', encoding='utf-8') as f:
            l2_data = json.load(f)

        query = l2_data.get('metadata', {}).get('query', 'Unknown')
        pages = l2_data.get('pages', [])

        logger.log(f"Processing: {query}")
        logger.log(f"Pages to classify: {len(pages)}")
        logger.log("")
        logger.log("Starting concurrent classification...")
        logger.log("")

        # Classify pages concurrently
        classified_pages = []
        stats = {'individual': 0, 'group': 0, 'directory': 0, 'other': 0, 'errors': 0}

        with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
            futures = {executor.submit(classifier.classify_page, page): page for page in pages}

            for i, future in enumerate(as_completed(futures), 1):
                result = future.result()
                classified_pages.append(result)

                # Update stats
                classification = result['classification']
                if classification == 'neurology_clinic_individual':
                    stats['individual'] += 1
                    batch_stats['individual'] += 1
                elif classification == 'neurology_clinic_group':
                    stats['group'] += 1
                    batch_stats['group'] += 1
                elif classification == 'directory':
                    stats['directory'] += 1
                    batch_stats['directory'] += 1
                elif classification == 'error':
                    stats['errors'] += 1
                    batch_stats['errors'] += 1
                else:
                    stats['other'] += 1
                    batch_stats['other'] += 1

                total_input_tokens += result.get('tokens_input', 0)
                total_output_tokens += result.get('tokens_output', 0)

                logger.log(f"[{i}/{len(pages)}] ✅ {result['url'][:50]}... → {classification} ({result['confidence']}) [{result.get('tokens_input', 0)} in, {result.get('tokens_output', 0)} out]")

        logger.log("")
        logger.log("=" * 70)
        logger.log("✅ CLASSIFICATION COMPLETE")
        logger.log("=" * 70)
        logger.log(f"   Total pages: {len(pages)}")
        logger.log(f"   Individual clinics: {stats['individual']} ({100*stats['individual']/len(pages):.1f}%)")
        logger.log(f"   Clinic groups: {stats['group']} ({100*stats['group']/len(pages):.1f}%)")
        logger.log(f"   Directories: {stats['directory']} ({100*stats['directory']/len(pages):.1f}%)")
        logger.log(f"   Other: {stats['other']} ({100*stats['other']/len(pages):.1f}%)")
        logger.log(f"   Errors: {stats['errors']} ({100*stats['errors']/len(pages):.1f}%)")
        logger.log("=" * 70)
        logger.log("")

        # Save to client-specific output folder
        output_dir = f'outputs/{args.client}'
        os.makedirs(output_dir, exist_ok=True)

        # Build output filename from L2 filename
        l2_basename = os.path.basename(l2_file).replace('l2_scraped_', 'l3_classified_')
        output_filename = f"{output_dir}/{l2_basename.replace('.json', '')}_{timestamp}.json"

        output_data = {
            'metadata': {
                'client': args.client,
                'spec': args.spec,
                'query': query,
                'source_file': l2_file,
                'classified_at': datetime.now().isoformat(),
                'stats': stats
            },
            'pages': classified_pages
        }

        with open(output_filename, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        logger.log(f"💾 Saved to: {output_filename}")
        logger.log("")

    # Final batch summary
    input_cost = total_input_tokens * 3 / 1_000_000
    output_cost = total_output_tokens * 15 / 1_000_000

    logger.log("")
    logger.log("=" * 70)
    logger.log("🎉 ALL RE-SCRAPED FILES COMPLETE!")
    logger.log("=" * 70)
    logger.log(f"   Files processed: {len(l2_files)}")
    logger.log(f"   Individual clinics: {batch_stats['individual']}")
    logger.log(f"   Clinic groups: {batch_stats['group']}")
    logger.log(f"   Directories: {batch_stats['directory']}")
    logger.log(f"   Other: {batch_stats['other']}")
    logger.log(f"   Errors: {batch_stats['errors']}")
    logger.log(f"   Input tokens: {total_input_tokens:,}")
    logger.log(f"   Output tokens: {total_output_tokens:,}")
    logger.log(f"   Cost: ${input_cost + output_cost:.3f}")
    logger.log("=" * 70)


if __name__ == '__main__':
    main()
