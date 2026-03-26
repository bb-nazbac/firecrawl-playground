"""
Output Manager

Manages output directory structure and incremental file writes.
Handles CSV, JSONL, JSON output with thread-safe operations.
Ensures data is written incrementally (not buffered until end).
"""

import csv
import json
import threading
from pathlib import Path
from datetime import datetime
from typing import List, Optional


class OutputManager:
    """
    Manages output directory and incremental file writes for pipeline runs.

    Creates and manages:
    - results.csv: Main results file with incremental appends
    - results.jsonl: JSON Lines file with full result objects
    - domains.csv: Domain list from search stage
    - {stage_name}_output.{format}: Intermediate stage outputs
    - summary.json: Final run summary
    - config_snapshot.json: Reproducibility snapshot
    """

    def __init__(self, output_dir: Path, spec=None):
        """
        Initialize output manager.

        Args:
            output_dir: Base output directory for this run
            spec: Optional AnalysisSpec for deriving field names
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._csv_lock = threading.Lock()
        self._jsonl_lock = threading.Lock()
        self._csv_initialized = False
        self._csv_fieldnames = []
        self._spec = spec

        # Standard file paths
        self.results_csv_path = self.output_dir / "results.csv"
        self.results_jsonl_path = self.output_dir / "results.jsonl"
        self.domains_csv_path = self.output_dir / "domains.csv"
        self.summary_path = self.output_dir / "summary.json"

    def init_results_csv(self, fieldnames: list):
        """
        Initialize results.csv with a header row.

        Args:
            fieldnames: List of column names for the CSV header
        """
        with self._csv_lock:
            self._csv_fieldnames = list(fieldnames)
            with open(self.results_csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=self._csv_fieldnames, extrasaction='ignore')
                writer.writeheader()
            self._csv_initialized = True

    def append_result(self, result: dict):
        """
        Thread-safe append a single result to both results.csv and results.jsonl.

        If CSV has not been initialized via init_results_csv(), the first call
        will auto-initialize using the keys of the result dict.

        Args:
            result: Dictionary containing result data
        """
        # Auto-initialize CSV if needed
        if not self._csv_initialized:
            self.init_results_csv(list(result.keys()))

        # Append to CSV
        with self._csv_lock:
            with open(self.results_csv_path, 'a', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=self._csv_fieldnames,
                    extrasaction='ignore',
                )
                # Flatten nested dicts for CSV
                flat_result = self._flatten_for_csv(result)
                writer.writerow(flat_result)

        # Append to JSONL
        with self._jsonl_lock:
            with open(self.results_jsonl_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(result, default=str) + '\n')

    def save_stage_output(self, stage_name: str, data, format: str = 'json'):
        """
        Save intermediate stage output.

        Args:
            stage_name: Name of the stage (e.g. "search", "qualify")
            data: Data to save (dict/list for json, list of dicts for csv)
            format: Output format - 'json', 'jsonl', or 'csv'
        """
        if format == 'json':
            output_path = self.output_dir / f"{stage_name}_output.json"
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, default=str)

        elif format == 'jsonl':
            output_path = self.output_dir / f"{stage_name}_output.jsonl"
            with open(output_path, 'w', encoding='utf-8') as f:
                if isinstance(data, list):
                    for item in data:
                        f.write(json.dumps(item, default=str) + '\n')
                else:
                    f.write(json.dumps(data, default=str) + '\n')

        elif format == 'csv':
            output_path = self.output_dir / f"{stage_name}_output.csv"
            if isinstance(data, list) and data:
                fieldnames = list(data[0].keys()) if isinstance(data[0], dict) else []
                with open(output_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
                    writer.writeheader()
                    for row in data:
                        if isinstance(row, dict):
                            writer.writerow(row)

    def save_domains_csv(self, domains: list):
        """
        Save domains.csv from search stage output.

        Args:
            domains: List of domain dicts, each should have at minimum a 'domain' key.
                     May also have: url, title, snippet, city, query, position
        """
        if not domains:
            return

        # Determine fieldnames from first item
        if isinstance(domains[0], dict):
            fieldnames = list(domains[0].keys())
        else:
            # Plain list of domain strings
            fieldnames = ['domain']
            domains = [{'domain': d} for d in domains]

        with open(self.domains_csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(domains)

    def write_summary(self, summary: dict):
        """
        Write final summary.json with run metadata and results.

        Args:
            summary: Dictionary containing run summary data
        """
        summary['written_at'] = datetime.now().isoformat()
        with open(self.summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, default=str)

    def save_config_snapshot(self, config_data: dict):
        """
        Save a config snapshot for reproducibility.

        Args:
            config_data: Configuration dictionary to save
        """
        snapshot_path = self.output_dir / "config_snapshot.json"
        snapshot = {
            "saved_at": datetime.now().isoformat(),
            "config": config_data,
        }
        with open(snapshot_path, 'w', encoding='utf-8') as f:
            json.dump(snapshot, f, indent=2, default=str)

    def _flatten_for_csv(self, data: dict) -> dict:
        """
        Flatten a nested dictionary for CSV output.

        Nested dicts become key.subkey format.
        Lists become JSON strings.

        Args:
            data: Nested dictionary

        Returns:
            Flat dictionary suitable for CSV writing
        """
        flat = {}
        for key, value in data.items():
            if isinstance(value, dict):
                for subkey, subval in value.items():
                    flat_key = f"{key}.{subkey}"
                    if flat_key in self._csv_fieldnames:
                        flat[flat_key] = subval
                    elif key in self._csv_fieldnames:
                        # If the parent key is in fieldnames, serialize as JSON
                        flat[key] = json.dumps(value, default=str)
                        break
                else:
                    # If no sub-keys matched and parent isn't in fieldnames, serialize
                    if key in self._csv_fieldnames:
                        flat[key] = json.dumps(value, default=str)
            elif isinstance(value, (list, tuple)):
                flat[key] = json.dumps(value, default=str)
            else:
                flat[key] = value

        return flat

    def load_results_jsonl(self) -> List[dict]:
        """
        Load all results from the JSONL file.

        Returns:
            List of result dictionaries
        """
        results = []
        if self.results_jsonl_path.exists():
            with open(self.results_jsonl_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            results.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        return results

    def get_output_dir(self) -> Path:
        """Get the output directory path."""
        return self.output_dir
