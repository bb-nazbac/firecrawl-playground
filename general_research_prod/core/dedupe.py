"""
Deduplication Layer

Groups qualifying results by a key field and keeps the best record per group.
"Best" = most extraction fields filled, then highest confidence.
"""

import csv
import json
from pathlib import Path
from typing import List, Dict, Any
from collections import defaultdict


def dedupe_results(
    input_csv: Path,
    output_csv: Path,
    key_field: str,
    mode: str = "dedupe",
    logger=None,
) -> Dict[str, Any]:
    """
    Deduplicate or group qualifying results by key_field.

    Args:
        input_csv: Path to qualifying results CSV
        output_csv: Path to write output CSV
        key_field: Column name to group on (e.g., 'target_company_name')
        mode: "dedupe" = keep best row per key, "group" = keep all rows sorted by key
        logger: Optional logger

    Returns:
        Dict with stats
    """
    def log(msg):
        if logger:
            logger.info(msg)

    # Read all rows
    rows = []
    with open(input_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            rows.append(row)

    total_input = len(rows)
    log(f"Dedupe: {total_input} rows, grouping by '{key_field}' (mode={mode})")

    # Check if key_field exists
    if fieldnames and key_field not in fieldnames:
        log(f"Warning: '{key_field}' not a direct column. Will check 'answers' JSON field.")

    # Group by key
    groups = defaultdict(list)
    no_key_rows = []

    for row in rows:
        key_value = _extract_key(row, key_field)
        if key_value:
            groups[key_value.lower().strip()].append(row)
        else:
            no_key_rows.append(row)

    if mode == "group":
        # Keep ALL rows, sorted by key so same-deal rows are adjacent
        # Best row per group comes first within each group
        output_rows = []
        for key, group_rows in sorted(groups.items()):
            sorted_group = sorted(group_rows, key=_substantive_score, reverse=True)
            output_rows.extend(sorted_group)
        output_rows.extend(no_key_rows)
        duplicates_removed = 0
    else:
        # Classic dedupe: keep best row per key
        output_rows = []
        for key, group_rows in groups.items():
            best = _pick_best(group_rows)
            output_rows.append(best)
        output_rows.extend(no_key_rows)
        duplicates_removed = total_input - len(output_rows)

    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    log(f"Dedupe complete: {len(output_rows)} output records ({duplicates_removed} duplicates removed)")
    log(f"  Unique keys: {len(groups)}")
    log(f"  No-key rows (kept as-is): {len(no_key_rows)}")

    return {
        "total_input": total_input,
        "unique_keys": len(groups),
        "no_key_rows": len(no_key_rows),
        "total_output": len(output_rows),
        "duplicates_removed": duplicates_removed,
    }


def _extract_key(row: Dict, key_field: str) -> str:
    """Extract key value from a row. Checks direct columns first, then 'answers' JSON."""
    # Direct column
    if key_field in row and row[key_field]:
        return row[key_field]

    # Check inside answers JSON (qualifying system stores answers as JSON string)
    answers_raw = row.get('answers', '')
    if answers_raw:
        try:
            answers = json.loads(answers_raw) if isinstance(answers_raw, str) else answers_raw
            if isinstance(answers, dict) and key_field in answers:
                return str(answers[key_field])
        except (json.JSONDecodeError, TypeError):
            pass

    return ''


_FILLER_VALUES = {
    'undisclosed', 'unknown', 'n/a', 'na', 'none', 'not stated',
    'not disclosed', 'not available', 'various', 'multiple', '',
}


def _substantive_score(row: Dict) -> int:
    """Score a row by number of fields with substantive (non-filler) values."""
    total = 0
    for v in row.values():
        s = str(v).strip().lower() if v else ''
        if s and s not in _FILLER_VALUES:
            total += 1
    return total


def _pick_best(rows: List[Dict]) -> Dict:
    """Pick the best row from a group of duplicates."""
    if len(rows) == 1:
        return rows[0]
    return max(rows, key=_substantive_score)
