#!/usr/bin/env python3
"""
Production Pipeline Orchestrator

Main entry point for running the search and analysis pipeline.
Loads configs, manages layers, tracks progress, costs, and diagnostics.
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
from core.spec_loader import load_spec, SpecValidationError
from core.progress_tracker import ProgressTracker
from core.cost_tracker import CostTracker
from core.diagnostics import DiagnosticsManager
from core.domain_cache import GlobalDomainCache
from core.queue_manager import QueueManager
from core.classify_queue_manager import ClassifyQueueManager
from core.layer_search import SearchLayer
from core.layer_scrape import ScrapeLayer
from core.layer_classify import ClassifyLayer
from core.layer_export import ExportLayer
from core.layer_dedupe import DedupeLayer
import threading


class PipelineOrchestrator:
    """
    Orchestrates the entire search and analysis pipeline

    Manages:
    - Config/spec loading
    - Layer execution
    - Progress tracking
    - Cost tracking
    - Diagnostics
    - Domain deduplication
    - Error handling
    """

    def __init__(self, config_name: str, args):
        """
        Initialize pipeline orchestrator

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

        # Load analysis spec
        print(f"Loading analysis spec: {self.config.analysis_spec}")
        try:
            self.spec = load_spec(self.config.analysis_spec)
        except (SpecValidationError, FileNotFoundError) as e:
            print(f"ERROR: Failed to load spec: {e}")
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
        self.domain_cache = GlobalDomainCache(self.client_output_dir)

        # Setup logging
        self._setup_logging()

        # Log configuration
        self.logger.info("="*60)
        self.logger.info(f"Pipeline run started: {self.run_id}")
        self.logger.info(f"Client: {self.config.client}")
        self.logger.info(f"Search query: {self.config.search.query}")
        self.logger.info(f"Cities: {', '.join(self.config.search.cities)}")
        self.logger.info(f"Results per city: {self.config.search.results_per_city}")
        self.logger.info(f"Analysis spec: {self.spec.spec_name}")
        self.logger.info(f"LLM model: {self.spec.llm.model}")
        self.logger.info(f"Test mode: {self.config.test_mode or 'disabled'}")
        self.logger.info(f"Max cost: ${self.config.max_cost_usd or 'unlimited'}")
        self.logger.info("="*60)

    def _setup_logging(self):
        """Setup file and console logging"""
        # Create logger
        self.logger = logging.getLogger('pipeline')
        self.logger.setLevel(logging.DEBUG)

        # File handler (exhaustive logs)
        log_file = self.output_dir / "run.log"
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(file_formatter)

        # Console handler (important messages only)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter('%(message)s')
        console_handler.setFormatter(console_formatter)

        # Add handlers
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

    def run(self):
        """
        Execute the complete pipeline

        Returns:
            Exit code (0 for success, 1 for failure)
        """
        try:
            # Determine which layers to run
            start_layer = self._get_start_layer()

            self.logger.info(f"\nStarting pipeline from layer: {start_layer}\n")

            # Run L1, L2, and L3 concurrently with streaming queues
            if start_layer <= 3:
                self._run_layers_1_2_3_streaming()
            elif start_layer == 2:
                # If starting from L2, use old L1+L2 streaming, then L3
                self._run_layers_1_2_streaming()
                self._run_layer_3_classify()
            elif start_layer == 1:
                self._run_layer_1_search()
                self._run_layer_3_classify()

            if start_layer <= 4:
                self._run_layer_4_export()

            if start_layer <= 5:
                self._run_layer_5_dedupe()

            # Complete the run
            self.progress.complete_run()
            self.logger.info("\n" + "="*60)
            self.logger.info("PIPELINE COMPLETED SUCCESSFULLY")
            self.logger.info("="*60)

            # Print final summaries
            print(self.progress.to_console_string())
            print(self.costs.to_console_string())

            return 0

        except KeyboardInterrupt:
            self.logger.error("\nPipeline interrupted by user")
            self.progress.fail_run("Interrupted by user")
            return 1

        except Exception as e:
            self.logger.error(f"\nPipeline failed with error: {e}", exc_info=True)
            self.progress.fail_run(str(e))
            return 1

    def _get_start_layer(self) -> int:
        """Determine which layer to start from"""
        if self.config.start_from:
            layer_map = {
                "search": 1,
                "scrape": 2,
                "classify": 3,
                "export": 4,
                "dedupe": 5
            }
            return layer_map.get(self.config.start_from, 1)
        return 1

    def _run_layer_1_search(self):
        """Run Layer 1: Search via Serper.dev"""
        self.logger.info("\n" + "="*60)
        self.logger.info("LAYER 1: SEARCH (Serper.dev)")
        self.logger.info("="*60)

        layer = SearchLayer(
            config=self.config,
            progress=self.progress,
            costs=self.costs,
            diagnostics=self.diagnostics,
            logger=self.logger,
            output_dir=self.output_dir
        )

        layer.run()

    def _run_layer_2_scrape(self):
        """Run Layer 2: Scrape via Firecrawl"""
        self.logger.info("\n" + "="*60)
        self.logger.info("LAYER 2: SCRAPE (Firecrawl)")
        self.logger.info("="*60)

        layer = ScrapeLayer(
            config=self.config,
            progress=self.progress,
            costs=self.costs,
            diagnostics=self.diagnostics,
            domain_cache=self.domain_cache,
            logger=self.logger,
            output_dir=self.output_dir,
            run_id=self.run_id
        )

        layer.run()

    def _run_layers_1_2_streaming(self):
        """Run L1 and L2 concurrently with streaming queue"""
        self.logger.info("\n" + "="*60)
        self.logger.info("STREAMING PIPELINE: L1 (Search) + L2 (Scrape)")
        self.logger.info("="*60)
        self.logger.info("L1 and L2 run concurrently with progressive feeding")
        self.logger.info("")

        # Create queue manager
        queue_manager = QueueManager(
            domain_cache=self.domain_cache,
            logger=self.logger
        )

        # Create L1 signal event
        l1_complete = threading.Event()

        # Create layers
        l1_layer = SearchLayer(
            config=self.config,
            progress=self.progress,
            costs=self.costs,
            diagnostics=self.diagnostics,
            logger=self.logger,
            output_dir=self.output_dir,
            queue_manager=queue_manager
        )

        l2_layer = ScrapeLayer(
            config=self.config,
            progress=self.progress,
            costs=self.costs,
            diagnostics=self.diagnostics,
            domain_cache=self.domain_cache,
            logger=self.logger,
            output_dir=self.output_dir,
            run_id=self.run_id,
            queue_manager=queue_manager
        )

        # Start L1 and L2 in threads
        def run_l1():
            self.logger.info("\n" + "="*60)
            self.logger.info("LAYER 1: SEARCH (Serper.dev)")
            self.logger.info("="*60)
            l1_layer.run()
            l1_complete.set()
            self.logger.info("\n✓ L1 complete - signaling L2 workers")

        def run_l2():
            self.logger.info("\n" + "="*60)
            self.logger.info("LAYER 2: SCRAPE (Firecrawl)")
            self.logger.info("="*60)
            l2_layer.run_from_queue(l1_complete)

        # Launch threads
        l1_thread = threading.Thread(target=run_l1, name="L1-Search")
        l2_thread = threading.Thread(target=run_l2, name="L2-Scrape")

        l2_thread.start()  # Start L2 workers first (they'll wait for queue items)
        l1_thread.start()  # Start L1 feeding

        # Wait for completion
        l1_thread.join()
        l2_thread.join()

        self.logger.info("\n✓ Streaming pipeline (L1+L2) complete")

    def _run_layers_1_2_3_streaming(self):
        """Run L1, L2, and L3 concurrently with streaming queues"""
        self.logger.info("\n" + "="*60)
        self.logger.info("STREAMING PIPELINE: L1 (Search) + L2 (Scrape) + L3 (Classify)")
        self.logger.info("="*60)
        self.logger.info("All layers run concurrently with progressive feeding")
        self.logger.info("")

        # Create queue managers
        l2_queue_manager = QueueManager(
            domain_cache=self.domain_cache,
            logger=self.logger
        )

        l3_queue_manager = ClassifyQueueManager(
            logger=self.logger
        )

        # Create signal events
        l1_complete = threading.Event()
        l2_complete = threading.Event()

        # Create layers
        l1_layer = SearchLayer(
            config=self.config,
            progress=self.progress,
            costs=self.costs,
            diagnostics=self.diagnostics,
            logger=self.logger,
            output_dir=self.output_dir,
            queue_manager=l2_queue_manager
        )

        l2_layer = ScrapeLayer(
            config=self.config,
            progress=self.progress,
            costs=self.costs,
            diagnostics=self.diagnostics,
            domain_cache=self.domain_cache,
            logger=self.logger,
            output_dir=self.output_dir,
            run_id=self.run_id,
            queue_manager=l2_queue_manager,
            classify_queue_manager=l3_queue_manager
        )

        l3_layer = ClassifyLayer(
            config=self.config,
            spec=self.spec,
            progress=self.progress,
            costs=self.costs,
            diagnostics=self.diagnostics,
            logger=self.logger,
            output_dir=self.output_dir
        )

        # Define thread functions
        def run_l1():
            self.logger.info("\n" + "="*60)
            self.logger.info("LAYER 1: SEARCH (Serper.dev)")
            self.logger.info("="*60)
            l1_layer.run()
            l1_complete.set()
            self.logger.info("\n✓ L1 complete - signaling L2 workers")

        def run_l2():
            self.logger.info("\n" + "="*60)
            self.logger.info("LAYER 2: SCRAPE (Firecrawl)")
            self.logger.info("="*60)
            l2_layer.run_from_queue(l1_complete)
            l2_complete.set()
            self.logger.info("\n✓ L2 complete - signaling L3 workers")

        def run_l3():
            self.logger.info("\n" + "="*60)
            self.logger.info("LAYER 3: CLASSIFY (Claude)")
            self.logger.info("="*60)
            l3_layer.run_from_queue(l2_complete, l3_queue_manager)
            self.logger.info("\n✓ L3 complete")

        # Launch threads
        l3_thread = threading.Thread(target=run_l3, name="L3-Classify")
        l2_thread = threading.Thread(target=run_l2, name="L2-Scrape")
        l1_thread = threading.Thread(target=run_l1, name="L1-Search")

        l3_thread.start()  # Start L3 workers first (they'll wait for queue items)
        l2_thread.start()  # Start L2 workers second (they'll wait for queue items)
        l1_thread.start()  # Start L1 feeding

        # Wait for completion
        l1_thread.join()
        l2_thread.join()
        l3_thread.join()

        self.logger.info("\n✓ Streaming pipeline (L1+L2+L3) complete")

    def _run_layer_3_classify(self):
        """Run Layer 3: Classify via Claude"""
        self.logger.info("\n" + "="*60)
        self.logger.info("LAYER 3: CLASSIFY (Claude)")
        self.logger.info("="*60)

        layer = ClassifyLayer(
            config=self.config,
            spec=self.spec,
            progress=self.progress,
            costs=self.costs,
            diagnostics=self.diagnostics,
            logger=self.logger,
            output_dir=self.output_dir
        )

        layer.run()

    def _run_layer_4_export(self):
        """Run Layer 4: CSV Export"""
        self.logger.info("\n" + "="*60)
        self.logger.info("LAYER 4: EXPORT (CSV)")
        self.logger.info("="*60)

        layer = ExportLayer(
            config=self.config,
            spec=self.spec,
            progress=self.progress,
            diagnostics=self.diagnostics,
            logger=self.logger,
            output_dir=self.output_dir
        )

        layer.run()

    def _run_layer_5_dedupe(self):
        """Run Layer 5: Domain Deduplication"""
        self.logger.info("\n" + "="*60)
        self.logger.info("LAYER 5: DEDUPLICATION")
        self.logger.info("="*60)

        layer = DedupeLayer(
            config=self.config,
            progress=self.progress,
            diagnostics=self.diagnostics,
            logger=self.logger,
            output_dir=self.output_dir
        )

        layer.run()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Production search and analysis pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with config file
  python run_pipeline.py fuse_neurology_test

  # Start from specific layer
  python run_pipeline.py fuse_neurology_test --start-from scrape

  # Re-run failures from previous run
  python run_pipeline.py fuse_neurology_test --rerun-failures --from-run run_20251113_140000

  # Dry run (validate configs only)
  python run_pipeline.py fuse_neurology_test --dry-run
        """
    )

    parser.add_argument(
        'config',
        help='Name of the run config file (without .yaml extension)'
    )

    parser.add_argument(
        '--start-from',
        choices=['search', 'scrape', 'classify', 'export', 'dedupe'],
        help='Start from a specific layer (skips earlier layers)'
    )

    parser.add_argument(
        '--rerun-failures',
        action='store_true',
        help='Re-run only failed items from a previous run'
    )

    parser.add_argument(
        '--from-run',
        help='Run ID to load failures from (required with --rerun-failures)'
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

    # Validate arguments
    if args.rerun_failures and not args.from_run:
        parser.error("--from-run is required when using --rerun-failures")

    # Create orchestrator
    orchestrator = PipelineOrchestrator(args.config, args)

    # Dry run mode
    if args.dry_run:
        print("\n" + "="*60)
        print("DRY RUN MODE: Configuration validated successfully")
        print("="*60)
        print(f"Config: {orchestrator.config_name}")
        print(f"Client: {orchestrator.config.client}")
        print(f"Spec: {orchestrator.spec.spec_name}")
        print(f"Cities: {len(orchestrator.config.search.cities)}")
        print(f"Model: {orchestrator.spec.llm.model}")
        print("="*60)
        return 0

    # Run pipeline
    exit_code = orchestrator.run()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
