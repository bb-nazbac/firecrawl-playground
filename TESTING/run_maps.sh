#!/bin/bash

API_KEY="REDACTED_API_KEY"

# Array of URLs to map
declare -a urls=(
    "https://phccconnect2025.eventscribe.net"
    "https://phccconnect2025.eventscribe.net/SearchByExpoCompany.asp"
    "https://phccconnect2025.eventscribe.net/aaStatic.asp"
    "https://phccconnect2025.eventscribe.net/ajaxcalls/ExhibitorInfo.asp"
    "https://phccconnect2025.eventscribe.net/agenda.asp"
    "https://phccconnect2025.eventscribe.net/login.asp"
)

declare -a names=(
    "map_1_home"
    "map_2_exhibitors"
    "map_3_companion"
    "map_4_exhibitorinfo"
    "map_5_schedule"
    "map_6_login"
)

# Run map on each URL
for i in "${!urls[@]}"; do
    echo "Mapping: ${urls[$i]}"
    curl -s -X POST https://api.firecrawl.dev/v2/map \
        -H "Authorization: Bearer ${API_KEY}" \
        -H "Content-Type: application/json" \
        -d "{\"url\": \"${urls[$i]}\"}" \
        | jq '.' > "TESTING/${names[$i]}.json"
    echo "Saved to TESTING/${names[$i]}.json"
    echo ""
done

echo "All done!"
