"""
Pipeline Orchestrator

Composes and executes pipeline stages based on config.
Supports sequential and streaming (concurrent search+qualify) execution modes.
"""

import csv
import json
import time
import logging
import threading
from pathlib import Path
from datetime import datetime
from dataclasses import asdict
from typing import Dict, Any, Optional

from core.config_loader import PipelineConfig
from core.spec_loader import AnalysisSpec, load_spec
from core.analytics import AnalyticsEngine
from core.output_manager import OutputManager
from core.queue_manager import StageQueue
from stages.search import SearchStage
from stages.qualify import QualifyStage
from stages.dedupe import DedupeStage
from stages.fact_check import FactCheckStage


class PipelineOrchestrator:
    """
    Main orchestrator that composes and executes pipeline stages.

    Reads a PipelineConfig to determine which stages run, loads the spec,
    sets up analytics/output, and executes stages in the correct order.
    """

    STAGE_ORDER = ["search", "qualify", "dedupe", "fact_check"]

    def __init__(self, config: PipelineConfig, output_dir: Path):
        self.config = config
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Setup logger
        self.logger = self._setup_logger()

        # Setup analytics
        self.analytics = AnalyticsEngine(
            self.output_dir,
            max_cost_usd=config.max_cost_usd,
        )

        # Setup output manager
        self.output = OutputManager(self.output_dir)

        # Load spec if qualify stage is configured
        self.spec = None
        if config.qualify:
            spec_name = config.qualify.spec
            specs_dir = Path(__file__).parent.parent / "configs" / "specs"
            self.spec = load_spec(spec_name, specs_dir=specs_dir)

        # Save config snapshot
        self.output.save_config_snapshot(config.to_dict())

    def run(self) -> Dict[str, Any]:
        """Execute the full pipeline. Returns summary dict."""
        self.logger.info("=" * 70)
        self.logger.info("PIPELINE ORCHESTRATOR")
        self.logger.info("=" * 70)
        self.logger.info(f"Client:  {self.config.client}")
        self.logger.info(f"Name:    {self.config.name}")
        self.logger.info(f"Output:  {self.output_dir}")
        self.logger.info(f"Stages:  {', '.join(self.config.active_stages)}")
        if self.config.streaming:
            self.logger.info(f"Mode:    STREAMING")
        if self.config.test_mode:
            self.logger.info(f"Test:    First {self.config.test_mode} items only")
        if self.config.max_cost_usd:
            self.logger.info(f"Budget:  ${self.config.max_cost_usd:.2f}")
        self.logger.info("=" * 70)

        try:
            if self._should_stream():
                result = self._run_streaming()
            else:
                result = self._run_sequential()

            self.analytics.finalize()

            # Write final summary
            summary = self._build_summary(result)
            self.output.write_summary(summary)

            # Print analytics
            self.logger.info(self.analytics.to_console_string())
            self.logger.info(f"\nOutput: {self.output_dir}")

            return summary

        except Exception as e:
            self.logger.error(f"Pipeline failed: {e}", exc_info=True)
            self.analytics.progress_tracker.fail_run(str(e))
            raise

    def _should_stream(self) -> bool:
        """Determine if streaming mode should be used."""
        return (
            self.config.streaming
            and self.config.has_search
            and self.config.has_qualify
        )

    def _run_sequential(self) -> Dict[str, Any]:
        """Run stages one at a time, passing output from one to the next."""
        result = {}
        stage_data = None  # Data passed between stages

        # If starting from CSV input (no search), load domains
        if self.config.input and not self.config.has_search:
            stage_data = self._load_input_csv()

        for stage_name in self.STAGE_ORDER:
            if stage_name not in self.config.active_stages:
                continue

            if self.analytics.is_over_budget():
                self.logger.warning("Budget exceeded — stopping pipeline")
                break

            self.logger.info(f"\n{'=' * 70}")
            self.logger.info(f"STAGE: {stage_name.upper()}")
            self.logger.info(f"{'=' * 70}")

            stage = self._create_stage(stage_name)
            stage_result = stage.run(stage_data)

            result[stage_name] = stage_result
            stage_data = stage_result  # Pass to next stage

        return result

    def _run_streaming(self) -> Dict[str, Any]:
        """
        Run search and qualify concurrently via a shared queue.
        Search feeds domains to qualify progressively.
        Dedupe and fact_check still run sequentially after.
        """
        result = {}
        domain_queue = StageQueue(dedup_key="domain")
        search_complete = threading.Event()
        qualify_complete = threading.Event()

        search_error = [None]
        qualify_error = [None]
        search_result = [None]
        qualify_result = [None]

        # Create stages
        search_stage = self._create_stage("search", queue=domain_queue)
        qualify_stage = self._create_stage("qualify")

        def run_search():
            try:
                self.logger.info(f"\n{'=' * 70}")
                self.logger.info("STAGE: SEARCH (streaming)")
                self.logger.info(f"{'=' * 70}")
                search_result[0] = search_stage.run(None)
            except Exception as e:
                search_error[0] = e
                self.logger.error(f"Search failed: {e}")
            finally:
                domain_queue.signal_complete()
                search_complete.set()

        def run_qualify():
            try:
                self.logger.info(f"\n{'=' * 70}")
                self.logger.info("STAGE: QUALIFY (streaming)")
                self.logger.info(f"{'=' * 70}")

                # Collect domains from queue as they arrive
                domains = []
                while True:
                    item = domain_queue.get(timeout=2.0)
                    if item is not None:
                        domains.append(item)
                        # Process in batches of 10 for efficiency
                        if len(domains) >= 10:
                            batch = domains[:]
                            domains = []
                            # Feed to qualify (it handles threading internally)
                            qualify_stage.run({"domains": batch})
                    elif search_complete.is_set() and domain_queue.qsize() == 0:
                        # Search is done and queue is empty
                        break

                # Process remaining domains
                if domains:
                    qualify_stage.run({"domains": domains})

                qualify_result[0] = {
                    "results_csv": str(self.output_dir / "results.csv"),
                }
            except Exception as e:
                qualify_error[0] = e
                self.logger.error(f"Qualify failed: {e}")
            finally:
                qualify_complete.set()

        # Start both threads
        search_thread = threading.Thread(target=run_search, name="search-thread")
        qualify_thread = threading.Thread(target=run_qualify, name="qualify-thread")

        search_thread.start()
        qualify_thread.start()

        search_thread.join()
        qualify_thread.join()

        # Collect results
        if search_result[0]:
            result["search"] = search_result[0]
        if qualify_result[0]:
            result["qualify"] = qualify_result[0]

        if search_error[0]:
            raise search_error[0]
        if qualify_error[0]:
            raise qualify_error[0]

        # Continue with remaining sequential stages
        stage_data = qualify_result[0] or {}
        for stage_name in ["dedupe", "fact_check"]:
            if stage_name not in self.config.active_stages:
                continue

            if self.analytics.is_over_budget():
                self.logger.warning("Budget exceeded — stopping pipeline")
                break

            self.logger.info(f"\n{'=' * 70}")
            self.logger.info(f"STAGE: {stage_name.upper()}")
            self.logger.info(f"{'=' * 70}")

            stage = self._create_stage(stage_name)
            stage_result = stage.run(stage_data)
            result[stage_name] = stage_result
            stage_data = stage_result

        return result

    def _create_stage(self, stage_name: str, queue=None):
        """Create a stage instance with proper config."""
        stage_config = self._get_stage_config_dict(stage_name)

        # Apply test_mode limits
        if self.config.test_mode and stage_name == "search":
            mode = stage_config.get('mode', 'query_list')
            if mode == 'query_list' and 'queries' in stage_config:
                stage_config['queries'] = stage_config['queries'][:self.config.test_mode]
            elif mode == 'geo' and 'cities' in stage_config:
                stage_config['cities'] = stage_config['cities'][:self.config.test_mode]

        if stage_name == "search":
            return SearchStage(
                config=stage_config,
                spec=self.spec,
                analytics=self.analytics,
                output=self.output,
                logger=self.logger,
                queue=queue,
            )
        elif stage_name == "qualify":
            return QualifyStage(
                config=stage_config,
                spec=self.spec,
                analytics=self.analytics,
                output=self.output,
                logger=self.logger,
            )
        elif stage_name == "dedupe":
            return DedupeStage(
                config=stage_config,
                spec=self.spec,
                analytics=self.analytics,
                output=self.output,
                logger=self.logger,
            )
        elif stage_name == "fact_check":
            return FactCheckStage(
                config=stage_config,
                spec=self.spec,
                analytics=self.analytics,
                output=self.output,
                logger=self.logger,
            )
        else:
            raise ValueError(f"Unknown stage: {stage_name}")

    def _get_stage_config_dict(self, stage_name: str) -> dict:
        """Convert a stage's dataclass config to a dict for stage constructors."""
        stage_obj = getattr(self.config, stage_name, None)
        if stage_obj is None:
            return {}
        return asdict(stage_obj)

    def _load_input_csv(self) -> Dict[str, Any]:
        """Load domains from an input CSV file."""
        input_config = self.config.input
        input_path = Path(input_config.file)

        # Try relative to project root
        if not input_path.is_absolute():
            project_root = Path(__file__).parent.parent
            input_path = project_root / input_path

        if not input_path.exists():
            raise FileNotFoundError(f"Input CSV not found: {input_path}")

        column = input_config.column
        domains = []

        with open(input_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                domain = row.get(column, '').strip()
                if domain:
                    domains.append({
                        'domain': domain,
                        'url': row.get('url', ''),
                        'title': row.get('title', ''),
                    })

        self.logger.info(f"Loaded {len(domains)} domains from {input_path}")

        # Apply test_mode limit
        if self.config.test_mode:
            domains = domains[:self.config.test_mode]
            self.logger.info(f"Test mode: using first {len(domains)} domains")

        return {"domains": domains}

    def _build_summary(self, result: Dict) -> dict:
        """Build final pipeline summary."""
        return {
            "client": self.config.client,
            "name": self.config.name,
            "completed_at": datetime.now().isoformat(),
            "stages_run": list(result.keys()),
            "streaming": self._should_stream(),
            "test_mode": self.config.test_mode,
            "total_cost_usd": round(self.analytics.get_total_cost(), 4),
            "output_dir": str(self.output_dir),
            "stage_results": {
                k: {kk: vv for kk, vv in v.items() if kk != 'results'}
                if isinstance(v, dict) else v
                for k, v in result.items()
            },
        }

    def _setup_logger(self) -> logging.Logger:
        """Setup file + console logger."""
        logger = logging.getLogger(f'pipeline.{self.config.name}')
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()

        # File handler
        fh = logging.FileHandler(self.output_dir / "run.log")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(fh)

        # Console handler
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(logging.Formatter('%(message)s'))
        logger.addHandler(ch)

        return logger
