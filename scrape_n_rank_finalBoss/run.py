#!/usr/bin/env python3
"""
scrape_n_rank_finalBoss — Unified Production Pipeline

Single entry point for all web-based research & qualification pipelines.
Reads a YAML config to drive the right stages automatically.

Usage:
    python run.py <config_name>
    python run.py ai_mna_2025
    python run.py ai_mna_2025 --dry-run
    python run.py poka_chemicals --start-from qualify
"""

import os
import sys
import argparse
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv

# Setup paths
SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent
load_dotenv(ROOT_DIR / '.env')
load_dotenv(SCRIPT_DIR / '.env')

sys.path.insert(0, str(SCRIPT_DIR))

from core.config_loader import load_config, ConfigValidationError
from core.orchestrator import PipelineOrchestrator


def run_dry_run(config):
    """Print config details without executing anything."""
    print(f"\nDRY RUN — Config validated successfully\n")
    print(f"Client:  {config.client}")
    print(f"Name:    {config.name}")
    print(f"Stages:  {', '.join(config.active_stages)}")

    if config.input:
        print(f"\nInput CSV:  {config.input.file}")
        print(f"Column:     {config.input.column}")

    if config.search:
        s = config.search
        print(f"\nSearch:")
        print(f"  Mode: {s.mode}")
        if s.mode == 'query_list' and s.queries:
            print(f"  Queries ({len(s.queries)}):")
            for i, q in enumerate(s.queries, 1):
                print(f"    {i}. {q}")
            print(f"  Results/query: {s.results_per_query}")
        elif s.mode == 'geo' and s.cities:
            print(f"  Template: {s.query_template}")
            print(f"  Cities ({len(s.cities)}):")
            for c in s.cities[:5]:
                print(f"    - {c}")
            if len(s.cities) > 5:
                print(f"    ... and {len(s.cities) - 5} more")
            print(f"  Results/city: {s.results_per_city}")
        print(f"  Concurrency: {s.concurrency}")
        print(f"  Region: {s.gl}")

    if config.qualify:
        q = config.qualify
        print(f"\nQualify:")
        print(f"  Spec: {q.spec}")
        print(f"  Model: {q.model}")
        print(f"  Scrape mode: {q.scrape_mode}")
        print(f"  Waterfall: {q.waterfall}")
        print(f"  Max pages: {q.max_pages}")
        print(f"  Firecrawl concurrency: {q.firecrawl_concurrency}")
        print(f"  LLM concurrency: {q.llm_concurrency}")

    if config.dedupe:
        d = config.dedupe
        print(f"\nDedupe:")
        print(f"  Key field: {d.key_field}")
        print(f"  Mode: {d.mode}")

    if config.fact_check:
        f = config.fact_check
        print(f"\nFact-check:")
        print(f"  Model: {f.model}")
        print(f"  Concurrency: {f.concurrency}")
        if f.fields_to_verify:
            print(f"  Fields: {', '.join(f.fields_to_verify)}")

    if config.streaming:
        print(f"\nStreaming: enabled")
    if config.test_mode:
        print(f"Test mode: first {config.test_mode} items only")
    if config.max_cost_usd:
        print(f"Budget: ${config.max_cost_usd:.2f}")

    print()
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="scrape_n_rank_finalBoss — Unified Production Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py ai_mna_2025              # Topic research (search → qualify → dedupe → fact-check)
  python run.py burnt_us_food            # Geo discovery (search → qualify → dedupe)
  python run.py poka_chemicals           # Domain qualification (CSV → qualify → dedupe)
  python run.py ai_mna_2025 --dry-run    # Validate config only
        """,
    )
    parser.add_argument('config', help='Config name (without .yaml)')
    parser.add_argument('--dry-run', action='store_true', help='Validate config and print details only')

    args = parser.parse_args()

    # Load config
    print(f"Loading config: {args.config}")
    try:
        config = load_config(args.config)
    except (ConfigValidationError, FileNotFoundError) as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    # Dry run
    if args.dry_run or config.dry_run:
        sys.exit(run_dry_run(config))

    # Setup output directory
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    run_id = f"{config.name}_{timestamp}"
    output_dir = SCRIPT_DIR / "outputs" / config.client / run_id

    # Run pipeline
    orchestrator = PipelineOrchestrator(config, output_dir)

    try:
        summary = orchestrator.run()
        print(f"\nTotal cost: ${summary.get('total_cost_usd', 0):.4f}")
        print(f"Output:     {output_dir}")
        sys.exit(0)
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\nPipeline failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
