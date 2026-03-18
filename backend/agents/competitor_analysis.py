"""
Competitor Analysis Agent
Retrieves and contextualizes the top 3 market competitors.
"""
import json
import logging
import time
from config import OPENAI_MODEL
from models.schemas import BrandInput, Competitor, CompetitorAnalysisResult
from data.seed_competitors import get_competitors
from agents.llm_client import get_openai_client, logged_chat_completion

log = logging.getLogger("sitescore.agent.competitors")


async def analyze_competitors(brand_input: BrandInput) -> CompetitorAnalysisResult:
    """Return competitor analysis -- uses seed data enriched by LLM market summary."""

    seed = get_competitors(brand_input.brand_name, brand_input.product_category)

    if seed:
        competitors = [Competitor(**c) for c in seed]
    else:
        # Fallback: ask the LLM to generate plausible competitors
        competitors = await _llm_generate_competitors(brand_input)

    # Generate a strategic market summary via LLM
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


async def _llm_generate_competitors(brand_input: BrandInput) -> list[Competitor]:
    prompt = f"""You are a marketing competitive intelligence analyst.
Given the following brand and product, identify the top 3 direct market competitors.

Brand: {brand_input.brand_name}
Category: {brand_input.product_category}
Current Tagline: {brand_input.current_tagline}
Target Audience: {brand_input.target_audience}

Return a JSON object with a "competitors" key containing an array of exactly 3 objects, each having:
- name: competitor brand name
- product: specific product name
- tagline: their current marketing tagline
- description: 2-sentence product description
- market_position: one sentence on their market standing

Return ONLY valid JSON, no markdown."""

    response = await logged_chat_completion(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        response_format={"type": "json_object"},
        caller="competitors.generate",
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
