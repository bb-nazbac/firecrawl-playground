const fs = require('fs');
const path = require('path');

// Load Spec
const SPEC_PATH = path.join(__dirname, 'selector_spec.json');
const spec = JSON.parse(fs.readFileSync(SPEC_PATH, 'utf8'));

// Input/Output Dirs
const INPUT_DIR = path.resolve(__dirname, '../round_01_map_endpoint_exploration/outputs');
const OUTPUT_DIR = path.resolve(__dirname, 'outputs');

if (!fs.existsSync(OUTPUT_DIR)) fs.mkdirSync(OUTPUT_DIR, { recursive: true });

function scoreUrl(url, strategy) {
    const lowerUrl = url.toLowerCase();
    for (const pattern of strategy.patterns) {
        // Simple inclusion match for now. Could be regex.
        if (lowerUrl.includes(pattern)) {
            // Prefer exact matches or matches closer to root?
            // For now, just return priority.
            return strategy.priority;
        }
    }
    return 0;
}

function selectPages(mapData) {
    const allLinks = mapData.links || [];
    const selectedPages = [];
    const debugLog = [];

    // 1. Filter out ignores
    const cleanLinks = allLinks.filter(link => {
        const lowerUrl = link.url.toLowerCase();
        return !spec.ignore_patterns.some(pattern => lowerUrl.includes(pattern));
    });

    // 2. Apply Strategies
    // We want to fill buckets based on strategy limits

    const buckets = {}; // strategy_id -> [links]

    for (const strategy of spec.strategies) {
        buckets[strategy.id] = [];

        for (const link of cleanLinks) {
            if (scoreUrl(link.url, strategy) > 0) {
                buckets[strategy.id].push(link);
            }
        }

        // Sort buckets? Maybe shortest URL first (heuristic for "main" page)?
        buckets[strategy.id].sort((a, b) => a.url.length - b.url.length);
    }

    // 3. Select final set
    // Iterate strategies by priority
    const sortedStrategies = [...spec.strategies].sort((a, b) => b.priority - a.priority);
    const selectedUrls = new Set();

    for (const strategy of sortedStrategies) {
        const candidates = buckets[strategy.id];
        let taken = 0;

        for (const candidate of candidates) {
            if (taken >= strategy.limit) break;
            if (selectedPages.length >= spec.max_pages) break;

            if (!selectedUrls.has(candidate.url)) {
                selectedPages.push({
                    ...candidate,
                    reason: strategy.id,
                    score: strategy.priority
                });
                selectedUrls.add(candidate.url);
                taken++;
            }
        }
    }

    // If we still have room, maybe fill with "Product" pages if we didn't hit limit?
    // Or just leave it.

    return {
        total_input: allLinks.length,
        clean_input: cleanLinks.length,
        selected: selectedPages
    };
}

function processFile(filename) {
    if (!filename.endsWith('_map.json')) return;

    console.log(`Processing ${filename}...`);
    const content = JSON.parse(fs.readFileSync(path.join(INPUT_DIR, filename), 'utf8'));

    const result = selectPages(content);

    console.log(`   Selected ${result.selected.length} pages from ${result.total_input} links.`);
    result.selected.forEach(p => console.log(`      [${p.reason}] ${p.url}`));

    fs.writeFileSync(path.join(OUTPUT_DIR, filename.replace('_map.json', '_selected.json')), JSON.stringify(result, null, 2));
}

// Main
console.log('🚀 Starting Round 02: Selector Logic');
console.log('====================================');

const files = fs.readdirSync(INPUT_DIR);
for (const file of files) {
    processFile(file);
}

console.log('====================================');
console.log('🏁 Round 02 Complete');
