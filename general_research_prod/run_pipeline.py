#!/usr/bin/env python3
"""
General Research Pipeline - Combined Search + Scrape + Dedupe + Fact-Check

Single entry point that reads one YAML config to drive:
  1. SEARCH      - Discover domains via Serper.dev
  2. SCRAPE      - Qualify/extract via Firecrawl + LLM
  3. DEDUPE      - Deduplicate results by key field
  4. FACT-CHECK  - Verify deals via Perplexity Sonar API

Usage:
    python run_pipeline.py <config_name>
    python run_pipeline.py ai_mna_2025
    python run_pipeline.py ai_mna_2025 --dry-run
    python run_pipeline.py ai_mna_2025 --skip-search --domains path/to/domains.csv
"""

import os
import sys
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv

# Load environment variables
SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent
load_dotenv(ROOT_DIR / '.env')

# Local imports
sys.path.insert(0, str(SCRIPT_DIR))
from core.config_loader import load_config, ConfigValidationError
from core.search_layer import SearchLayer
from core.dedupe import dedupe_results
from core.fact_check import fact_check_deals

# Import qualifying system (no code duplication)
QUALIFYING_DIR = ROOT_DIR / "qualifying_agentic_system_prod"
sys.path.insert(0, str(QUALIFYING_DIR))
from core_openai.pipeline import BatchPipeline, PipelineConfig as QualifyConfig


def setup_logger(output_dir: Path) -> logging.Logger:
    """Setup file + console logger."""
    logger = logging.getLogger('research_pipeline')
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    # File handler
    fh = logging.FileHandler(output_dir / "run.log")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(fh)

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(ch)

    return logger


def run_pipeline(config_name: str, args):
    """Main pipeline orchestrator."""

    # ─── Load Config ───────────────────────────────────────────
    print(f"Loading config: {config_name}")
    try:
        config = load_config(config_name)
    except (ConfigValidationError, FileNotFoundError) as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    # ─── Setup Output Directory ────────────────────────────────
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    run_id = f"{config.name}_{timestamp}"
    output_dir = SCRIPT_DIR / "outputs" / config.client / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    logger = setup_logger(output_dir)

    logger.info("=" * 70)
    logger.info("GENERAL RESEARCH PIPELINE")
    logger.info("=" * 70)
    logger.info(f"Client:  {config.client}")
    logger.info(f"Name:    {config.name}")
    logger.info(f"Output:  {output_dir}")
    logger.info(f"Queries: {len(config.search.queries)}")
    logger.info(f"Spec:    {config.scrape.spec}")
    logger.info(f"Model:   {config.scrape.model}")
    logger.info("=" * 70)

    # ─── Dry Run ───────────────────────────────────────────────
    if config.dry_run or args.dry_run:
        logger.info("\nDRY RUN - Config validated successfully")
        logger.info(f"\nQueries ({len(config.search.queries)}):")
        for i, q in enumerate(config.search.queries, 1):
            logger.info(f"  {i}. {q}")
        logger.info(f"\nSpec: {config.scrape.spec}")
        logger.info(f"Model: {config.scrape.model}")
        logger.info(f"Waterfall: {config.scrape.use_waterfall}")
        logger.info(f"Dedupe key: {config.dedupe.key_field}")
        return 0

    # ─── Stage 1: SEARCH ──────────────────────────────────────
    if args.skip_search and args.domains:
        # Skip search, use provided domains CSV
        domains_csv = args.domains
        logger.info(f"\nSkipping search, using provided domains: {domains_csv}")
        search_cost = 0
    else:
        logger.info("\n" + "=" * 70)
        logger.info("STAGE 1: SEARCH (Serper.dev)")
        logger.info("=" * 70)

        search_layer = SearchLayer(
            queries=config.search.queries,
            results_per_query=config.search.results_per_query,
            gl=config.search.gl,
            concurrency=config.search.concurrency,
            output_dir=output_dir,
            logger=logger,
            test_mode=config.test_mode,
        )

        search_result = search_layer.run()
        domains_csv = search_result['domains_csv']
        search_cost = search_result['cost_usd']

        if search_result['unique_domains'] == 0:
            logger.info("No domains found. Stopping.")
            return 0

    # ─── Stage 2: SCRAPE + QUALIFY ─────────────────────────────
    logger.info("\n" + "=" * 70)
    logger.info("STAGE 2: SCRAPE + QUALIFY (Firecrawl + LLM)")
    logger.info("=" * 70)

    # Resolve spec path
    spec_name = config.scrape.spec
    if not spec_name.endswith('.json'):
        spec_name += '.json'
    spec_path = SCRIPT_DIR / "specs" / spec_name

    # Configure the qualifying pipeline - output directly into our run folder
    qualify_config = QualifyConfig(
        spec_path=str(spec_path),
        client_name=config.client,
        run_name=config.name,
        openai_model=config.scrape.model,
        firecrawl_concurrency=config.scrape.firecrawl_concurrency,
        openai_concurrency=config.scrape.openai_concurrency,
        max_pages=config.scrape.max_pages,
        use_waterfall=config.scrape.use_waterfall,
        output_dir=str(output_dir),
        scrape_mode=config.scrape.mode,
    )

    pipeline = BatchPipeline(config=qualify_config)
    results = pipeline.run(domains_csv)

    # Qualifying system now writes directly to output_dir:
    #   results.csv, results.jsonl, analytics.jsonl, summary.json
    our_qualify_csv = output_dir / "results.csv"

    # ─── Stage 3: DEDUPE ───────────────────────────────────────
    deduped_csv = output_dir / "4_deduped_results.csv"
    if config.dedupe.enabled and our_qualify_csv.exists():
        logger.info("\n" + "=" * 70)
        logger.info("STAGE 3: DEDUPE")
        logger.info("=" * 70)
        dedupe_stats = dedupe_results(
            input_csv=our_qualify_csv,
            output_csv=deduped_csv,
            key_field=config.dedupe.key_field,
            mode=config.dedupe.mode,
            logger=logger,
        )
    else:
        dedupe_stats = {"duplicates_removed": 0, "total_output": 0}
        deduped_csv = our_qualify_csv  # fact-check reads from qualify results directly

    # ─── Stage 4: FACT-CHECK ─────────────────────────────────────
    fc_stats = {}
    if config.fact_check and config.fact_check.enabled and deduped_csv.exists():
        logger.info("\n" + "=" * 70)
        logger.info("STAGE 4: FACT-CHECK (Perplexity Sonar)")
        logger.info("=" * 70)

        factchecked_csv = output_dir / "5_factchecked_results.csv"
        fc_stats = fact_check_deals(
            input_csv=deduped_csv,
            output_csv=factchecked_csv,
            config=config.fact_check,
            key_field=config.dedupe.key_field,
            logger=logger,
        )

    # ─── Final Summary ─────────────────────────────────────────
    logger.info("\n" + "=" * 70)
    logger.info("PIPELINE COMPLETE")
    logger.info("=" * 70)

    # Load qualify summary for cost info (now written directly to output_dir)
    qualify_cost = 0
    qualify_data = {}
    qualify_summary_path = output_dir / "summary.json"
    if qualify_summary_path.exists():
        with open(qualify_summary_path) as f:
            qualify_data = json.load(f)
            qualify_cost = qualify_data.get('cost_usd', {}).get('total', 0)

    total_cost = search_cost + qualify_cost

    summary = {
        "client": config.client,
        "name": config.name,
        "completed_at": datetime.now().isoformat(),
        "search": {
            "queries": len(config.search.queries),
            "domains_found": search_result['unique_domains'] if not args.skip_search else "N/A",
            "cost_usd": round(search_cost, 4),
        },
        "qualify": {
            "total_domains": qualify_data.get('total_domains', 0),
            "filtered_early": qualify_data.get('filtered_early', 0),
            "homepage_sufficient": qualify_data.get('homepage_sufficient', 0),
            "needed_iteration": qualify_data.get('needed_iteration', 0),
            "failed": qualify_data.get('failed', 0),
            "cost_usd": round(qualify_cost, 4),
        },
        "dedupe": dedupe_stats,
        "fact_check": fc_stats,
        "total_cost_usd": round(total_cost, 4),
        "output_dir": str(output_dir),
    }

    summary_path = output_dir / "summary.json"
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2)

    logger.info(f"Search cost:   ${search_cost:.4f}")
    logger.info(f"Qualify cost:  ${qualify_cost:.4f}")
    logger.info(f"Total cost:    ${total_cost:.4f}")
    logger.info(f"Dedupe:        {dedupe_stats.get('duplicates_removed', 0)} duplicates removed")
    logger.info(f"Output:        {output_dir}")
    logger.info("=" * 70)

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="General Research Pipeline - Search + Scrape + Dedupe",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_pipeline.py ai_mna_2025
  python run_pipeline.py ai_mna_2025 --dry-run
  python run_pipeline.py ai_mna_2025 --skip-search --domains path/to/domains.csv
        """
    )
    parser.add_argument('config', help='Config name (without .yaml)')
    parser.add_argument('--dry-run', action='store_true', help='Validate config only')
    parser.add_argument('--skip-search', action='store_true', help='Skip search stage')
    parser.add_argument('--domains', help='Path to domains CSV (use with --skip-search)')

    args = parser.parse_args()
    exit_code = run_pipeline(args.config, args)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
