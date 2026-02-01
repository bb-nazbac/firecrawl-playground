#!/usr/bin/env python3
"""
Analyze analytics.jsonl to understand concurrency patterns.
Usage: python temp/analyze_analytics.py <path_to_analytics.jsonl>
"""

import json
import sys
import statistics
from pathlib import Path

def analyze_analytics(jsonl_path: str):
    snapshots = []
    with open(jsonl_path, 'r') as f:
        for line in f:
            snapshots.append(json.loads(line))

    print(f"=" * 60)
    print(f"ANALYTICS: {Path(jsonl_path).parent.name}")
    print(f"=" * 60)
    print(f"Total snapshots: {len(snapshots)}")
    print(f"Duration: {snapshots[-1]['elapsed_seconds']:.1f}s")
    print()

    # Skip first 2 seconds (startup)
    steady_state = [s for s in snapshots if s['elapsed_seconds'] > 2]

    if not steady_state:
        print("Not enough data for analysis")
        return

    # Firecrawl utilization
    fc_utils = [s['firecrawl_utilization_pct'] for s in steady_state]
    fc_active = [s['firecrawl_active'] for s in steady_state]
    print("=== FIRECRAWL UTILIZATION (after 2s) ===")
    print(f"  Min: {min(fc_utils):.1f}%  ({min(fc_active)} active)")
    print(f"  Max: {max(fc_utils):.1f}%  ({max(fc_active)} active)")
    print(f"  Mean: {statistics.mean(fc_utils):.1f}%")
    print(f"  Median: {statistics.median(fc_utils):.1f}%")
    print()

    # OpenAI utilization
    oai_utils = [s['openai_utilization_pct'] for s in steady_state]
    oai_active = [s['openai_active'] for s in steady_state]
    print("=== OPENAI UTILIZATION (after 2s) ===")
    print(f"  Min: {min(oai_utils):.1f}%  ({min(oai_active)} active)")
    print(f"  Max: {max(oai_utils):.1f}%  ({max(oai_active)} active)")
    print(f"  Mean: {statistics.mean(oai_utils):.1f}%")
    print(f"  Median: {statistics.median(oai_utils):.1f}%")
    print()

    # Utilization buckets for Firecrawl
    print("=== FIRECRAWL UTILIZATION DISTRIBUTION ===")
    buckets = {'0-20%': 0, '20-40%': 0, '40-60%': 0, '60-80%': 0, '80-100%': 0}
    for u in fc_utils:
        if u <= 20: buckets['0-20%'] += 1
        elif u <= 40: buckets['20-40%'] += 1
        elif u <= 60: buckets['40-60%'] += 1
        elif u <= 80: buckets['60-80%'] += 1
        else: buckets['80-100%'] += 1

    for bucket, count in buckets.items():
        pct = count / len(fc_utils) * 100
        bar = '█' * int(pct / 2)
        print(f"  {bucket}: {count:4d} ({pct:5.1f}%) {bar}")
    print()

    # Throughput
    throughputs = [s['domains_per_minute'] for s in steady_state]
    print("=== THROUGHPUT ===")
    print(f"  Min: {min(throughputs):.1f} domains/min")
    print(f"  Max: {max(throughputs):.1f} domains/min")
    print(f"  Mean: {statistics.mean(throughputs):.1f} domains/min")
    print(f"  Final: {throughputs[-1]:.1f} domains/min")
    print()

    # Time spent at low Firecrawl utilization
    low_fc_time = sum(1 for s in steady_state if s['firecrawl_utilization_pct'] < 30)
    high_oai_time = sum(1 for s in steady_state if s['openai_utilization_pct'] > 100)
    print("=== BOTTLENECK ANALYSIS ===")
    print(f"  Time with Firecrawl < 30%: {low_fc_time}s ({low_fc_time/len(steady_state)*100:.1f}% of run)")
    print(f"  Time with OpenAI > 100%: {high_oai_time}s ({high_oai_time/len(steady_state)*100:.1f}% of run)")

    if high_oai_time > low_fc_time * 0.5:
        print()
        print("  ⚠️  BOTTLENECK: OpenAI/LLM is the constraint!")
        print("  Recommendation: Increase OpenAI concurrency to match Firecrawl")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python temp/analyze_analytics.py <path_to_analytics.jsonl>")
        sys.exit(1)

    analyze_analytics(sys.argv[1])
