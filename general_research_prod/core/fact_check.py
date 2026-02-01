"""
Fact-Check Layer (Perplexity Sonar API)

After dedupe/grouping, sends each unique deal to Perplexity for web-grounded
verification. Returns verified fields + citations alongside original data.
"""

import os
import csv
import json
import asyncio
import time
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import defaultdict
from openai import AsyncOpenAI


# Fields that the fact-check prompt asks Perplexity to verify
FC_OUTPUT_FIELDS = [
    "fc_verified",
    "fc_acquirer_name",
    "fc_target_company_name",
    "fc_deal_value",
    "fc_deal_date",
    "fc_deal_status",
    "fc_ai_vertical",
    "fc_deal_type",
    "fc_corrections",
    "fc_confidence",
    "fc_citations",
]

# Fields we pull from each row to build the verification prompt
DEFAULT_VERIFY_FIELDS = [
    "acquirer_name",
    "target_company_name",
    "deal_value",
    "deal_date",
    "deal_status",
    "ai_vertical",
    "deal_type",
]


def _build_prompt(row: Dict, fields: List[str]) -> str:
    """Build the verification prompt for a single deal."""
    lines = []
    for f in fields:
        val = row.get(f, "")
        if val:
            label = f.replace("_", " ").title()
            lines.append(f"- {label}: {val}")

    deal_desc = "\n".join(lines) if lines else "- (no details extracted)"

    return f"""Verify this M&A transaction using web search. Return JSON only, no markdown.

Claimed deal:
{deal_desc}

Return this exact JSON structure:
{{
  "deal_verified": true or false,
  "acquirer_name": "verified name or null if unknown",
  "target_company_name": "verified name or null if unknown",
  "deal_value": "verified value or null if unknown",
  "deal_date": "verified date or null if unknown",
  "deal_status": "verified status (announced/closed/pending/terminated) or null",
  "ai_vertical": "verified AI sub-field or null",
  "deal_type": "verified type (acquisition/merger/acqui-hire/majority_stake) or null",
  "corrections": "brief note on any discrepancies between claimed and verified data, or empty string if all correct",
  "confidence": "high, medium, or low"
}}"""


def _parse_response(raw_content: str, citations: Optional[List[str]]) -> Dict[str, str]:
    """Parse Perplexity response into flat fc_ prefixed dict."""
    result = {f: "" for f in FC_OUTPUT_FIELDS}

    try:
        data = json.loads(raw_content)
    except (json.JSONDecodeError, TypeError):
        result["fc_corrections"] = f"JSON parse error: {raw_content[:200]}"
        return result

    result["fc_verified"] = str(data.get("deal_verified", "")).lower()
    result["fc_acquirer_name"] = data.get("acquirer_name") or ""
    result["fc_target_company_name"] = data.get("target_company_name") or ""
    result["fc_deal_value"] = data.get("deal_value") or ""
    result["fc_deal_date"] = data.get("deal_date") or ""
    result["fc_deal_status"] = data.get("deal_status") or ""
    result["fc_ai_vertical"] = data.get("ai_vertical") or ""
    result["fc_deal_type"] = data.get("deal_type") or ""
    result["fc_corrections"] = data.get("corrections") or ""
    result["fc_confidence"] = data.get("confidence") or ""

    if citations:
        result["fc_citations"] = " | ".join(citations)

    return result


async def _verify_deal(
    client: AsyncOpenAI,
    row: Dict,
    fields: List[str],
    model: str,
    semaphore: asyncio.Semaphore,
    logger=None,
) -> Dict[str, str]:
    """Send one deal to Perplexity for verification."""
    target = row.get("target_company_name", "unknown")

    async with semaphore:
        try:
            prompt = _build_prompt(row, fields)
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a financial research assistant. Verify M&A deals using web search. Return only valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
            )

            raw_content = response.choices[0].message.content
            citations = getattr(response, "citations", None)

            result = _parse_response(raw_content, citations)

            if logger:
                verified = result.get("fc_verified", "?")
                logger.info(f"  Fact-check: {target} → verified={verified}")

            return result

        except Exception as e:
            if logger:
                logger.warning(f"  Fact-check FAILED for {target}: {e}")
            result = {f: "" for f in FC_OUTPUT_FIELDS}
            result["fc_corrections"] = f"API error: {str(e)[:200]}"
            return result


async def _run_fact_checks(
    deals: List[Dict],
    fields: List[str],
    model: str,
    concurrency: int,
    logger=None,
) -> List[Dict[str, str]]:
    """Run all fact-checks concurrently with rate limiting."""
    api_key = os.environ.get("PERPLEXITY_API_KEY")
    if not api_key:
        raise ValueError("PERPLEXITY_API_KEY not set in environment")

    client = AsyncOpenAI(
        api_key=api_key,
        base_url="https://api.perplexity.ai",
    )

    semaphore = asyncio.Semaphore(concurrency)

    tasks = [
        _verify_deal(client, deal, fields, model, semaphore, logger)
        for deal in deals
    ]

    results = await asyncio.gather(*tasks)
    return list(results)


def fact_check_deals(
    input_csv: Path,
    output_csv: Path,
    config,  # FactCheckConfig
    key_field: str = "target_company_name",
    logger=None,
) -> Dict[str, Any]:
    """
    Fact-check unique deals from deduped/grouped CSV via Perplexity.

    For grouped CSVs (multiple rows per deal), only the best row per deal key
    is sent to Perplexity. The verified data is then attached to ALL rows
    sharing that key.

    Args:
        input_csv: Path to deduped results CSV (4_deduped_results.csv)
        output_csv: Path to write fact-checked CSV (5_factchecked_results.csv)
        config: FactCheckConfig with model, concurrency, fields_to_verify
        key_field: Column to group deals by
        logger: Optional logger

    Returns:
        Dict with stats
    """
    def log(msg):
        if logger:
            logger.info(msg)

    start_time = time.time()

    # Read all rows
    rows = []
    with open(input_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        for row in reader:
            rows.append(row)

    total_input = len(rows)

    # Separate DEAL_FOUND rows from others
    deal_rows = [r for r in rows if r.get("classification") == "DEAL_FOUND"]
    other_rows = [r for r in rows if r.get("classification") != "DEAL_FOUND"]

    log(f"Fact-check: {len(deal_rows)} DEAL_FOUND rows, {len(other_rows)} other rows")

    # Group DEAL_FOUND rows by key to find unique deals
    groups = defaultdict(list)
    no_key_deals = []
    for row in deal_rows:
        key = (row.get(key_field) or "").strip().lower()
        if key:
            groups[key].append(row)
        else:
            no_key_deals.append(row)

    log(f"  Unique deal keys: {len(groups)}")
    log(f"  No-key deal rows: {len(no_key_deals)}")

    # Pick best representative row per group for fact-checking
    from core.dedupe import _substantive_score

    representatives = {}
    for key, group_rows in groups.items():
        best = max(group_rows, key=_substantive_score)
        representatives[key] = best

    deals_to_check = list(representatives.values())
    log(f"  Sending {len(deals_to_check)} unique deals to Perplexity ({config.model})...")

    # Run fact-checks
    fields = config.fields_to_verify or DEFAULT_VERIFY_FIELDS

    fc_results = asyncio.run(
        _run_fact_checks(
            deals=deals_to_check,
            fields=fields,
            model=config.model,
            concurrency=config.concurrency,
            logger=logger,
        )
    )

    # Map results back to deal keys
    fc_by_key = {}
    for deal_row, fc_data in zip(deals_to_check, fc_results):
        key = (deal_row.get(key_field) or "").strip().lower()
        fc_by_key[key] = fc_data

    # Attach fact-check columns to all rows
    output_fieldnames = fieldnames + FC_OUTPUT_FIELDS

    for row in rows:
        key = (row.get(key_field) or "").strip().lower()
        if row.get("classification") == "DEAL_FOUND" and key in fc_by_key:
            row.update(fc_by_key[key])
        else:
            # Non-deal rows or no-key deals: empty fc columns
            for f in FC_OUTPUT_FIELDS:
                row[f] = ""

    # Write output
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=output_fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    elapsed = time.time() - start_time

    # Stats
    verified_count = sum(1 for k, v in fc_by_key.items() if v.get("fc_verified") == "true")
    not_verified = sum(1 for k, v in fc_by_key.items() if v.get("fc_verified") == "false")
    errors = sum(1 for k, v in fc_by_key.items() if "error" in v.get("fc_corrections", "").lower())

    stats = {
        "total_deals_checked": len(deals_to_check),
        "verified": verified_count,
        "not_verified": not_verified,
        "errors": errors,
        "elapsed_seconds": round(elapsed, 1),
    }

    log(f"Fact-check complete in {elapsed:.1f}s")
    log(f"  Verified: {verified_count}/{len(deals_to_check)}")
    log(f"  Not verified: {not_verified}")
    log(f"  Errors: {errors}")
    log(f"  Output: {output_csv}")

    return stats
