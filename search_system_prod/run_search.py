#!/usr/bin/env python3
"""
Search System - Domain Discovery Pipeline

Simple pipeline that searches for businesses across cities and outputs a domains.csv
ready to feed into the qualifying_agentic_system_prod for classification.

Usage:
    python run_search.py <config_name>
    python run_search.py burnt_arkansas_food_distributors
    python run_search.py burnt_arkansas_food_distributors --dry-run

Output:
    outputs/{client}/{run_id}/domains.csv
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv(Path(__file__).parent.parent / '.env')

# Add core to path
sys.path.insert(0, str(Path(__file__).parent))

from core.config_loader import load_config, ConfigValidationError
from core.progress_tracker import ProgressTracker
from core.cost_tracker import CostTracker
from core.diagnostics import DiagnosticsManager
from core.layer_search import SearchLayer


class SearchPipeline:
    """
    Simple search-only pipeline.

    Searches for businesses across cities and outputs domains.csv
    """

    def __init__(self, config_name: str, args):
        """
        Initialize search pipeline

        Args:
            config_name: Name of the run config file
            args: Parsed command-line arguments
        """
        self.config_name = config_name
        self.args = args

        # Load configuration
        print(f"Loading configuration: {config_name}")
        try:
            self.config = load_config(config_name)
        except (ConfigValidationError, FileNotFoundError) as e:
            print(f"ERROR: Failed to load config: {e}")
            sys.exit(1)

        # Create run ID
        self.run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Setup output directory
        outputs_base = Path(__file__).parent / "outputs"
        self.client_output_dir = outputs_base / self.config.client
        self.output_dir = self.client_output_dir / self.run_id
        self.output_dir.mkdir(parents=True, exist_ok=True)

        print(f"Output directory: {self.output_dir}")

        # Initialize tracking systems
        self.progress = ProgressTracker(self.output_dir)
        self.costs = CostTracker(self.output_dir, self.config.max_cost_usd)
        self.diagnostics = DiagnosticsManager(self.output_dir)

        # Setup logging
        self._setup_logging()

        # Log configuration
        self.logger.info("=" * 60)
        self.logger.info("SEARCH SYSTEM - DOMAIN DISCOVERY")
        self.logger.info("=" * 60)
        self.logger.info(f"Run ID: {self.run_id}")
        self.logger.info(f"Client: {self.config.client}")
        self.logger.info(f"Search query: {self.config.search.query}")
        self.logger.info(f"Cities: {len(self.config.search.cities)}")
        self.logger.info(f"Results per city: {self.config.search.results_per_city}")
        self.logger.info(f"Test mode: {self.config.test_mode or 'disabled'}")
        self.logger.info("=" * 60)

    def _setup_logging(self):
        """Setup file and console logging"""
        self.logger = logging.getLogger('search_pipeline')
        self.logger.setLevel(logging.DEBUG)

        # File handler
        log_file = self.output_dir / "run.log"
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(file_formatter)

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter('%(message)s')
        console_handler.setFormatter(console_formatter)

        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

    def run(self):
        """
        Execute the search pipeline

        Returns:
            Exit code (0 for success, 1 for failure)
        """
        try:
            self.logger.info("\n" + "=" * 60)
            self.logger.info("SEARCHING...")
            self.logger.info("=" * 60)

            # Run search layer
            layer = SearchLayer(
                config=self.config,
                progress=self.progress,
                costs=self.costs,
                diagnostics=self.diagnostics,
                logger=self.logger,
                output_dir=self.output_dir
            )

            result = layer.run()

            # Complete the run
            self.progress.complete_run()

            self.logger.info("\n" + "=" * 60)
            self.logger.info("SEARCH COMPLETE")
            self.logger.info("=" * 60)
            self.logger.info(f"Total URLs found: {result['total_results']}")
            self.logger.info(f"Unique domains: {result['unique_domains']}")
            self.logger.info(f"Output: {result['domains_csv']}")
            self.logger.info("=" * 60)

            # Print summaries
            print(self.progress.to_console_string())
            print(self.costs.to_console_string())

            print(f"\n✅ Ready for qualification pipeline:")
            print(f"   python qualifying_agentic_system_prod/core/pipeline.py {result['domains_csv']}")

            return 0

        except KeyboardInterrupt:
            self.logger.error("\nPipeline interrupted by user")
            self.progress.fail_run("Interrupted by user")
            return 1

        except Exception as e:
            self.logger.error(f"\nPipeline failed with error: {e}", exc_info=True)
            self.progress.fail_run(str(e))
            return 1


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Search for businesses across cities and output domains.csv",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with config file
  python run_search.py burnt_arkansas_food_distributors

  # Dry run (validate configs only)
  python run_search.py burnt_arkansas_food_distributors --dry-run

Output:
  domains.csv with columns: domain, url, city, title, snippet
  Ready to feed into qualifying_agentic_system_prod
        """
    )

    parser.add_argument(
        'config',
        help='Name of the run config file (without .yaml extension)'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Validate configs only, do not execute pipeline'
    )

    parser.add_argument(
        '--max-cost',
        type=float,
        help='Override max cost threshold (USD)'
    )

    args = parser.parse_args()

    # Create pipeline
    pipeline = SearchPipeline(args.config, args)

    # Dry run mode
    if args.dry_run:
        print("\n" + "=" * 60)
        print("DRY RUN MODE: Configuration validated successfully")
        print("=" * 60)
        print(f"Config: {pipeline.config_name}")
        print(f"Client: {pipeline.config.client}")
        print(f"Query: {pipeline.config.search.query}")
        print(f"Cities: {len(pipeline.config.search.cities)}")
        print(f"Results per city: {pipeline.config.search.results_per_city}")
        print("=" * 60)
        return 0

    # Run pipeline
    exit_code = pipeline.run()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
