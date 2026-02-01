"""
Layer 4: CSV Export Implementation

Exports classified results to CSV with all fields including reasoning and evidence.
"""

import csv
import json
from datetime import datetime
from typing import Dict, Any
from pathlib import Path


class ExportLayer:
    """
    Layer 4: Export to CSV

    Exports all classification results with reasoning and evidence.
    """

    def __init__(self, config, spec, progress, diagnostics, logger, output_dir):
        """
        Initialize export layer

        Args:
            config: RunConfig object
            spec: AnalysisSpec object
            progress: ProgressTracker instance
            diagnostics: DiagnosticsManager instance
            logger: Logger instance
            output_dir: Output directory path
        """
        self.config = config
        self.spec = spec
        self.progress = progress
        self.diagnostics = diagnostics
        self.logger = logger
        self.output_dir = Path(output_dir)

        # Setup layer diagnostics
        self.layer_diag = self.diagnostics.get_layer("export", 4)

    def run(self) -> Dict[str, Any]:
        """
        Execute export layer

        Returns:
            Dictionary with export metadata
        """
        # Load L3 results
        l3_file = self.output_dir / "l3_classified_pages.json"
        if not l3_file.exists():
            raise FileNotFoundError(f"L3 results not found: {l3_file}")

        with open(l3_file, 'r') as f:
            l3_data = json.load(f)

        pages = l3_data['pages']

        self.logger.info(f"Exporting {len(pages)} classified pages to CSV...")
        self.logger.info("")

        # Start layer
        self.progress.start_layer("l4_export")
        export_start = datetime.now()

        # Build CSV headers dynamically from spec
        headers = self._build_headers()

        # Export to CSV
        csv_file = self.output_dir / "final_results.csv"
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()

            for page in pages:
                if page.get('success'):
                    row = self._build_row(page)
                    writer.writerow(row)

        # Record success
        duration = (datetime.now() - export_start).total_seconds()
        self.layer_diag.record_success(
            item_id="csv_export",
            duration_seconds=duration
        )

        # Complete layer
        self.layer_diag.complete()
        self.progress.complete_layer("l4_export")

        self.logger.info(f"✓ Layer 4 complete: Exported to {csv_file}")
        self.logger.info(f"  Rows: {len([p for p in pages if p.get('success')])}")
        self.logger.info(f"  Columns: {len(headers)}")
        self.logger.info("")

        return {
            "csv_file": str(csv_file),
            "rows": len([p for p in pages if p.get('success')]),
            "columns": len(headers)
        }

    def _build_headers(self) -> list:
        """
        Build CSV headers from spec

        Returns:
            List of column names
        """
        headers = [
            'url',
            'classification',
            'confidence',
            'reasoning'
        ]

        # Add extraction fields
        for field_name in self.spec.extraction_fields.keys():
            headers.append(field_name)

        # Add question fields (with answer, reasoning, evidence)
        for question in self.spec.questions:
            headers.append(f"{question.field}_answer")
            if question.reasoning_required:
                headers.append(f"{question.field}_reasoning")
            if question.evidence_required:
                headers.append(f"{question.field}_evidence")

        # Add token fields
        headers.extend(['tokens_input', 'tokens_output'])

        return headers

    def _build_row(self, page: Dict[str, Any]) -> Dict[str, str]:
        """
        Build CSV row from classified page

        Args:
            page: Classified page data

        Returns:
            Dictionary mapping column names to values
        """
        row = {
            'url': page.get('url', ''),
            'classification': page.get('classification', ''),
            'confidence': page.get('confidence', ''),
            'reasoning': page.get('reasoning', '')
        }

        # Add extraction fields
        extracted_data = page.get('extracted_data', {})
        for field_name in self.spec.extraction_fields.keys():
            value = extracted_data.get(field_name, '')
            # Convert lists to comma-separated strings
            if isinstance(value, list):
                value = ', '.join(str(v) for v in value)
            row[field_name] = str(value) if value else ''

        # Add question answers
        questions_data = page.get('questions', {})
        for question in self.spec.questions:
            question_result = questions_data.get(question.field, {})

            # Answer
            answer = question_result.get('answer', '')
            if isinstance(answer, list):
                answer = ', '.join(str(a) for a in answer)
            row[f"{question.field}_answer"] = str(answer) if answer else ''

            # Reasoning (if required)
            if question.reasoning_required:
                row[f"{question.field}_reasoning"] = question_result.get('reasoning', '')

            # Evidence (if required)
            if question.evidence_required:
                row[f"{question.field}_evidence"] = question_result.get('evidence', '')

        # Add token fields
        row['tokens_input'] = str(page.get('tokens_input', 0))
        row['tokens_output'] = str(page.get('tokens_output', 0))

        return row
