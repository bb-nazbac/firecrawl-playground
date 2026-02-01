import fs from 'fs';
import path from 'path';
import https from 'https';

// Simple .env parser since we might not have dotenv
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
    'stripe.com',
    'linear.app',
    'openai.com',
    'vercel.com'
];

const OUTPUT_DIR = path.resolve(__dirname, '../outputs');
const LOG_DIR = path.resolve(__dirname, '../logs/l1_map_exploration');

// Ensure directories exist
if (!fs.existsSync(OUTPUT_DIR)) fs.mkdirSync(OUTPUT_DIR, { recursive: true });
if (!fs.existsSync(LOG_DIR)) fs.mkdirSync(LOG_DIR, { recursive: true });

async function mapDomain(domain: string) {
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
                search: "pricing about team contact", // Optional: search query to filter? No, let's get all first.
                // Actually, let's try WITHOUT search first to see full map, 
                // or maybe we WANT to test if search works?
                // The prompt said "Map-then-Qualify", implying we get the map and THEN select.
                // So let's get the full map (or default limit).
                limit: 5000
            })
        });

        const data = await response.json();
        const duration = Date.now() - startTime;

        if (data.success) {
            console.log(`✅ Success (${duration}ms)`);
            console.log(`   Found ${data.links?.length || 0} links`);
            
            // Save result
            const outputPath = path.join(OUTPUT_DIR, `${domain.replace('.', '_')}_map.json`);
            fs.writeFileSync(outputPath, JSON.stringify(data, null, 2));
            console.log(`   Saved to ${outputPath}`);
            
            return {
                domain,
                success: true,
                links_count: data.links?.length || 0,
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

    } catch (error: any) {
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
