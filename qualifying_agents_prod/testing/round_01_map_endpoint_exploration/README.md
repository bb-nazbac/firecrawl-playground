# Round 01: Map Endpoint Exploration

**Objective**: Validate the Firecrawl `/map` endpoint for discovering high-value pages.

## Goals
1. Verify `/map` returns a comprehensive list of URLs.
2. Check if key pages (`/pricing`, `/about`, `/team`) are consistently found.
3. Measure latency and cost of the `/map` endpoint.

## Structure
- `l1_map_exploration/`: Scripts to call the map endpoint.
- `inputs/`: List of domains to test.
- `outputs/`: Raw JSON responses from Firecrawl.
- `logs/`: Execution logs.

## Usage
```bash
# Run the exploration script
npx ts-node qualifying_agents_prod/testing/round_01_map_endpoint_exploration/l1_map_exploration/map_domains.ts
```
