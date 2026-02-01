#!/usr/bin/env python3
"""
Round 06: Production Pipeline Orchestrator
Runs L1 → L2 → L3 → L4 with client-specific configuration

Usage:
    python3 main.py --client=fuse --spec=spec_v2_hospital_university

Optional:
    --skip-l1    Skip L1 (search) if already done
    --skip-l2    Skip L2 (scrape) if already done
    --skip-l3    Skip L3 (classify) if already done
    --skip-l4    Skip L4 (export) if already done
"""

import argparse
import subprocess
import sys
import os
from datetime import datetime
from pathlib import Path


class PipelineOrchestrator:
    def __init__(self, client, spec, skip_layers=None):
        self.client = client
        self.spec = spec
        self.skip_layers = skip_layers or []
        self.run_id = datetime.now().strftime('%Y%m%d_%H%M%S')

        # Create unified pipeline log
        self.log_file = f'logs/pipeline_runs/run_{client}_{self.run_id}.log'
        Path('logs/pipeline_runs').mkdir(parents=True, exist_ok=True)

        with open(self.log_file, 'w') as f:
            f.write("=" * 70 + "\n")
            f.write("ROUND 06: PRODUCTION PIPELINE ORCHESTRATOR\n")
            f.write("=" * 70 + "\n")
            f.write(f"RUN ID: {self.run_id}\n")
            f.write(f"CLIENT: {client}\n")
            f.write(f"SPEC: {spec}\n")
            f.write(f"STARTED: {datetime.now().isoformat()}\n")
            if self.skip_layers:
                f.write(f"SKIPPING LAYERS: {', '.join(self.skip_layers)}\n")
            f.write("=" * 70 + "\n\n")
            f.flush()

    def log(self, message):
        """Write to unified pipeline log and console"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_line = f"[{timestamp}] {message}\n"

        with open(self.log_file, 'a') as f:
            f.write(log_line)
            f.flush()

        print(message, flush=True)

    def run_layer(self, layer_id, layer_name, script_path, args=None):
        """Run a layer script with error handling"""

        if layer_id in self.skip_layers:
            self.log(f"⏭️  SKIPPING LAYER: {layer_name}")
            self.log("")
            return True

        self.log("=" * 70)
        self.log(f"LAYER: {layer_name}")
        self.log("=" * 70)

        # Build command
        cmd = ['python3', script_path]
        if args:
            cmd.extend(args)

        self.log(f"Command: {' '.join(cmd)}")
        self.log("")

        # Change to script directory
        script_dir = os.path.dirname(script_path)
        original_dir = os.getcwd()

        if script_dir:
            os.chdir(script_dir)
            self.log(f"Working directory: {os.getcwd()}")
            self.log("")

        # Run the script
        try:
            result = subprocess.run(
                cmd if not script_dir else [cmd[0], os.path.basename(cmd[1])] + cmd[2:],
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour timeout
            )

            # Log output
            if result.stdout:
                for line in result.stdout.split('\n'):
                    if line.strip():
                        self.log(f"  {line}")

            # Check for errors
            if result.returncode != 0:
                self.log("")
                self.log(f"❌ LAYER FAILED: {layer_name}")
                self.log(f"Return code: {result.returncode}")
                if result.stderr:
                    self.log("STDERR:")
                    for line in result.stderr.split('\n'):
                        if line.strip():
                            self.log(f"  {line}")
                return False

            self.log("")
            self.log(f"✅ LAYER COMPLETE: {layer_name}")
            self.log("")
            return True

        except subprocess.TimeoutExpired:
            self.log(f"❌ LAYER TIMEOUT: {layer_name} (exceeded 1 hour)")
            return False

        except Exception as e:
            self.log(f"❌ LAYER ERROR: {layer_name}")
            self.log(f"Exception: {str(e)}")
            return False

        finally:
            if script_dir:
                os.chdir(original_dir)

    def run_pipeline(self):
        """Execute full L1→L2→L3→L4 pipeline"""

        self.log("=" * 70)
        self.log("PIPELINE EXECUTION START")
        self.log("=" * 70)
        self.log(f"Client: {self.client}")
        self.log(f"Spec: {self.spec}")
        self.log("=" * 70)
        self.log("")

        # Note: L1 and L2 don't need client parameter (they're source-agnostic)
        # Only L3 and L4 are client-aware

        # L1: Search (currently manual - would need to be updated for automation)
        if 'l1' not in self.skip_layers:
            self.log("⚠️  L1 (Search) - Currently requires manual execution")
            self.log("    Run: cd l1_serpapi_search && python3 search_batch.py")
            self.log("    Skipping L1 for now. Use --skip-l1 to acknowledge.")
            self.log("")

        # L2: Scrape (currently manual - would need to be updated for automation)
        if 'l2' not in self.skip_layers:
            self.log("⚠️  L2 (Scrape) - Currently requires manual execution")
            self.log("    Run: cd l2_firecrawl_scrape && python3 scrape_batch_logged.py")
            self.log("    Skipping L2 for now. Use --skip-l2 to acknowledge.")
            self.log("")

        # L3: Classify with client spec
        if not self.run_layer(
            'l3',
            'L3 - LLM Classification',
            'l3_llm_classify/classify_with_spec.py',
            ['--client', self.client, '--spec', self.spec]
        ):
            return False

        # L4: Export with client filter
        if not self.run_layer(
            'l4',
            'L4 - CSV Export (Independent Clinics)',
            'l4_csv_export/export_with_client.py',
            ['--client', self.client, '--filter', 'independent']
        ):
            return False

        self.log("=" * 70)
        self.log("✅ PIPELINE COMPLETE")
        self.log("=" * 70)
        self.log(f"Run ID: {self.run_id}")
        self.log(f"Client: {self.client}")
        self.log(f"Log file: {self.log_file}")
        self.log("")
        self.log(f"Output locations:")
        self.log(f"  L3: l3_llm_classify/outputs/{self.client}/")
        self.log(f"  L4: l4_csv_export/outputs/{self.client}/")
        self.log("=" * 70)

        return True


def main():
    parser = argparse.ArgumentParser(
        description='Round 06 Pipeline Orchestrator: L1→L2→L3→L4',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run L3→L4 for Fuse client (assuming L1/L2 already done)
  python3 main.py --client=fuse --spec=spec_v2_hospital_university --skip-l1 --skip-l2

  # Run full pipeline
  python3 main.py --client=fuse --spec=spec_v2_hospital_university
        """
    )

    parser.add_argument('--client', required=True,
                       help='Client name (e.g., fuse)')
    parser.add_argument('--spec', required=True,
                       help='L3 spec name (e.g., spec_v2_hospital_university)')
    parser.add_argument('--skip-l1', action='store_true',
                       help='Skip L1 (search layer)')
    parser.add_argument('--skip-l2', action='store_true',
                       help='Skip L2 (scrape layer)')
    parser.add_argument('--skip-l3', action='store_true',
                       help='Skip L3 (classify layer)')
    parser.add_argument('--skip-l4', action='store_true',
                       help='Skip L4 (export layer)')

    args = parser.parse_args()

    # Build skip list
    skip_layers = []
    if args.skip_l1:
        skip_layers.append('l1')
    if args.skip_l2:
        skip_layers.append('l2')
    if args.skip_l3:
        skip_layers.append('l3')
    if args.skip_l4:
        skip_layers.append('l4')

    # Create orchestrator
    orchestrator = PipelineOrchestrator(
        client=args.client,
        spec=args.spec,
        skip_layers=skip_layers
    )

    # Run pipeline
    success = orchestrator.run_pipeline()

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
