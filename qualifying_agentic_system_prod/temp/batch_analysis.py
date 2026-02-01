#!/usr/bin/env python3
"""Analyze batch 1 & 2 results for QA"""
import json

def analyze():
    print("=" * 70)
    print("BATCH 1 & 2 OUTPUT VERIFICATION")
    print("=" * 70)

    for batch_num, path in [(1, 'outputs/poka_labs/poka_l2_1_of_20_20260103_095511/results.jsonl'),
                            (2, 'outputs/poka_labs/poka_l2_2_of_20_20260103_124115/results.jsonl')]:
        print(f"\n{'='*30} BATCH {batch_num} {'='*30}")

        found_examples = {}
        all_classifications = {}

        with open(path) as f:
            for line in f:
                r = json.loads(line)
                cls = r.get('classification')
                all_classifications[cls] = all_classifications.get(cls, 0) + 1

                # Store first example of each interesting classification
                if cls and cls not in ['DISQUALIFIED'] and cls not in found_examples:
                    found_examples[cls] = {
                        'domain': r['domain'],
                        'company_name': r.get('company_name'),
                        'products_found': r.get('products_found'),
                        'answers': r.get('answers'),
                    }

        print("\n--- Classification Distribution ---")
        for cls, count in sorted(all_classifications.items(), key=lambda x: -x[1]):
            print(f"  {cls}: {count}")

        print("\n--- Sample Qualified Results ---")
        for cls in ['CHEMICAL', 'PHARMA', 'ENGINEERED_MATERIALS', 'OTHER_TECHNICAL',
                    'QUALIFIED_TIER_1', 'QUALIFIED_TIER_2', 'QUALIFIED_TIER_3']:
            if cls in found_examples:
                ex = found_examples[cls]
                print(f"\n  [{cls}] {ex['domain']}")
                print(f"    Company: {ex['company_name']}")
                print(f"    Products: {ex['products_found']}")
                if ex['answers']:
                    ans = ex['answers']
                    print(f"    Answers: sells={ans.get('sells_products')}, "
                          f"b2b={ans.get('is_b2b')}, "
                          f"inv={ans.get('has_inventory_or_manufacturing')}, "
                          f"type={ans.get('product_type')}")

if __name__ == "__main__":
    analyze()
