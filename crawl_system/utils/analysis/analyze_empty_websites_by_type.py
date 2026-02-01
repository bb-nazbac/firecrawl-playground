import json
from pathlib import Path

responses_dir = Path("l3_llm_classify_extract/outputs/openinfo/unitaswholesale/llm_responses")

stats = {
    "company_individual": {"with_website": 0, "without_website": 0},
    "company_list": {"with_website": 0, "without_website": 0},
    "navigation": {"with_website": 0, "without_website": 0},
    "other": {"with_website": 0, "without_website": 0}
}

for response_file in sorted(responses_dir.glob("response_chunk_*.json")):
    try:
        with open(response_file) as f:
            data = json.load(f)
        
        if "content" in data and len(data["content"]) > 0:
            text = data["content"][0].get("text", "")
            if text:
                try:
                    parsed = json.loads(text.strip().replace("```json\n", "").replace("\n```", ""))
                    
                    if "classifications" in parsed:
                        for classification in parsed["classifications"]:
                            class_type = classification.get("classification", "other")
                            
                            if "companies_extracted" in classification:
                                for company in classification["companies_extracted"]:
                                    if company.get("website", "").strip():
                                        stats[class_type]["with_website"] += 1
                                    else:
                                        stats[class_type]["without_website"] += 1
                except:
                    pass
    except:
        pass

print("Companies by Classification Type:")
print("=" * 70)
for class_type, counts in stats.items():
    total = counts["with_website"] + counts["without_website"]
    if total > 0:
        pct_with = (counts["with_website"] / total * 100)
        print(f"\n{class_type.upper()}:")
        print(f"  Total: {total}")
        print(f"  With website: {counts['with_website']} ({pct_with:.1f}%)")
        print(f"  WITHOUT website: {counts['without_website']} ({100-pct_with:.1f}%)")
