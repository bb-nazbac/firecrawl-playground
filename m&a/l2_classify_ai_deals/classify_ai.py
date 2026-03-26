#!/usr/bin/env python3
"""
L2 AI Classification - Web Research Based

Takes tech deals from L1, researches each company via web search,
and classifies whether they are AI/ML companies.

Usage:
    python classify_ai.py --test 100    # Sample 100 deals
    python classify_ai.py               # Full run on all tech deals
"""

import os
import sys
import json
import asyncio
import argparse
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional
import random

import pandas as pd
import aiohttp
from openai import AsyncOpenAI
from dotenv import load_dotenv

# ─── Config ────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent.parent
load_dotenv(ROOT_DIR / '.env')

DEFAULT_MODEL = "gpt-4o-mini"
SERP_CONCURRENCY = 5
LLM_CONCURRENCY = 10
SERP_RESULTS_PER_QUERY = 5

# ─── Logging Setup ─────────────────────────────────────────────────────────
def setup_logging(log_dir: Path) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    log_file = log_dir / f"classify_ai_{timestamp}.log"

    logger = logging.getLogger('l2_classify_ai')
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    fh = logging.FileHandler(log_file)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter('[%(asctime)s] %(message)s', datefmt='%H:%M:%S'))
    logger.addHandler(ch)

    return logger

# ─── SERP API ──────────────────────────────────────────────────────────────
def get_deal_type(shares_after: float) -> str:
    """Determine deal type based on percentage of shares owned after transaction."""
    if pd.isna(shares_after) or shares_after >= 100:
        return "acquisition"
    elif shares_after >= 50:
        return "majority investment"
    else:
        return "minority investment"


async def search_company(
    session: aiohttp.ClientSession,
    company_name: str,
    acquirer_name: str,
    shares_after: float,
    serp_api_key: str,
    num_results: int = 5,
) -> dict:
    """Search for company info via Serper.dev API using deal context."""

    # Clean names for search
    clean_target = company_name.replace('"', '').replace("'", "")
    clean_acquirer = acquirer_name.replace('"', '').replace("'", "") if acquirer_name else ""

    # Determine deal type
    deal_type = get_deal_type(shares_after)

    # Build query with deal context: "Target" "deal_type" by "Acquirer"
    # This surfaces acquisition articles which explain the rationale
    if clean_acquirer:
        query = f'"{clean_target}" {deal_type} by "{clean_acquirer}"'
    else:
        # Fallback if no acquirer name
        query = f'"{clean_target}" company technology products services'

    url = "https://google.serper.dev/search"
    headers = {
        "X-API-KEY": serp_api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "q": query,
        "num": num_results,
    }

    try:
        async with session.post(url, headers=headers, json=payload) as resp:
            if resp.status == 200:
                data = await resp.json()
                return {
                    "success": True,
                    "query": query,  # Include query for debugging
                    "organic": data.get("organic", []),
                    "knowledge_graph": data.get("knowledgeGraph", {}),
                }
            else:
                return {"success": False, "error": f"HTTP {resp.status}", "query": query}
    except Exception as e:
        return {"success": False, "error": str(e), "query": query}


def format_search_results(results: dict) -> str:
    """Format search results for LLM consumption."""
    if not results.get("success"):
        return f"Search failed: {results.get('error', 'Unknown error')}"

    parts = []

    # Knowledge graph
    kg = results.get("knowledge_graph", {})
    if kg:
        if kg.get("title"):
            parts.append(f"Company: {kg.get('title')}")
        if kg.get("description"):
            parts.append(f"Description: {kg.get('description')}")
        if kg.get("type"):
            parts.append(f"Type: {kg.get('type')}")

    # Organic results
    organic = results.get("organic", [])
    if organic:
        parts.append("\nSearch Results:")
        for i, result in enumerate(organic[:5], 1):
            title = result.get("title", "")
            snippet = result.get("snippet", "")
            parts.append(f"{i}. {title}")
            if snippet:
                parts.append(f"   {snippet}")

    return "\n".join(parts) if parts else "No search results found."


# ─── LLM Classification ────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are an expert at classifying software companies by their AI/ML involvement.

You are analyzing M&A deals. Given information about a TARGET COMPANY (the company being ACQUIRED),
classify the TARGET into one of four categories based on their AI/ML involvement.

IMPORTANT: Focus ONLY on the TARGET company's own products/services. Ignore information about the
ACQUIRER (the company doing the buying). Base your classification on EXPLICIT EVIDENCE only -
do not speculate or use words like "likely" or "probably".

## CRITICAL: Avoid Acquirer Contamination
Search results about acquisitions often mix information about BOTH companies. You MUST:
1. **Classify the TARGET's capabilities BEFORE the acquisition** - not the combined entity after
2. **Ignore AI features from the ACQUIRER** - if the acquirer is an AI company, that doesn't make the target an AI company
3. **Look for what the TARGET built** - not what the acquirer added after buying them

COMMON MISTAKE EXAMPLE:
- Target: "JUMP Technology" (investment management software, NO AI)
- Acquirer: "Clearwater Analytics" (has AI features)
- Search results show: "Clearwater's AI-powered platform now includes JUMP"
- WRONG: Classifying JUMP as AI because Clearwater has AI
- CORRECT: JUMP is SOFTWARE_NO_AI because JUMP itself had no AI before acquisition

ASK YOURSELF: "Did the TARGET company have this AI capability BEFORE being acquired, or was it added by the acquirer?"

## Classification Categories (choose exactly one):

### 1. PURE_PLAY_AI
AI/ML IS the PRODUCT ITSELF. The company sells AI technology, not a product enhanced by AI.
Ask: "What does this company sell?" If the answer is "AI" or an AI capability, it's Tier 1.

PURE_PLAY_AI Examples:
- Foundation model companies (OpenAI, Anthropic, Stability AI, Midjourney)
- ML platforms and tools (Hugging Face, Weights & Biases, DataRobot)
- Speech recognition/NLP companies (Nuance, TheySay sentiment analysis)
- Computer vision companies (Moodstocks image recognition, Clarifai)
- Conversational AI platforms (Ultimate.ai virtual agents, Apprento NLP)
- AI chatbot developers (companies that BUILD chatbots/voicebots as their product)
- AI drug discovery platforms (computational drug discovery companies)
- Generative AI platforms (NeuralFabric, Jasper AI)
- AI analytics engines (companies selling AI-powered analytics AS the product)

Key test: Remove the AI and nothing remains - AI IS what they sell.

### 2. SOFTWARE_WITH_EXPLICIT_AI
A software product that USES AI as a FEATURE, but would still exist without AI.
The company has a primary product category (CRM, security, healthcare records, etc.)
that is enhanced by documented AI capabilities.

SOFTWARE_WITH_EXPLICIT_AI Examples:
- Salesforce CRM with Einstein AI features (CRM first, AI added)
- Healthcare records software with AI diagnostics (health IT first, AI added)
- Fraud detection features in banking software (banking software first)
- "AI-powered" analytics in a BI dashboard (BI tool first, AI added)
- Cybersecurity platform with ML threat detection (security platform first)

Key test: Remove the AI and a viable product remains - AI is an enhancement.
Must have EXPLICIT mentions of AI/ML in product descriptions, not just speculation.

### 3. SOFTWARE_WITH_POTENTIAL_AI
Software company where AI/ML MIGHT be used but is NOT explicitly stated.
The product category suggests possible AI use, but no direct evidence.

Examples:
- Advanced analytics without explicit AI mentions
- Recommendation engines without ML documentation
- "Smart" or "intelligent" products without AI specifics
- Automation tools that could use ML but don't say so

Key: Reasonable to assume AI might be involved, but no explicit evidence found.

### 4. SOFTWARE_NO_AI
Traditional software company with no indication of AI/ML involvement.

Examples:
- Traditional SaaS, ERP, CRM without AI features
- Basic data visualization and reporting tools
- Standard e-commerce platforms
- IT consulting and services
- Hardware without AI components

## Response Format (JSON only):
{
    "ai_tier": "PURE_PLAY_AI" | "SOFTWARE_WITH_EXPLICIT_AI" | "SOFTWARE_WITH_POTENTIAL_AI" | "SOFTWARE_NO_AI",
    "ai_category": "category if tier 1 or 2, empty string otherwise",
    "confidence": "high/medium/low",
    "reasoning": "brief explanation citing specific evidence"
}

## AI Categories (for PURE_PLAY_AI and SOFTWARE_WITH_EXPLICIT_AI only):
- Generative AI (LLMs, image/video/audio generation, foundation models)
- NLP & Language AI
- Computer Vision
- Machine Learning Platforms & Tools
- AI-Powered Analytics
- Autonomous Systems & Robotics
- Healthcare AI
- AI Infrastructure (chips, training infrastructure, inference)
- Conversational AI & Chatbots
- Fraud Detection & Risk AI
- Other AI/ML

## Critical Rules:
1. Do NOT use "likely" or "probably" - if you can't confirm AI, use tier 3 or 4
2. Ask: "What does this company SELL?" If the answer is "AI technology" → PURE_PLAY_AI
3. Ask: "Could this product exist without AI?" If NO → PURE_PLAY_AI; If YES → Tier 2
4. Companies that BUILD chatbots/virtual agents = PURE_PLAY_AI (they sell AI)
5. Companies that USE chatbots for support = Tier 2 or lower (they use AI as a feature)
6. Speech recognition, NLP, computer vision, image recognition companies = almost always PURE_PLAY_AI

## BE SKEPTICAL - Common False Positives:
1. **Marketing claims are NOT evidence**: "AI company", "AI-powered", "enterprise AI" in marketing copy
   does NOT make a company Pure Play AI. Look for what they ACTUALLY SELL.
2. **Use INDUSTRY CONTEXT**: If the company is in "Ophthalmic Goods" or "Medical Equipment",
   "vision" probably means eyesight/eye care, NOT computer vision AI.
3. **"Computational" ≠ AI**: "Computational drug discovery" or "computational biology" does NOT
   automatically mean AI/ML. Many use traditional simulations, not machine learning.
4. **Knowledge management with AI features**: Companies that capture/document knowledge using AI
   transcription are NOT Pure Play AI - they sell knowledge management, AI is a feature.
5. **Biotech/pharma that "might use" AI**: Unless explicitly stated they develop AI technology
   for drug discovery, biotech companies should be Tier 2-4, not Pure Play.

## Examples to clarify the distinction:
- Nuance (speech recognition company) → PURE_PLAY_AI (they SELL speech AI)
- Ultimate.ai (builds virtual agents) → PURE_PLAY_AI (they SELL AI agents)
- Salesforce (CRM with Einstein AI) → Tier 2 (they sell CRM, AI is a feature)
- Athenahealth (EHR with AI features) → Tier 2 (they sell EHR, AI is a feature)
- "Vision Systems Inc" in Ophthalmic industry → Tier 4 (sells eye care equipment, NOT computer vision)
- "Sugarwork" knowledge management platform → Tier 2 (sells knowledge mgmt, uses AI features)
- "Chord Therapeutics" drug repurposing biotech → Tier 4 (traditional biotech, no AI evidence)"""


# ─── Verification Prompt for Pure Play AI ─────────────────────────────────────
VERIFICATION_PROMPT = """You are a strict verifier for PURE_PLAY_AI classifications. A company was classified as
PURE_PLAY_AI, meaning "AI IS their product, not a feature." Your job is to VERIFY or REJECT this classification.

## KEY PRINCIPLE: What do they SELL?
A company can focus on a specific vertical (healthcare, nutrition, finance, etc.) and STILL be Pure Play AI
if what they SELL is AI technology, models, patents, or AI capabilities - not the vertical's products.

Example: A company developing "causal-AI for personalized nutrition" that has AI patents and licenses AI
technology is PURE_PLAY_AI - they sell AI, even though it's applied to nutrition.

REJECT the PURE_PLAY_AI classification if ANY of these apply:
1. The company sells a product/service in another category (knowledge management, CRM, healthcare IT, etc.)
   that merely USES AI features
2. The company is described as an "AI company" but actually sells something else (the product is NOT AI)
3. The industry context suggests the company name is misleading (e.g., "Vision Systems" in ophthalmic/medical
   equipment industry = eye care, NOT computer vision)
4. "Computational" methods are mentioned but no specific AI/ML technology is documented
5. The company is biotech/pharma that uses computational methods but has NO explicit AI/ML patents,
   AI platforms, or AI technology products

VERIFY the PURE_PLAY_AI classification if ANY of these apply:
1. The company's PRIMARY product IS AI technology (speech recognition, NLP APIs, computer vision SDK,
   ML platforms, generative AI, chatbot builders, etc.)
2. Removing the AI would leave NO viable product
3. Customers pay specifically for AI capabilities, not for another product enhanced by AI
4. The company has AI/ML PATENTS as their primary intellectual property asset
5. The company was acquired specifically for their AI technology/IP (pre-product or early-stage)
6. The company develops AI models, algorithms, or platforms for a specific vertical (healthcare AI,
   nutrition AI, etc.) where the AI IS what they sell

Respond with JSON:
{
    "verified": true/false,
    "new_tier": "PURE_PLAY_AI" if verified, else "SOFTWARE_WITH_EXPLICIT_AI" or "SOFTWARE_NO_AI",
    "reasoning": "Brief explanation of your decision"
}"""


async def verify_pure_play(
    client: AsyncOpenAI,
    company_name: str,
    industry: str,
    original_reasoning: str,
    search_context: str,
    model: str = "gpt-4o",  # Use better model for verification
) -> dict:
    """Verify if a PURE_PLAY_AI classification is correct."""

    user_message = f"""Company: {company_name}
Industry (from M&A data): {industry}
Original classification reasoning: {original_reasoning}

Web search results:
{search_context}

Is this company TRULY Pure Play AI (AI IS the product), or should it be downgraded?"""

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": VERIFICATION_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )

        result = json.loads(response.choices[0].message.content)
        result["tokens_in"] = response.usage.prompt_tokens
        result["tokens_out"] = response.usage.completion_tokens
        return result

    except Exception as e:
        return {
            "verified": True,  # Default to keeping classification on error
            "new_tier": "PURE_PLAY_AI",
            "reasoning": f"Verification error: {str(e)}",
            "tokens_in": 0,
            "tokens_out": 0,
        }


async def classify_company(
    client: AsyncOpenAI,
    company_name: str,
    acquirer_name: str,
    tech_category: str,
    industry: str,
    search_context: str,
    model: str = DEFAULT_MODEL,
) -> dict:
    """Classify a company as AI/ML or not based on search results."""

    user_message = f"""TARGET COMPANY (being acquired): {company_name}
ACQUIRER (the buyer - IGNORE their capabilities): {acquirer_name}
Tech Category (from L1): {tech_category}
Target Industry (from M&A data): {industry}

Web Search Results about the TARGET:
{search_context}

IMPORTANT RULES:
1. Use the Target Industry to disambiguate the company. For example, if the industry is
   "Ophthalmic Goods" or "Medical Equipment", words like "vision" probably mean eyesight, not computer vision AI.
2. IGNORE any AI capabilities that belong to the ACQUIRER ({acquirer_name}). Only classify based on
   what the TARGET ({company_name}) built BEFORE being acquired.
3. If the search results describe the "combined platform" or "integrated offering" with AI features,
   ask: did {company_name} have this AI feature before acquisition, or did {acquirer_name} add it?

Based on the TARGET company's own products/services (not the acquirer), classify this company into one of the four AI tiers."""

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )

        content = response.usage
        result = json.loads(response.choices[0].message.content)
        result["tokens_in"] = response.usage.prompt_tokens
        result["tokens_out"] = response.usage.completion_tokens
        return result

    except Exception as e:
        return {
            "ai_tier": "SOFTWARE_NO_AI",
            "ai_category": "",
            "confidence": "low",
            "reasoning": f"Error: {str(e)}",
            "tokens_in": 0,
            "tokens_out": 0,
        }


# ─── Pipeline ──────────────────────────────────────────────────────────────
async def process_company(
    idx: int,
    row: pd.Series,
    session: aiohttp.ClientSession,
    openai_client: AsyncOpenAI,
    serp_api_key: str,
    serp_semaphore: asyncio.Semaphore,
    llm_semaphore: asyncio.Semaphore,
    logger: logging.Logger,
) -> dict:
    """Process a single company: search + classify."""

    company_name = row["Target Full Name"]
    acquirer_name = row.get("Acquiror Full Name", "")
    shares_after = row.get("Percentage of Shares Owned after Transaction", 100)
    tech_category = row.get("tech_category", "")
    industry = row.get("Target Mid Industry", row.get("Target Macro Industry", ""))

    # Step 1: Web search with deal context
    async with serp_semaphore:
        search_results = await search_company(
            session, company_name, acquirer_name, shares_after, serp_api_key
        )

    search_context = format_search_results(search_results)

    # Step 2: LLM classification
    async with llm_semaphore:
        classification = await classify_company(
            openai_client,
            company_name,
            acquirer_name,
            tech_category,
            industry,
            search_context,
        )

    return {
        "idx": idx,
        "target_name": company_name,
        "tech_category": tech_category,
        "search_success": search_results.get("success", False),
        "ai_tier": classification.get("ai_tier", "SOFTWARE_NO_AI"),
        "ai_category": classification.get("ai_category", ""),
        "ai_confidence": classification.get("confidence", ""),
        "ai_reasoning": classification.get("reasoning", ""),
        "tokens_in": classification.get("tokens_in", 0),
        "tokens_out": classification.get("tokens_out", 0),
    }


async def run_classification(
    input_csv: Path,
    output_dir: Path,
    test_limit: Optional[int] = None,
    logger: logging.Logger = None,
):
    """Main classification pipeline."""

    # Load data
    logger.info(f"Loading tech deals from {input_csv}")
    df = pd.read_csv(input_csv)
    logger.info(f"Loaded {len(df):,} tech deals")

    # Sample if test mode
    if test_limit:
        df = df.sample(n=min(test_limit, len(df)), random_state=42)
        logger.info(f"Sampled {len(df)} deals for test run")

    # Setup clients
    serp_api_key = os.getenv("SERP_API_KEY")
    openai_api_key = os.getenv("OPENAI_API_KEY")

    if not serp_api_key:
        raise ValueError("SERP_API_KEY not found in environment")
    if not openai_api_key:
        raise ValueError("OPENAI_API_KEY not found in environment")

    openai_client = AsyncOpenAI(api_key=openai_api_key)

    serp_semaphore = asyncio.Semaphore(SERP_CONCURRENCY)
    llm_semaphore = asyncio.Semaphore(LLM_CONCURRENCY)

    # Process companies
    results = []
    total = len(df)
    start_time = datetime.now()

    total_tokens_in = 0
    total_tokens_out = 0
    tier_counts = {
        "PURE_PLAY_AI": 0,
        "SOFTWARE_WITH_EXPLICIT_AI": 0,
        "SOFTWARE_WITH_POTENTIAL_AI": 0,
        "SOFTWARE_NO_AI": 0,
    }

    async with aiohttp.ClientSession() as session:
        tasks = []
        for idx, (_, row) in enumerate(df.iterrows()):
            task = process_company(
                idx, row, session, openai_client, serp_api_key,
                serp_semaphore, llm_semaphore, logger
            )
            tasks.append(task)

        # Process with progress
        for i, coro in enumerate(asyncio.as_completed(tasks)):
            result = await coro
            results.append(result)

            total_tokens_in += result["tokens_in"]
            total_tokens_out += result["tokens_out"]
            tier = result.get("ai_tier", "SOFTWARE_NO_AI")
            if tier in tier_counts:
                tier_counts[tier] += 1

            # Progress every 10
            if (i + 1) % 10 == 0 or (i + 1) == total:
                elapsed = (datetime.now() - start_time).total_seconds()
                rate = (i + 1) / elapsed if elapsed > 0 else 0
                pure_ai = tier_counts["PURE_PLAY_AI"]
                explicit_ai = tier_counts["SOFTWARE_WITH_EXPLICIT_AI"]
                logger.info(
                    f"  [{i+1:,}/{total:,}] Pure:{pure_ai} Explicit:{explicit_ai} | "
                    f"{rate:.1f}/s | "
                    f"Tokens: {total_tokens_in:,} in / {total_tokens_out:,} out"
                )

    # Sort by original index
    results.sort(key=lambda x: x["idx"])

    # ─── VERIFICATION STEP: Re-check PURE_PLAY_AI with GPT-4o ───────────────
    pure_play_results = [r for r in results if r.get("ai_tier") == "PURE_PLAY_AI"]
    verification_tokens_in = 0
    verification_tokens_out = 0

    if pure_play_results:
        logger.info("")
        logger.info(f"  ─── Verifying {len(pure_play_results)} PURE_PLAY_AI candidates with GPT-4o ───")

        verification_tokens_in = 0
        verification_tokens_out = 0
        downgrades = 0

        async with aiohttp.ClientSession() as verify_session:
            for i, result in enumerate(pure_play_results):
                idx = result["idx"]
                row = df.iloc[idx]
                company_name = result["target_name"]
                acquirer_name = row.get("Acquiror Full Name", "")
                shares_after = row.get("Percentage of Shares Owned after Transaction", 100)
                industry = row.get("Target Mid Industry", row.get("Target Macro Industry", ""))

                # Re-fetch search results for verification (with deal context)
                search_results = await search_company(
                    verify_session, company_name, acquirer_name, shares_after, serp_api_key
                )
                search_context = format_search_results(search_results)

                # Verify with GPT-4o
                verification = await verify_pure_play(
                    openai_client,
                    company_name,
                    industry,
                    result.get("ai_reasoning", ""),
                    search_context,
                )

                verification_tokens_in += verification.get("tokens_in", 0)
                verification_tokens_out += verification.get("tokens_out", 0)

                if not verification.get("verified", True):
                    # Downgrade the classification
                    new_tier = verification.get("new_tier", "SOFTWARE_WITH_EXPLICIT_AI")
                    old_tier = result["ai_tier"]
                    result["ai_tier"] = new_tier
                    result["ai_reasoning"] += f" [VERIFICATION: Downgraded from {old_tier} to {new_tier}: {verification.get('reasoning', '')}]"

                    # Update tier counts
                    tier_counts["PURE_PLAY_AI"] -= 1
                    if new_tier in tier_counts:
                        tier_counts[new_tier] += 1

                    downgrades += 1
                    logger.info(f"    [{i+1}/{len(pure_play_results)}] DOWNGRADED: {company_name} → {new_tier}")
                else:
                    logger.info(f"    [{i+1}/{len(pure_play_results)}] VERIFIED: {company_name}")

        logger.info(f"  Verification complete: {len(pure_play_results) - downgrades} verified, {downgrades} downgraded")
        logger.info(f"  Verification tokens: {verification_tokens_in:,} in / {verification_tokens_out:,} out")

        # Add verification costs
        total_tokens_in += verification_tokens_in
        total_tokens_out += verification_tokens_out

    # Calculate costs
    # gpt-4o-mini: $0.15/1M input, $0.60/1M output (main classification)
    # gpt-4o: $2.50/1M input, $10.00/1M output (verification - only for pure play)
    # SERP: $0.001 per search
    main_tokens_in = total_tokens_in - verification_tokens_in
    main_tokens_out = total_tokens_out - verification_tokens_out

    llm_cost_main = (main_tokens_in * 0.15 / 1_000_000) + (main_tokens_out * 0.60 / 1_000_000)
    llm_cost_verify = (verification_tokens_in * 2.50 / 1_000_000) + (verification_tokens_out * 10.00 / 1_000_000)
    llm_cost = llm_cost_main + llm_cost_verify
    serp_cost = (total + len(pure_play_results)) * 0.001  # Extra SERP calls for verification
    total_cost = llm_cost + serp_cost

    # Save results
    results_df = pd.DataFrame(results)

    suffix = f"_test_{test_limit}" if test_limit else ""
    output_csv = output_dir / f"ai_classified{suffix}.csv"
    results_df.to_csv(output_csv, index=False)

    # Merge with original data for AI tiers (Pure Play + Explicit AI)
    df_indexed = df.reset_index(drop=True)

    # Create output for top 2 tiers (Pure Play AI + Explicit AI)
    ai_tiers_top2 = ["PURE_PLAY_AI", "SOFTWARE_WITH_EXPLICIT_AI"]
    ai_indices = [r["idx"] for r in results if r.get("ai_tier") in ai_tiers_top2]
    ai_full = df_indexed.iloc[ai_indices].copy() if ai_indices else pd.DataFrame()

    # Add AI classification columns
    ai_results_dict = {r["idx"]: r for r in results if r.get("ai_tier") in ai_tiers_top2}
    if not ai_full.empty:
        ai_full["ai_tier"] = ai_full.index.map(lambda i: ai_results_dict.get(i, {}).get("ai_tier", ""))
        ai_full["ai_category"] = ai_full.index.map(lambda i: ai_results_dict.get(i, {}).get("ai_category", ""))
        ai_full["ai_confidence"] = ai_full.index.map(lambda i: ai_results_dict.get(i, {}).get("ai_confidence", ""))
        ai_full["ai_reasoning"] = ai_full.index.map(lambda i: ai_results_dict.get(i, {}).get("ai_reasoning", ""))

    ai_only_csv = output_dir / f"ai_deals_only{suffix}.csv"
    ai_full.to_csv(ai_only_csv, index=False)

    # Stats
    duration = (datetime.now() - start_time).total_seconds()
    ai_related = tier_counts["PURE_PLAY_AI"] + tier_counts["SOFTWARE_WITH_EXPLICIT_AI"]
    stats = {
        "timestamp": datetime.now().isoformat(),
        "total_processed": total,
        "tier_counts": tier_counts,
        "pure_play_ai": tier_counts["PURE_PLAY_AI"],
        "software_with_explicit_ai": tier_counts["SOFTWARE_WITH_EXPLICIT_AI"],
        "software_with_potential_ai": tier_counts["SOFTWARE_WITH_POTENTIAL_AI"],
        "software_no_ai": tier_counts["SOFTWARE_NO_AI"],
        "ai_related_total": ai_related,
        "ai_related_percentage": round(100 * ai_related / total, 2) if total > 0 else 0,
        "duration_seconds": round(duration, 1),
        "tokens_in": total_tokens_in,
        "tokens_out": total_tokens_out,
        "cost_llm": round(llm_cost, 4),
        "cost_serp": round(serp_cost, 4),
        "cost_total": round(total_cost, 4),
        "output_all": str(output_csv),
        "output_ai_only": str(ai_only_csv),
    }

    stats_file = output_dir / f"classify_ai_stats{suffix}.json"
    with open(stats_file, 'w') as f:
        json.dump(stats, f, indent=2)

    logger.info("")
    logger.info("=" * 60)
    logger.info("CLASSIFICATION COMPLETE")
    logger.info("=" * 60)
    logger.info(f"  Total processed:      {total:,}")
    logger.info(f"  ─── AI Tiers ───")
    logger.info(f"  Pure Play AI:         {tier_counts['PURE_PLAY_AI']:,}")
    logger.info(f"  Explicit AI Features: {tier_counts['SOFTWARE_WITH_EXPLICIT_AI']:,}")
    logger.info(f"  Potential AI:         {tier_counts['SOFTWARE_WITH_POTENTIAL_AI']:,}")
    logger.info(f"  No AI:                {tier_counts['SOFTWARE_NO_AI']:,}")
    logger.info(f"  ─── Summary ───")
    logger.info(f"  AI-related (T1+T2):   {ai_related:,} ({stats['ai_related_percentage']:.1f}%)")
    logger.info(f"  Duration:             {duration:.1f}s")
    logger.info(f"  LLM cost:             ${llm_cost:.4f}")
    logger.info(f"  SERP cost:            ${serp_cost:.4f}")
    logger.info(f"  Total cost:           ${total_cost:.4f}")
    logger.info(f"  Output:               {output_csv}")
    logger.info("=" * 60)

    return stats


# ─── Main ──────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="L2 AI Classification via Web Research")
    parser.add_argument("--test", type=int, help="Limit to N deals for testing")
    parser.add_argument("--input", type=str, help="Input CSV (default: tech_deals_only.csv)")
    args = parser.parse_args()

    # Paths
    input_csv = Path(args.input) if args.input else SCRIPT_DIR.parent / "outputs" / "tech_deals_only.csv"
    output_dir = SCRIPT_DIR.parent / "outputs"
    log_dir = SCRIPT_DIR.parent / "logs" / "l2_classify_ai"

    logger = setup_logging(log_dir)

    logger.info("=" * 60)
    logger.info("L2 AI CLASSIFICATION - Web Research Based")
    logger.info("=" * 60)
    logger.info(f"Input:  {input_csv}")
    logger.info(f"Output: {output_dir}")
    if args.test:
        logger.info(f"Mode:   TEST ({args.test} deals)")
    else:
        logger.info("Mode:   FULL RUN")
    logger.info("=" * 60)

    asyncio.run(run_classification(
        input_csv=input_csv,
        output_dir=output_dir,
        test_limit=args.test,
        logger=logger,
    ))


if __name__ == "__main__":
    main()
