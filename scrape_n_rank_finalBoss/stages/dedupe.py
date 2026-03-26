import csv
import json
from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict
from stages.base import BaseStage


class DedupeStage(BaseStage):
    STAGE_NAME = "dedupe"

    def run(self, input_data) -> Dict[str, Any]:
        """
        input_data: dict with 'results_csv' path
        """
        # Get input CSV path
        input_csv = None
        if isinstance(input_data, dict):
            input_csv = input_data.get('results_csv', '')

        if not input_csv:
            input_csv = str(self.output.output_dir / "results.csv")

        input_path = Path(input_csv)
        if not input_path.exists():
            self.logger.warning(f"Dedupe: Input CSV not found: {input_csv}")
            return {"deduped_csv": ""}

        output_path = self.output.output_dir / "deduped_results.csv"

        key_field = self.config.get('key_field', 'domain')
        mode = self.config.get('mode', 'dedupe')

        self.analytics.start_stage("dedupe")

        stats = self._dedupe(input_path, output_path, key_field, mode)

        self.analytics.complete_stage("dedupe")

        self.logger.info(f"Dedupe complete: {stats['total_input']} -> {stats['total_output']} ({stats['duplicates_removed']} duplicates removed)")

        return {"deduped_csv": str(output_path), "stats": stats}

    def _dedupe(self, input_csv, output_csv, key_field, mode) -> dict:
        """Core deduplication logic."""
        rows = []
        with open(input_csv, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            for row in reader:
                rows.append(row)

        total_input = len(rows)

        # Group by key
        groups = defaultdict(list)
        no_key_rows = []

        for row in rows:
            key_value = self._extract_key(row, key_field)
            if key_value:
                groups[key_value.lower().strip()].append(row)
            else:
                no_key_rows.append(row)

        if mode == "group":
            output_rows = []
            for key, group_rows in sorted(groups.items()):
                sorted_group = sorted(group_rows, key=self._substantive_score, reverse=True)
                output_rows.extend(sorted_group)
            output_rows.extend(no_key_rows)
            duplicates_removed = 0
        else:
            output_rows = []
            for key, group_rows in groups.items():
                best = max(group_rows, key=self._substantive_score)
                output_rows.append(best)
            output_rows.extend(no_key_rows)
            duplicates_removed = total_input - len(output_rows)

        with open(output_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(output_rows)

        return {
            "total_input": total_input,
            "unique_keys": len(groups),
            "no_key_rows": len(no_key_rows),
            "total_output": len(output_rows),
            "duplicates_removed": duplicates_removed,
        }

    @staticmethod
    def _extract_key(row, key_field):
        if key_field in row and row[key_field]:
            return row[key_field]
        answers_raw = row.get('answers', '')
        if answers_raw:
            try:
                answers = json.loads(answers_raw) if isinstance(answers_raw, str) else answers_raw
                if isinstance(answers, dict) and key_field in answers:
                    return str(answers[key_field])
            except (json.JSONDecodeError, TypeError):
                pass
        return ''

    _FILLER = {'undisclosed', 'unknown', 'n/a', 'na', 'none', 'not stated', 'not disclosed', ''}

    @classmethod
    def _substantive_score(cls, row):
        return sum(1 for v in row.values() if str(v).strip().lower() not in cls._FILLER)
