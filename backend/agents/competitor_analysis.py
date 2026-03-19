"""
Competitor Analysis Agent
Discovers and contextualizes the top 3 market competitors using LLM intelligence.
Fully agentic — no hardcoded seed data.
"""
import json
import logging
import time
from config import OPENAI_MODEL
from models.schemas import BrandInput, Competitor, CompetitorAnalysisResult
from agents.llm_client import logged_chat_completion

log = logging.getLogger("sitescore.agent.competitors")


async def analyze_competitors(brand_input: BrandInput) -> CompetitorAnalysisResult:
    """Discover competitors via LLM and generate a strategic market summary."""

    competitors = await _discover_competitors(brand_input)
    market_summary = await _generate_market_summary(brand_input, competitors)

    return CompetitorAnalysisResult(
        competitors=competitors,
        market_summary=market_summary,
    )


# ── LangGraph node wrapper ────────────────────────────────────
async def competitor_analysis_node(state: dict) -> dict:
    """LangGraph node: runs competitor analysis and returns result."""
    log.info("⚙ competitor_analysis_node ENTER")
    t0 = time.perf_counter()
    brand_input = BrandInput(**state["brand_input"]) if isinstance(state["brand_input"], dict) else state["brand_input"]
    result = await analyze_competitors(brand_input)
    log.info("⚙ competitor_analysis_node EXIT  %.1fs  competitors=%d", time.perf_counter() - t0, len(result.competitors))
    return {"competitor_result": result}


async def _discover_competitors(brand_input: BrandInput) -> list[Competitor]:
    """Use GPT-4o to identify the top 3 direct market competitors."""
    prompt = f"""You are a marketing competitive intelligence analyst with deep knowledge of global brands and market dynamics.

Given the following brand and product category, identify the top 3 REAL direct market competitors. Use your knowledge of actual brands, their real taglines, real products, and real market positions.

Brand: {brand_input.brand_name}
Category: {brand_input.product_category}
Current Tagline: "{brand_input.current_tagline}"
Target Audience: {brand_input.target_audience or "General consumer"}

Return a JSON object with a "competitors" key containing an array of exactly 3 objects, each having:
- name: the real competitor brand name
- product: their specific flagship product in this category
- tagline: their actual current marketing tagline (must be real, not invented)
- description: 2-sentence product description with real details
- market_position: one sentence on their actual market standing (include real metrics like market share, revenue, or store count where possible)

IMPORTANT: Use REAL brands with REAL taglines and REAL market data. Do not invent fictional competitors.

Return ONLY valid JSON, no markdown."""

    response = await logged_chat_completion(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        response_format={"type": "json_object"},
        caller="competitors.discover",
    )
    data = json.loads(response.choices[0].message.content)
    items = data if isinstance(data, list) else data.get("competitors", [])
    return [Competitor(**c) for c in items[:3]]


async def _generate_market_summary(
    brand_input: BrandInput, competitors: list[Competitor]
) -> str:
    comp_info = "\n".join(
        f'- {c.name} ({c.product}): "{c.tagline}" -- {c.market_position}'
        for c in competitors
    )
    prompt = f"""You are a senior marketing strategist. Write a concise 3-sentence competitive landscape summary.

Brand being analyzed: {brand_input.brand_name} ({brand_input.product_category})
Their tagline: "{brand_input.current_tagline}"

Top competitors:
{comp_info}

Focus on positioning gaps and strategic opportunities. Be specific and data-oriented."""

    response = await logged_chat_completion(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
        max_tokens=300,
        caller="competitors.summary",
    )
    return response.choices[0].message.content.strip()
