#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# MAP Endpoint Rate Limit Test Runner
# Runs tests at multiple concurrency levels to find optimal config
# ═══════════════════════════════════════════════════════════════

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Create results directory
mkdir -p "${RESULTS_DIR}"

echo "═══════════════════════════════════════════════════════════════"
echo "MAP ENDPOINT RATE LIMIT TEST SUITE"
echo "═══════════════════════════════════════════════════════════════"
echo "Started: $(date)"
echo "Results will be saved to: ${RESULTS_DIR}"
echo ""

# Test matrix - concurrency levels to test
CONCURRENCY_LEVELS=(1 2 3 5 10)
DOMAINS_PER_TEST=50

for concurrency in "${CONCURRENCY_LEVELS[@]}"; do
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo "TEST: Concurrency = ${concurrency}"
    echo "═══════════════════════════════════════════════════════════════"

    output_file="${RESULTS_DIR}/test_c${concurrency}_${TIMESTAMP}.json"

    python3 "${SCRIPT_DIR}/map_rate_test.py" \
        --concurrency "${concurrency}" \
        --domains "${DOMAINS_PER_TEST}" \
        --output "${output_file}"

    echo ""
    echo "Completed test at concurrency ${concurrency}"
    echo "Results saved to: ${output_file}"
    echo ""

    # Brief pause between tests to let rate limits reset
    if [ "${concurrency}" != "${CONCURRENCY_LEVELS[-1]}" ]; then
        echo "Waiting 60 seconds before next test..."
        sleep 60
    fi
done

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "ALL TESTS COMPLETE"
echo "═══════════════════════════════════════════════════════════════"
echo "Finished: $(date)"
echo "Results saved to: ${RESULTS_DIR}"
echo ""

# Generate summary
echo "Generating summary..."
python3 - << 'EOF'
import json
import glob
import os

results_dir = os.environ.get('RESULTS_DIR', 'results')
files = sorted(glob.glob(f"{results_dir}/test_c*.json"))

if not files:
    print("No result files found")
    exit(1)

print("\n" + "="*70)
print("SUMMARY: MAP Rate Limit Test Results")
print("="*70)
print(f"{'Concurrency':<12} {'Success':<10} {'Failed':<10} {'Rate %':<10} {'429s':<10} {'Req/min':<10}")
print("-"*70)

for f in files:
    with open(f) as fp:
        data = json.load(fp)
        m = data['metrics']
        print(f"{m['concurrency']:<12} {m['successful']:<10} {m['failed']:<10} {m['success_rate']:<10.1f} {m['total_rate_limits']:<10} {m['requests_per_minute']:<10.1f}")

print("="*70)
EOF
