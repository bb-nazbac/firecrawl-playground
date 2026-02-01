import json
import re
from pathlib import Path

# Find chunks that have markdown links to company websites
chunks_dir = Path("l2_merge_and_chunk/outputs/openinfo/unitaswholesale/chunks")
responses_dir = Path("l3_llm_classify_extract/outputs/openinfo/unitaswholesale/llm_responses")

extraction_failures = []

# Pattern to match markdown links in company listings
# Looking for patterns like "[Company Name](http://website.com/)"
link_pattern = re.compile(r'\[([^\]]+)\]\((https?://[^\)]+)\)')

for chunk_file in sorted(chunks_dir.glob("chunk_*.json"))[:100]:  # Check first 100
    chunk_num = chunk_file.stem.split("_")[1]
    response_file = responses_dir / f"response_chunk_{chunk_num}.json"
    
    if not response_file.exists():
        continue
    
    try:
        # Read chunk
        with open(chunk_file) as f:
            chunk_data = json.load(f)
        
        markdown = chunk_data["pages"][0]["markdown"]
        
        # Find all links in markdown (excluding social media, generic links, etc.)
        links = link_pattern.findall(markdown)
        company_links = [
            (name, url) for name, url in links 
            if "unitaswholesale.co.uk" not in url.lower()
            and not any(x in url.lower() for x in ["facebook.com", "twitter.com", "linkedin.com", "instagram.com"])
            and not url.lower().endswith((".png", ".jpg", ".svg", ".pdf"))
        ]
        
        if not company_links:
            continue
            
        # Read response
        with open(response_file) as f:
            response_data = json.load(f)
        
        if "content" not in response_data:
            continue
            
        text = response_data["content"][0].get("text", "")
        if not text:
            continue
            
        try:
            parsed = json.loads(text.strip().replace("```json\n", "").replace("\n```", ""))
        except:
            continue
        
        # Get extracted companies
        extracted_companies = []
        if "classifications" in parsed:
            for classification in parsed["classifications"]:
                if "companies_extracted" in classification:
                    for company in classification["companies_extracted"]:
                        extracted_companies.append({
                            "name": company.get("name"),
                            "website": company.get("website", "")
                        })
        
        # Check if links in markdown were missed
        for link_name, link_url in company_links[:3]:  # Show first 3 links
            # Check if this company was extracted
            found = False
            for extracted in extracted_companies:
                if link_url in extracted.get("website", ""):
                    found = True
                    break
            
            if not found:
                extraction_failures.append({
                    "chunk": chunk_num,
                    "markdown_link_name": link_name,
                    "markdown_link_url": link_url,
                    "extracted_count": len(extracted_companies)
                })
                
    except Exception as e:
        pass

print(f"Found {len(extraction_failures)} potential extraction failures")
print("\nFirst 10 examples where markdown had links but Claude didn't extract them:")
for i, item in enumerate(extraction_failures[:10]):
    print(f"{i+1}. Chunk {item['chunk']}: [{item['markdown_link_name']}]({item['markdown_link_url']}) - Claude extracted {item['extracted_count']} companies total")
