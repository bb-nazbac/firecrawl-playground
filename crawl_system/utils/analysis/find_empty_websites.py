import json
from pathlib import Path

responses_dir = Path("l3_llm_classify_extract/outputs/openinfo/unitaswholesale/llm_responses")

empty_websites = []

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
                            if "companies_extracted" in classification:
                                for company in classification["companies_extracted"]:
                                    if company.get("website", "").strip() == "":
                                        empty_websites.append({
                                            "file": response_file.name,
                                            "company": company.get("name"),
                                            "classification": classification.get("classification")
                                        })
                except:
                    pass
    except:
        pass

print(f"Found {len(empty_websites)} companies with empty websites")
print("\nFirst 10 examples:")
for i, item in enumerate(empty_websites[:10]):
    print(f"{i+1}. {item['company']} (from {item['file']}, type: {item['classification']})")
