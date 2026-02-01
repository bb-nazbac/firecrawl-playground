"""
Layer 5: Domain Deduplication Implementation

Removes duplicate domains from final CSV, keeping the best result per domain.
"""

import csv
from datetime import datetime
from typing import Dict, Any
from pathlib import Path
from urllib.parse import urlparse
from collections import defaultdict


class DedupeLayer:
    """
    Layer 5: Domain Deduplication

    Removes duplicates by domain, keeping highest confidence result per domain.
    """

    def __init__(self, config, progress, diagnostics, logger, output_dir):
        """
        Initialize dedupe layer

        Args:
            config: RunConfig object
            progress: ProgressTracker instance
            diagnostics: DiagnosticsManager instance
            logger: Logger instance
            output_dir: Output directory path
        """
        self.config = config
        self.progress = progress
        self.diagnostics = diagnostics
        self.logger = logger
        self.output_dir = Path(output_dir)

        # Setup layer diagnostics
        self.layer_diag = self.diagnostics.get_layer("dedupe", 5)

    def run(self) -> Dict[str, Any]:
        """
        Execute dedupe layer

        Returns:
            Dictionary with deduplication metadata
        """
        # Load CSV
        csv_file = self.output_dir / "final_results.csv"
        if not csv_file.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_file}")

        self.logger.info(f"Deduplicating results by domain...")
        self.logger.info("")

        # Start layer
        dedupe_start = datetime.now()

        # Read CSV
        rows = []
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames
            rows = list(reader)

        total_rows = len(rows)
        self.progress.start_layer("l5_dedupe")
        self.layer_diag.set_total_items(total_rows)

        # Group by domain
        domain_groups = defaultdict(list)
        for row in rows:
            domain = self._extract_domain(row['url'])
            domain_groups[domain].append(row)

        # Keep best result per domain
        deduplicated = []
        duplicates_removed = 0

        confidence_order = {'high': 3, 'medium': 2, 'low': 1, 'unknown': 0}

        for domain, group in domain_groups.items():
            if len(group) == 1:
                deduplicated.append(group[0])
            else:
                # Sort by confidence (high > medium > low), then by URL length (shorter is better)
                sorted_group = sorted(
                    group,
                    key=lambda r: (
                        confidence_order.get(r.get('confidence', 'unknown'), 0),
                        -len(r.get('url', ''))
                    ),
                    reverse=True
                )
                deduplicated.append(sorted_group[0])
                duplicates_removed += len(group) - 1

        # Write deduplicated CSV
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(deduplicated)

        # Record success
        duration = (datetime.now() - dedupe_start).total_seconds()
        self.layer_diag.record_success(
            item_id="deduplication",
            duration_seconds=duration,
            metadata={
                "total_rows": total_rows,
                "unique_domains": len(deduplicated),
                "duplicates_removed": duplicates_removed
            }
        )

        # Update progress
        self.progress.update_summary(final_results=len(deduplicated))

        # Complete layer
        self.layer_diag.complete()
        self.progress.complete_layer("l5_dedupe")

        self.logger.info(f"✓ Layer 5 complete: Deduplication finished")
        self.logger.info(f"  Before: {total_rows} rows")
        self.logger.info(f"  After: {len(deduplicated)} rows")
        self.logger.info(f"  Removed: {duplicates_removed} duplicates")
        self.logger.info("")

        return {
            "total_rows": total_rows,
            "unique_rows": len(deduplicated),
            "duplicates_removed": duplicates_removed
        }

    def _extract_domain(self, url: str) -> str:
        """
        Extract normalized domain from URL

        Args:
            url: Full URL

        Returns:
            Normalized domain
        """
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()

            # Remove www. prefix
            if domain.startswith('www.'):
                domain = domain[4:]

            return domain
        except Exception:
            return url.lower()
