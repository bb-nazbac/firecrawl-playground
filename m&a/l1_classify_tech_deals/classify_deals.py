#!/usr/bin/env python3
"""
classify_deals.py — LLM-based technology deal classifier
=========================================================
L1 Independent Script | m&a pipeline

Reads full_data.csv (411K M&A deals), sends batches to gpt-5-mini,
classifies each target company as technology-related or not.

This is a WIDE NET filter — catches all tech companies (software,
hardware, biotech, fintech, etc.) so that downstream research
can determine more specific categories like AI/ML.

Usage:
    python classify_deals.py                        # Full run (all 411K rows)
    python classify_deals.py --test 10000           # Test on first 10K rows
    python classify_deals.py --test 10000 --resume  # Resume test run
    python classify_deals.py --resume               # Resume from checkpoint
    python classify_deals.py --merge-only           # Skip classify, just merge
"""

import os
import sys
import csv
import json
import asyncio
import time
import argparse
import logging
from pathlib import Path
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent.parent / ".env")
except ImportError:
    pass

from openai import AsyncOpenAI

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════

BATCH_SIZE = 10
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_CONCURRENCY = 15
MAX_RETRIES = 3
RETRY_DELAY_BASE = 2  # seconds, exponential backoff

PROJECT_ROOT = Path(__file__).parent.parent  # m&a/
INPUT_CSV = PROJECT_ROOT / "full_data.csv"
OUTPUT_DIR = PROJECT_ROOT / "outputs"
LOG_DIR = PROJECT_ROOT / "logs" / "l1_classify_tech_deals"
CHECKPOINT_DIR = OUTPUT_DIR / ".checkpoints"

# Columns sent to LLM for classification
CLASSIFY_COLS = [
    "Target Full Name",
    "Target Primary SIC",
    "Target Mid Industry",
    "Target Macro Industry",
]

# ═══════════════════════════════════════════════════════════════
# PROMPTS
# ═══════════════════════════════════════════════════════════════

SYSTEM_PROMPT = (
    "You are a financial analyst classifying M&A target companies as technology "
    "companies or not. Cast a WIDE NET — if there is reasonable evidence the "
    "company is in a technology-related field, classify it as tech.\n\n"
    "TECHNOLOGY COMPANY includes:\n"
    "- Software (SaaS, enterprise, consumer, mobile apps, games with tech core)\n"
    "- Hardware (semiconductors, electronics, devices, chips, sensors)\n"
    "- Internet & online platforms (e-commerce tech, social media, ad tech)\n"
    "- IT services & consulting (systems integrators, managed services)\n"
    "- Telecommunications & networking\n"
    "- Biotech & life sciences technology\n"
    "- Healthcare technology (health IT, medical devices with tech core)\n"
    "- Fintech (payments, trading platforms, insurtech)\n"
    "- Cybersecurity & data privacy\n"
    "- AI, ML, robotics, automation\n"
    "- Clean tech & energy technology\n"
    "- Aerospace & defense technology\n"
    "- Data analytics & business intelligence\n\n"
    "NOT TECHNOLOGY:\n"
    "- Traditional manufacturing (steel, chemicals, food processing)\n"
    "- Real estate, construction, property management\n"
    "- Mining, oil & gas extraction (unless tech-focused)\n"
    "- Retail & consumer goods (unless tech platform)\n"
    "- Banks, insurance, asset management (unless fintech)\n"
    "- Hospitals, clinics, pharma manufacturing (unless health IT)\n"
    "- Agriculture, forestry, fishing\n"
    "- Transportation & logistics (unless tech platform)\n"
    "- Restaurants, hospitality, entertainment (unless tech platform)\n\n"
    "When in doubt, lean toward classifying as tech. We prefer false positives "
    "over false negatives.\n\n"
    "Respond ONLY with a valid JSON object. No markdown, no explanation."
)


def build_batch_prompt(rows):
    """Build classification prompt for a batch of rows."""
    lines = []
    for i, row in enumerate(rows, 1):
        name = row.get("Target Full Name") or "Unknown"
        sic = row.get("Target Primary SIC") or ""
        mid = row.get("Target Mid Industry") or ""
        macro = row.get("Target Macro Industry") or ""
        parts = [f'{i}. "{name}"']
        if sic:
            parts.append(f"SIC: {sic}")
        if mid:
            parts.append(f"Industry: {mid}")
        if macro:
            parts.append(f"Macro: {macro}")
        lines.append(" | ".join(parts))

    return (
        "Classify each company — is it a TECHNOLOGY company?\n\n"
        + "\n".join(lines)
        + '\n\nReturn JSON: {"results": [{"idx": 1, "is_tech": true/false, '
        '"tech_category": "category or null", "confidence": "high/medium/low"}, ...]}'
    )


def parse_llm_response(content, expected_count):
    """Parse LLM JSON response into list of classification dicts."""
    text = content.strip()

    # Strip markdown fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return [{"is_tech": None, "tech_category": "", "confidence": "parse_error"}] * expected_count

    # Handle both {"results": [...]} and bare [...]
    if isinstance(data, dict) and "results" in data:
        items = data["results"]
    elif isinstance(data, list):
        items = data
    else:
        return [{"is_tech": None, "tech_category": "", "confidence": "parse_error"}] * expected_count

    results = []
    for item in items:
        is_tech = item.get("is_tech")
        if isinstance(is_tech, str):
            is_tech = is_tech.lower() in ("true", "yes", "1")
        results.append({
            "is_tech": bool(is_tech) if is_tech is not None else None,
            "tech_category": item.get("tech_category") or "",
            "confidence": item.get("confidence", "unknown"),
        })

    # Pad if fewer results than expected
    while len(results) < expected_count:
        results.append({"is_tech": None, "tech_category": "", "confidence": "missing"})

    return results[:expected_count]


# ═══════════════════════════════════════════════════════════════
# CORE ASYNC CLASSIFICATION
# ═══════════════════════════════════════════════════════════════

async def classify_batch(client, batch, semaphore, model, stats, logger):
    """Classify a single batch of rows via LLM."""
    async with semaphore:
        prompt = build_batch_prompt(batch)
        for attempt in range(MAX_RETRIES):
            try:
                resp = await client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0,
                    response_format={"type": "json_object"},
                )
                stats["api_calls"] += 1
                if resp.usage:
                    stats["input_tokens"] += resp.usage.prompt_tokens
                    stats["output_tokens"] += resp.usage.completion_tokens
                content = resp.choices[0].message.content
                return parse_llm_response(content, len(batch))
            except Exception as e:
                stats["retries"] += 1
                err_str = str(e)
                if "rate_limit" in err_str.lower() or "429" in err_str:
                    delay = RETRY_DELAY_BASE * (2 ** attempt) + 5
                    logger.warning(f"Rate limited, waiting {delay}s...")
                    await asyncio.sleep(delay)
                elif attempt < MAX_RETRIES - 1:
                    delay = RETRY_DELAY_BASE * (2 ** attempt)
                    logger.warning(f"Batch error (attempt {attempt + 1}): {e}, retry in {delay}s")
                    await asyncio.sleep(delay)
                else:
                    stats["errors"] += 1
                    logger.error(f"Batch FAILED after {MAX_RETRIES} attempts: {e}")
                    return [{"is_tech": None, "tech_category": "", "confidence": "api_error"}] * len(batch)


async def run_classification(rows, checkpoint_file, model, concurrency, args, logger):
    """Run async classification across all rows."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY not set. Add it to .env or export it.")
        sys.exit(1)

    client = AsyncOpenAI(api_key=api_key)
    semaphore = asyncio.Semaphore(concurrency)
    checkpoint_lock = asyncio.Lock()

    # Load existing checkpoint for resume
    completed_indices = set()
    if args.resume and checkpoint_file.exists():
        with open(checkpoint_file, "r") as f:
            for line in f:
                if line.strip():
                    entry = json.loads(line)
                    completed_indices.add(entry["idx"])
        logger.info(f"Resume: {len(completed_indices):,} rows already classified")
    elif not args.resume and checkpoint_file.exists():
        checkpoint_file.unlink()
        logger.info("Cleared old checkpoint (fresh run)")

    # Filter to remaining rows
    remaining = [r for r in rows if r["idx"] not in completed_indices]
    if not remaining:
        logger.info("All rows already classified.")
        return {"api_calls": 0, "input_tokens": 0, "output_tokens": 0,
                "retries": 0, "errors": 0, "tech_found": 0}

    logger.info(f"Rows to classify: {len(remaining):,}")

    # Create batches
    batches = [remaining[i:i + BATCH_SIZE] for i in range(0, len(remaining), BATCH_SIZE)]
    total_batches = len(batches)
    logger.info(f"Batches: {total_batches:,} (size={BATCH_SIZE}, concurrency={concurrency})")

    stats = {
        "api_calls": 0, "input_tokens": 0, "output_tokens": 0,
        "retries": 0, "errors": 0, "tech_found": 0, "completed_batches": 0,
    }
    start_time = time.time()

    async def process_batch(batch):
        results = await classify_batch(client, batch, semaphore, model, stats, logger)

        async with checkpoint_lock:
            with open(checkpoint_file, "a") as f:
                for row, result in zip(batch, results):
                    entry = {
                        "idx": row["idx"],
                        "target_name": row["Target Full Name"],
                        **result,
                    }
                    f.write(json.dumps(entry) + "\n")
                    if result.get("is_tech"):
                        stats["tech_found"] += 1

            stats["completed_batches"] += 1
            cb = stats["completed_batches"]
            if cb % 100 == 0 or cb == total_batches:
                elapsed = time.time() - start_time
                rate = cb / elapsed if elapsed > 0 else 0
                eta = (total_batches - cb) / rate if rate > 0 else 0
                pct = cb / total_batches * 100
                logger.info(
                    f"  [{pct:5.1f}%] {cb:,}/{total_batches:,} batches | "
                    f"Tech: {stats['tech_found']:,} | Err: {stats['errors']} | "
                    f"{rate:.1f} b/s | ETA: {eta:.0f}s"
                )

    tasks = [process_batch(b) for b in batches]
    await asyncio.gather(*tasks)

    elapsed = time.time() - start_time
    cost_in = stats["input_tokens"] * 0.15 / 1_000_000
    cost_out = stats["output_tokens"] * 0.60 / 1_000_000
    total_cost = cost_in + cost_out

    logger.info("")
    logger.info("=" * 60)
    logger.info("CLASSIFICATION COMPLETE")
    logger.info("=" * 60)
    logger.info(f"  Duration:      {elapsed:.1f}s ({elapsed/60:.1f}m)")
    logger.info(f"  API calls:     {stats['api_calls']:,}")
    logger.info(f"  Tokens:        {stats['input_tokens']:,} in / {stats['output_tokens']:,} out")
    logger.info(f"  Cost estimate: ${total_cost:.2f} (${cost_in:.2f} in + ${cost_out:.2f} out)")
    logger.info(f"  Tech found:    {stats['tech_found']:,}")
    logger.info(f"  Errors:        {stats['errors']}")
    logger.info(f"  Retries:       {stats['retries']}")
    logger.info("=" * 60)

    return stats


# ═══════════════════════════════════════════════════════════════
# MERGE: Combine checkpoint with full CSV
# ═══════════════════════════════════════════════════════════════

def merge_results(checkpoint_file, test_limit, logger):
    """Stream-read full_data.csv + checkpoint results -> output CSVs."""
    logger.info("Loading checkpoint results...")
    classifications = {}
    with open(checkpoint_file, "r") as f:
        for line in f:
            if line.strip():
                entry = json.loads(line)
                classifications[entry["idx"]] = entry
    logger.info(f"Loaded {len(classifications):,} classifications")

    suffix = "_test" if test_limit else ""
    all_out = OUTPUT_DIR / f"all_deals_classified{suffix}.csv"
    tech_out = OUTPUT_DIR / f"tech_deals_only{suffix}.csv"
    stats_out = OUTPUT_DIR / f"classify_stats{suffix}.json"

    tech_count = 0
    not_tech_count = 0
    error_count = 0
    total = 0

    logger.info(f"Merging with {INPUT_CSV.name} -> output CSVs...")

    with open(INPUT_CSV, "r") as fin:
        reader = csv.DictReader(fin)
        out_fields = list(reader.fieldnames) + ["is_tech", "tech_category", "tech_confidence"]

        with open(all_out, "w", newline="") as fall, open(tech_out, "w", newline="") as ftech:
            wall = csv.DictWriter(fall, fieldnames=out_fields)
            wtech = csv.DictWriter(ftech, fieldnames=out_fields)
            wall.writeheader()
            wtech.writeheader()

            for i, row in enumerate(reader):
                if test_limit and i >= test_limit:
                    break

                clf = classifications.get(i, {})
                is_tech_val = clf.get("is_tech")
                if is_tech_val is True:
                    row["is_tech"] = "true"
                elif is_tech_val is False:
                    row["is_tech"] = "false"
                else:
                    row["is_tech"] = "error"
                row["tech_category"] = clf.get("tech_category", "")
                row["tech_confidence"] = clf.get("confidence", "")

                wall.writerow(row)
                total += 1

                if row["is_tech"] == "true":
                    wtech.writerow(row)
                    tech_count += 1
                elif row["is_tech"] == "false":
                    not_tech_count += 1
                else:
                    error_count += 1

    stats = {
        "timestamp": datetime.now().isoformat(),
        "total_rows": total,
        "tech_deals": tech_count,
        "not_tech_deals": not_tech_count,
        "errors": error_count,
        "tech_percentage": round(tech_count / total * 100, 2) if total else 0,
        "output_all": str(all_out),
        "output_tech_only": str(tech_out),
    }
    with open(stats_out, "w") as f:
        json.dump(stats, f, indent=2)

    logger.info("")
    logger.info("=" * 60)
    logger.info("MERGE RESULTS")
    logger.info("=" * 60)
    logger.info(f"  Total rows:   {total:,}")
    if total:
        logger.info(f"  Tech deals:   {tech_count:,} ({tech_count / total * 100:.1f}%)")
    logger.info(f"  Not tech:     {not_tech_count:,}")
    logger.info(f"  Errors:       {error_count:,}")
    logger.info(f"  Output (all): {all_out}")
    logger.info(f"  Output (tech):{tech_out}")
    logger.info(f"  Stats:        {stats_out}")
    logger.info("=" * 60)

    return stats


# ═══════════════════════════════════════════════════════════════
# LOGGING SETUP
# ═══════════════════════════════════════════════════════════════

def setup_logger(test_limit, model, concurrency):
    """Configure logging per COMMANDMENTS.yml."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file = LOG_DIR / f"classify_deals_{ts}.log"

    logger = logging.getLogger("classify_deals")
    logger.setLevel(logging.INFO)
    # Clear any existing handlers (important for re-runs)
    logger.handlers.clear()

    fmt = logging.Formatter("[%(asctime)s] %(message)s", datefmt="%H:%M:%S")

    fh = logging.FileHandler(log_file)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    logger.info("=" * 60)
    logger.info("SCRIPT: classify_deals.py")
    logger.info("LAYER: L1 - Tech Deal Classification")
    logger.info(f"STARTED: {datetime.now().isoformat()}")
    mode = f"TEST ({test_limit:,} rows)" if test_limit else "FULL RUN"
    logger.info(f"MODE: {mode}")
    logger.info(f"MODEL: {model}")
    logger.info(f"BATCH_SIZE: {BATCH_SIZE}")
    logger.info(f"MAX_CONCURRENCY: {concurrency}")
    logger.info("=" * 60)

    return logger, log_file


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Classify M&A deals as technology-related")
    parser.add_argument("--test", type=int, metavar="N", help="Limit to first N rows")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    parser.add_argument("--merge-only", action="store_true", help="Skip classification, merge existing checkpoint")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY, help="Max parallel API calls")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="OpenAI model to use")
    args = parser.parse_args()

    model = args.model
    concurrency = args.concurrency

    logger, log_file = setup_logger(args.test, model, concurrency)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    suffix = f"test_{args.test}" if args.test else "full"
    checkpoint_file = CHECKPOINT_DIR / f"classify_tech_{suffix}.jsonl"

    if not args.merge_only:
        if not INPUT_CSV.exists():
            logger.error(f"Input CSV not found: {INPUT_CSV}")
            sys.exit(1)

        logger.info(f"Reading {INPUT_CSV.name} (extracting classify columns)...")
        t0 = time.time()
        rows = []
        with open(INPUT_CSV, "r") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                if args.test and i >= args.test:
                    break
                rows.append({
                    "idx": i,
                    "Target Full Name": row.get("Target Full Name", ""),
                    "Target Primary SIC": row.get("Target Primary SIC", ""),
                    "Target Mid Industry": row.get("Target Mid Industry", ""),
                    "Target Macro Industry": row.get("Target Macro Industry", ""),
                })
        logger.info(f"Loaded {len(rows):,} rows in {time.time() - t0:.1f}s")

        asyncio.run(run_classification(rows, checkpoint_file, model, concurrency, args, logger))

    if checkpoint_file.exists():
        merge_results(checkpoint_file, args.test, logger)
    else:
        logger.error("No checkpoint file found. Run classification first.")

    logger.info("")
    logger.info("=" * 60)
    logger.info(f"COMPLETED: {datetime.now().isoformat()}")
    logger.info(f"STATUS: SUCCESS")
    logger.info(f"LOG: {log_file}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
