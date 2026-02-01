const fs = require('fs');
const path = require('path');

// Simple .env parser
function loadEnv() {
    try {
        const envPath = path.resolve(__dirname, '../../../../.env');
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

const API_KEY = process.env.FIRECRAWL_API_KEY;
if (!API_KEY) {
    console.error('❌ FIRECRAWL_API_KEY not found in environment variables');
    process.exit(1);
}

const DOMAINS = [
    'rampf-group.com'
];

const OUTPUT_DIR = path.resolve(__dirname, '../outputs');
const LOG_DIR = path.resolve(__dirname, '../logs/l1_map_exploration');

// Ensure directories exist
if (!fs.existsSync(OUTPUT_DIR)) fs.mkdirSync(OUTPUT_DIR, { recursive: true });
if (!fs.existsSync(LOG_DIR)) fs.mkdirSync(LOG_DIR, { recursive: true });

function isLikelyNonEnglish(url) {
    // Common non-English language codes in paths
    // We'll rely on the specific en-XX filter for those, 
    // and this one for completely different languages.
    const nonEnglishPatterns = [
        '/de/', '/de-', '/-de/', // German
        '/fr/', '/fr-', '/-fr/', // French
        '/es/', '/es-', '/-es/', // Spanish
        '/it/', '/it-', '/-it/', // Italian
        '/ja/', '/jp/', '/ja-jp/', // Japanese
        '/zh/', '/cn/', // Chinese
        '/ko/', '/kr/', // Korean
        '/ru/', // Russian
        '/pt/', '/br/', // Portuguese
        '/nl/', // Dutch
        '/pl/', // Polish
        '/tr/', // Turkish
        '/ar/', // Arabic
        '/hi/', // Hindi
        '/vi/', // Vietnamese
        '/th/', // Thai
        '/id/', // Indonesian
    ];

    const lowerUrl = url.toLowerCase();
    return nonEnglishPatterns.some(pattern => lowerUrl.includes(pattern));
}

function filterEnglishVariants(links) {
    const enPattern = /\/en-([a-z]{2})(\/|$)/i;

    // Pass 1: Detect available variants
    let hasEnUs = false;
    let hasEnGb = false;

    for (const link of links) {
        const match = link.url.match(enPattern);
        if (match) {
            const variant = match[1].toLowerCase();
            if (variant === 'us') hasEnUs = true;
            if (variant === 'gb') hasEnGb = true;
        }
    }

    // Decision logic: Prefer US over GB
    const keepEnUs = hasEnUs;
    const keepEnGb = !hasEnUs && hasEnGb; // Only keep GB if US is missing

    console.log(`   English Variants Detected: US=${hasEnUs}, GB=${hasEnGb}`);
    console.log(`   Policy: Keep US=${keepEnUs}, Keep GB=${keepEnGb}`);

    // Pass 2: Filter
    const filtered = [];
    let droppedCount = 0;

    for (const link of links) {
        const match = link.url.match(enPattern);
        if (match) {
            const variant = match[1].toLowerCase();
            if (variant === 'us') {
                if (keepEnUs) filtered.push(link);
                else droppedCount++;
            } else if (variant === 'gb') {
                if (keepEnGb) filtered.push(link);
                else droppedCount++;
            } else {
                // Drop all other en-XX (en-jp, en-kr, etc.)
                droppedCount++;
            }
        } else {
            // No /en-XX/ pattern, keep it (generic or root)
            filtered.push(link);
        }
    }

    return { filtered, droppedCount };
}

async function mapDomain(domain) {
    console.log(`\n🗺️  Mapping ${domain}...`);
    const startTime = Date.now();

    try {
        const response = await fetch('https://api.firecrawl.dev/v2/map', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${API_KEY}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                url: `https://${domain}`,
                limit: 5000
            })
        });

        const data = await response.json();
        const duration = Date.now() - startTime;

        if (data.success) {
            const totalLinks = data.links?.length || 0;

            // Step 1: Basic Non-English Filter
            let currentLinks = (data.links || []).filter(link => !isLikelyNonEnglish(link.url));
            const basicFilteredCount = totalLinks - currentLinks.length;

            // Step 2: English Variant Filter
            const { filtered: finalLinks, droppedCount: variantDroppedCount } = filterEnglishVariants(currentLinks);

            // Update data object
            data.links = finalLinks;

            console.log(`✅ Success (${duration}ms)`);
            console.log(`   Found ${totalLinks} links`);
            console.log(`   Filtered ${basicFilteredCount} non-English links (de, fr, etc.)`);
            console.log(`   Filtered ${variantDroppedCount} unwanted English variants (en-jp, etc.)`);
            console.log(`   Remaining ${finalLinks.length} links`);

            // Save result
            const outputPath = path.join(OUTPUT_DIR, `${domain.replace('.', '_')}_map.json`);
            fs.writeFileSync(outputPath, JSON.stringify(data, null, 2));
            console.log(`   Saved to ${outputPath}`);

            return {
                domain,
                success: true,
                links_count: finalLinks.length,
                original_count: totalLinks,
                filtered_count: basicFilteredCount + variantDroppedCount,
                duration,
                error: null
            };
        } else {
            console.error(`❌ Failed (${duration}ms): ${data.error}`);
            return {
                domain,
                success: false,
                links_count: 0,
                duration,
                error: data.error
            };
        }

    } catch (error) {
        const duration = Date.now() - startTime;
        console.error(`❌ Exception (${duration}ms): ${error.message}`);
        return {
            domain,
            success: false,
            links_count: 0,
            duration,
            error: error.message
        };
    }
}

async function main() {
    console.log('🚀 Starting Round 01: Map Endpoint Exploration');
    console.log('=============================================');

    const results = [];

    for (const domain of DOMAINS) {
        const result = await mapDomain(domain);
        results.push(result);
        // Small delay to avoid rate limits
        await new Promise(resolve => setTimeout(resolve, 1000));
    }

    // Save summary
    const summaryPath = path.join(OUTPUT_DIR, 'summary.json');
    fs.writeFileSync(summaryPath, JSON.stringify({
        timestamp: new Date().toISOString(),
        results
    }, null, 2));

    console.log('\n=============================================');
    console.log('🏁 Round 01 Complete');
    console.table(results);
}

main().catch(console.error);
