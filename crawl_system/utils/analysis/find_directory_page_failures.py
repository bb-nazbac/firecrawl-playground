import json
import re
from pathlib import Path

chunks_dir = Path("l2_merge_and_chunk/outputs/openinfo/unitaswholesale/chunks")
responses_dir = Path("l3_llm_classify_extract/outputs/openinfo/unitaswholesale/llm_responses")

failures = []

for chunk_file in sorted(chunks_dir.glob("chunk_*.json")):
    chunk_num = chunk_file.stem.split("_")[1]
    response_file = responses_dir / f"response_chunk_{chunk_num}.json"
    
    if not response_file.exists():
        continue
    
    try:
        with open(chunk_file) as f:
            chunk_data = json.load(f)
        
        url = chunk_data["pages"][0]["url"]
        markdown = chunk_data["pages"][0]["markdown"]
        
        # Only check wholesaler directory pages
        if "wholesaler-search" not in url:
            continue
        
        # Count companies with links in markdown (rough heuristic)
        # Looking for patterns where company names appear before website links
        link_pattern = re.compile(r'\[([^\]]{5,})\]\((https?://(?!unitaswholesale)[^\)]+)\)', re.IGNORECASE)
        links = link_pattern.findall(markdown)
        
        # Filter to likely company links (not social media, etc)
        company_links = [
            (name, url) for name, url in links 
            if not any(x in url.lower() for x in ["facebook", "twitter", "linkedin", "instagram", "google.com"])
            and not url.lower().endswith((".png", ".jpg", ".svg", ".pdf"))
            and len(name) > 2
        ]
        
        if len(company_links) == 0:
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
        
        # Get extracted companies WITH websites
        extracted_with_websites = 0
        extracted_without_websites = 0
        
        if "classifications" in parsed:
            for classification in parsed["classifications"]:
                if "companies_extracted" in classification:
                    for company in classification["companies_extracted"]:
                        if company.get("website", "").strip():
                            extracted_with_websites += 1
                        else:
                            extracted_without_websites += 1
        
        if extracted_without_websites > 0:
            failures.append({
                "chunk": chunk_num,
                "url": url,
                "markdown_links_count": len(company_links),
                "extracted_with_websites": extracted_with_websites,
                "extracted_without_websites": extracted_without_websites,
                "sample_markdown_links": company_links[:2]
            })
                
    except Exception as e:
        pass

print(f"Found {len(failures)} wholesaler directory pages where Claude extracted companies WITHOUT websites")
print(f"\nThese pages had {sum(f['markdown_links_count'] for f in failures)} total markdown links")
print(f"\nFirst 5 examples:")
for i, item in enumerate(failures[:5]):
    print(f"\n{i+1}. Chunk {item['chunk']} ({item['url']})")
    print(f"   Markdown had {item['markdown_links_count']} company links")
    print(f"   Claude extracted: {item['extracted_with_websites']} WITH websites, {item['extracted_without_websites']} WITHOUT")
    print(f"   Sample links in markdown: {item['sample_markdown_links'][0] if item['sample_markdown_links'] else 'none'}")
