"""
Audience Resonance Branch Agent
Maps how well each brand's messaging resonates with the target audience segments.
"""
from __future__ import annotations

import json
import logging
import time
from config import OPENAI_MODEL
from models.schemas import BrandInput, CompetitorAnalysisResult
from agents.llm_client import logged_chat_completion

log = logging.getLogger("sitescore.branch.audience_resonance")


async def analyze_audience_resonance(
    brand_input: BrandInput,
    competitor_result: CompetitorAnalysisResult,
) -> dict:
    """Analyse audience resonance for brand and competitors."""
    comp_context = "\n".join(
        f'- {c.name}: "{c.tagline}" (targeting: {c.market_position})' for c in competitor_result.competitors
    )

    prompt = f"""You are a consumer psychology expert specialising in message-audience fit.

Analyse how well each brand's tagline resonates with its target audience. Consider emotional triggers, cultural relevance, lifestyle alignment, and generational preferences.

BRAND: {brand_input.brand_name}
TAGLINE: "{brand_input.current_tagline}"
CATEGORY: {brand_input.product_category}
TARGET AUDIENCE: {brand_input.target_audience or "General consumer"}

COMPETITORS:
{comp_context}

Return a JSON object:
{{
  "brand_resonance": {{
    "resonance_score": <0-10>,
    "emotional_triggers": ["trigger 1", "trigger 2"],
    "audience_alignment": "How well the message matches audience values",
    "cultural_relevance": "Cultural context analysis"
  }},
  "competitor_resonance": [
    {{
      "name": "CompetitorName",
      "resonance_score": <0-10>,
      "emotional_triggers": ["..."],
      "audience_alignment": "..."
    }}
  ],
  "resonance_insights": ["insight 1", "insight 2"]
}}

Return ONLY valid JSON."""

    response = await logged_chat_completion(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        response_format={"type": "json_object"},
        caller="audience_resonance.analyze",
    )
    return json.loads(response.choices[0].message.content)


async def audience_resonance_node(state: dict) -> dict:
    """LangGraph node: analyses audience resonance."""
    log.info("⚙ audience_resonance_node ENTER")
    t0 = time.perf_counter()
    brand_input = BrandInput(**state["brand_input"]) if isinstance(state["brand_input"], dict) else state["brand_input"]
    competitor_result = state["competitor_result"]
    if isinstance(competitor_result, dict):
        competitor_result = CompetitorAnalysisResult(**competitor_result)
    result = await analyze_audience_resonance(brand_input, competitor_result)
    log.info("⚙ audience_resonance_node EXIT  %.1fs", time.perf_counter() - t0)
    return {"audience_resonance_data": result}
