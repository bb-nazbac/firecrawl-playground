const fs = require('fs');
const path = require('path');
const Anthropic = require('@anthropic-ai/sdk');

// Load Env
function loadEnv() {
    try {
        // Script is in qualifying_agents_prod/testing/round_02_selector_logic/
        // Root is ../../../
        const envPath = path.resolve(__dirname, '../../../.env');
        if (fs.existsSync(envPath)) {
            const envConfig = fs.readFileSync(envPath, 'utf8');
            envConfig.split('\n').forEach(line => {
                const [key, value] = line.split('=');
                if (key && value) {
                    process.env[key.trim()] = value.trim();
                }
            });
        }
    } catch (error) {
        console.warn('Could not load .env file', error);
    }
}
loadEnv();

if (!process.env.ANTHROPIC_API_KEY) {
    console.error('❌ ANTHROPIC_API_KEY not found');
    process.exit(1);
}

const anthropic = new Anthropic({
    apiKey: process.env.ANTHROPIC_API_KEY,
});

// Load Spec
const SPEC_PATH = path.join(__dirname, 'selector_spec.json');
const spec = JSON.parse(fs.readFileSync(SPEC_PATH, 'utf8'));

// Input/Output Dirs
const INPUT_DIR = path.resolve(__dirname, '../round_01_map_endpoint_exploration/outputs');
const OUTPUT_DIR = path.resolve(__dirname, 'outputs_llm');

if (!fs.existsSync(OUTPUT_DIR)) fs.mkdirSync(OUTPUT_DIR, { recursive: true });

async function selectPagesWithLLM(mapData, domain) {
    const allLinks = mapData.links || [];

    // 1. Deterministic Pre-filter (Save tokens)
    // Filter out ignores and non-English (re-using logic if possible, or just ignores)
    const cleanLinks = allLinks.filter(link => {
        const lowerUrl = link.url.toLowerCase();
        // Ignore patterns from spec
        if (spec.ignore_patterns.some(pattern => lowerUrl.includes(pattern))) return false;
        // Basic non-English check (optional, but good for token saving)
        if (['/de/', '/ja/', '/fr/', '/es/'].some(p => lowerUrl.includes(p))) return false;
        return true;
    });

    console.log(`   Pre-filtered ${allLinks.length} -> ${cleanLinks.length} links`);

    // 2. Prepare Prompt
    // We'll send the list of URLs and the strategies
    const urlList = cleanLinks.map(l => l.url).join('\n');

    const strategiesDesc = spec.strategies.map(s =>
        `- ID: ${s.id} (${s.label})\n  Goal: Find ${s.limit} best page(s).`
    ).join('\n');

    const prompt = `
You are a URL classification agent. Your goal is to select the most relevant pages for specific categories from a list of website URLs.

DOMAIN: ${domain}

CATEGORIES:
${strategiesDesc}

INSTRUCTIONS:
1. Analyze the provided list of URLs.
2. For each category, select the BEST matching URLs based on the path and likely content.
3. Be strict. If no good match exists for a category, return an empty list for it.
4. Avoid blog posts (unless specifically asked), login pages, or irrelevant sub-pages.
5. Prioritize "root" pages (e.g., /pricing is better than /pricing/enterprise).
6. FOR JOB POSTINGS: Look for individual job descriptions (e.g. /jobs/software-engineer), NOT general career landing pages.
7. CRITICAL: Return ONLY valid JSON. Do not include any conversational text, markdown formatting, or explanations.

URL LIST:
${urlList}

OUTPUT FORMAT:
{
  "selections": [
    {
      "category_id": "pricing",
      "urls": ["https://example.com/pricing"]
    },
    ...
  ]
}
`;

    // 3. Call Claude
    try {
        const msg = await anthropic.messages.create({
            model: "claude-3-5-haiku-20241022",
            max_tokens: 4096,
            temperature: 0,
            system: "You are a helpful JSON-outputting assistant. You output ONLY valid JSON.",
            messages: [
                { role: "user", content: prompt }
            ]
        });

        const content = msg.content[0].text;

        // Robust JSON extraction
        const jsonStart = content.indexOf('{');
        const jsonEnd = content.lastIndexOf('}');

        if (jsonStart === -1 || jsonEnd === -1) {
            throw new Error("No JSON object found in response");
        }

        const jsonStr = content.substring(jsonStart, jsonEnd + 1);
        const result = JSON.parse(jsonStr);

        return {
            total_input: allLinks.length,
            clean_input: cleanLinks.length,
            selections: result.selections,
            raw_response: result
        };

    } catch (error) {
        console.error("LLM Error:", error);
        return null;
    }
}

async function processFile(filename) {
    if (!filename.endsWith('_map.json')) return;

    console.log(`Processing ${filename}...`);
    const content = JSON.parse(fs.readFileSync(path.join(INPUT_DIR, filename), 'utf8'));

    // Extract domain from filename or content
    // filename: rampf-group_com_map.json -> rampf-group.com
    const domain = filename.replace('_map.json', '').replace(/_/g, '.'); // Approximate

    const result = await selectPagesWithLLM(content, domain);

    if (result) {
        console.log(`   LLM Selected pages:`);
        result.selections.forEach(cat => {
            console.log(`      [${cat.category_id}]: ${cat.urls.join(', ')}`);
        });

        fs.writeFileSync(path.join(OUTPUT_DIR, filename.replace('_map.json', '_selected_llm.json')), JSON.stringify(result, null, 2));
    }
}

// Main
async function main() {
    console.log('🚀 Starting Round 02: LLM Selector Logic (Haiku 3.5)');
    console.log('====================================================');

    const files = fs.readdirSync(INPUT_DIR);
    for (const file of files) {
        // Let's prioritize rampf-group for the user request
        if (file.includes('rampf')) {
            await processFile(file);
        }
    }

    // Process others? Maybe later or if requested.
    // Let's do all for completeness if it's fast.
    /*
    for (const file of files) {
        if (!file.includes('rampf') && file.endsWith('_map.json')) {
            await processFile(file);
        }
    }
    */

    console.log('====================================================');
    console.log('🏁 Round 02 LLM Complete');
}

main().catch(console.error);
