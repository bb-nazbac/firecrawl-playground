#!/usr/bin/env python3
"""
Analyze a pipeline run's results.jsonl file
Usage: python temp/analyze_run.py <path_to_results.jsonl>
"""

import json
import sys
import statistics
from collections import Counter, defaultdict
from pathlib import Path

def analyze_run(jsonl_path: str):
    results = []
    with open(jsonl_path, 'r') as f:
        for line in f:
            results.append(json.loads(line))

    print(f"=" * 60)
    print(f"ANALYSIS: {Path(jsonl_path).parent.name}")
    print(f"=" * 60)
    print(f"Total results: {len(results)}")
    print()

    # Classification breakdown
    classifications = Counter(r.get('classification', 'unknown') for r in results)
    print("=== CLASSIFICATION BREAKDOWN ===")
    for cls, count in classifications.most_common():
        pct = count / len(results) * 100
        print(f"  {cls}: {count} ({pct:.1f}%)")
    print()

    # Path breakdown
    paths = Counter(r.get('path', 'unknown') for r in results)
    print("=== PATH BREAKDOWN ===")
    for path, count in paths.most_common():
        pct = count / len(results) * 100
        print(f"  {path}: {count} ({pct:.1f}%)")
    print()

    # Disqualification reasons
    disqualified = [r for r in results if r.get('classification') == 'disqualified']
    if disqualified:
        print(f"=== DISQUALIFICATION REASONS ({len(disqualified)} domains) ===")
        reasons = []
        for r in disqualified:
            reason = r.get('disqualification_reason') or r.get('reason') or r.get('l1_reason') or 'unknown'
            if isinstance(reason, str) and len(reason) > 80:
                reason = reason[:80] + '...'
            reasons.append(reason)

        reason_counts = Counter(reasons)
        for reason, count in reason_counts.most_common(15):
            pct = count / len(disqualified) * 100
            print(f"  {count:4d} ({pct:5.1f}%): {reason}")
        print()

    # Duration statistics
    durations = [r.get('duration_seconds', 0) for r in results if r.get('duration_seconds')]
    if durations:
        print("=== DURATION STATISTICS ===")
        print(f"  Domains with duration: {len(durations)}")
        print(f"  Min: {min(durations):.1f}s")
        print(f"  Max: {max(durations):.1f}s")
        print(f"  Mean: {statistics.mean(durations):.1f}s")
        print(f"  Median: {statistics.median(durations):.1f}s")
        sorted_d = sorted(durations)
        if len(sorted_d) > 1:
            p95 = sorted_d[int(len(sorted_d) * 0.95)]
            p99 = sorted_d[int(len(sorted_d) * 0.99)]
            print(f"  P95: {p95:.1f}s")
            print(f"  P99: {p99:.1f}s")
        total_time = sum(durations)
        print(f"  Total processing time (sum): {total_time/3600:.2f} hours")
        print()

    # Tokens by path
    print("=== TOKENS BY PATH ===")
    path_tokens = defaultdict(lambda: {'input': 0, 'output': 0, 'count': 0})
    for r in results:
        path = r.get('path', 'unknown')
        path_tokens[path]['input'] += r.get('input_tokens', 0)
        path_tokens[path]['output'] += r.get('output_tokens', 0)
        path_tokens[path]['count'] += 1

    for path, data in sorted(path_tokens.items()):
        total = data['input'] + data['output']
        avg = total / data['count'] if data['count'] else 0
        print(f"  {path}: {total:,} tokens ({data['count']} domains, avg {avg:,.0f}/domain)")
    print()

    # Pages scraped distribution
    print("=== PAGES SCRAPED DISTRIBUTION ===")
    pages_scraped = Counter(r.get('pages_scraped', 0) for r in results)
    for pages, count in sorted(pages_scraped.items()):
        pct = count / len(results) * 100
        print(f"  {pages} pages: {count} ({pct:.1f}%)")
    print()

    # Qualified companies sample
    qualified = [r for r in results if r.get('classification') == 'qualified']
    if qualified:
        print(f"=== QUALIFIED SAMPLE (first 10 of {len(qualified)}) ===")
        for r in qualified[:10]:
            company = r.get('company_name', r.get('domain', 'unknown'))
            print(f"  - {company}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python temp/analyze_run.py <path_to_results.jsonl>")
        sys.exit(1)

    analyze_run(sys.argv[1])
