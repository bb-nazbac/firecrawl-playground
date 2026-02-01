# L2 Iterative Qualification Layer

## Purpose

Iteratively qualify companies by:
1. Scraping homepage first
2. Asking Claude if enough information exists
3. If not, Claude selects additional pages from the map
4. Repeat until confident or max pages reached

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  ROUND 0: Homepage                                          │
│  ─────────────────────────────────────────────────────────  │
│  1. Scrape homepage (1 credit)                              │
│  2. Feed to Claude with qualification questions             │
│  3. Claude assesses: "Do I have enough info?"               │
│     → YES: Return qualification result                      │
│     → NO: Proceed to Round 1                                │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  ROUND 1: First Expansion                                   │
│  ─────────────────────────────────────────────────────────  │
│  1. Claude selects 5 pages from map                         │
│  2. Scrape selected pages (5 credits)                       │
│  3. Feed ALL content to Claude                              │
│  4. Claude assesses: "Do I have enough info now?"           │
│     → YES: Return qualification result                      │
│     → NO: Proceed to Round 2 (FINAL)                        │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  ROUND 2: Final Expansion                                   │
│  ─────────────────────────────────────────────────────────  │
│  1. Claude selects 5 MORE pages from map                    │
│  2. Scrape selected pages (5 credits)                       │
│  3. Feed ALL content to Claude                              │
│  4. Force qualification with available info                 │
└─────────────────────────────────────────────────────────────┘
```

## Page Selection Strategy

When Claude needs more information, it selects pages based on:
1. **Relevance to questions**: Pages likely to contain qualification answers
2. **Page type priority**: About > Products/Services > Contact > Other
3. **URL patterns**: `/about`, `/products`, `/services`, `/what-we-do`

## Files

- `qualify_domain.py` - Main qualification logic (TO BE IMPLEMENTED)
- `page_selector.py` - Claude-based page selection (TO BE IMPLEMENTED)
- `prompts.py` - Prompt templates (TO BE IMPLEMENTED)

## Status

🚧 **IN DEVELOPMENT** - Awaiting L1 validation and user input on qualification questions
