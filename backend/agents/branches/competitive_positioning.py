"""
Competitive Positioning Branch Agent
Maps the competitive landscape as a positioning matrix, identifying whitespace
opportunities and overlapping positioning dangers.
"""
from __future__ import annotations

import json
import logging
import time
from config import OPENAI_MODEL
from models.schemas import BrandInput, EvaluationResult
from agents.llm_client import logged_chat_completion

log = logging.getLogger("sitescore.branch.positioning")


async def analyze_positioning(
    brand_input: BrandInput,
    evaluation: EvaluationResult,
) -> dict:
    """Map competitive positioning and identify whitespace."""
    rankings = "\n".join(
        f"- {r['brand']}: score {r['score']}/10 (rank #{r['rank']})"
        for r in evaluation.rankings
    )
    insights = "\n".join(f"- {i}" for i in evaluation.insights)

    prompt = f"""You are a strategic brand positioning expert.

Using the evaluation data below, create a competitive positioning analysis.

BRAND: {brand_input.brand_name}
CATEGORY: {brand_input.product_category}
TARGET AUDIENCE: {brand_input.target_audience or "General consumer"}

RANKINGS:
{rankings}

EVALUATION INSIGHTS:
{insights}

Return a JSON object:
{{
  "positioning_map": [
    {{
      "brand": "BrandName",
      "x_axis": "Rational ← → Emotional",
      "y_axis": "Premium ← → Mass Market",
      "x_value": <-5 to 5>,
      "y_value": <-5 to 5>,
      "positioning_statement": "Their core position"
    }}
  ],
  "whitespace_opportunities": ["area 1 with no competitor presence", "area 2"],
  "overlap_dangers": ["where multiple brands compete for the same position"],
  "recommended_position": "Where {brand_input.brand_name} should position for maximum differentiation"
}}

Return ONLY valid JSON."""

    response = await logged_chat_completion(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        response_format={"type": "json_object"},
        caller="positioning.analyze",
    )
    return json.loads(response.choices[0].message.content)


async def competitive_positioning_node(state: dict) -> dict:
    """LangGraph node: competitive positioning analysis."""
    log.info("⚙ competitive_positioning_node ENTER")
    t0 = time.perf_counter()
    brand_input = BrandInput(**state["brand_input"]) if isinstance(state["brand_input"], dict) else state["brand_input"]
    evaluation = state["evaluation"]
    if isinstance(evaluation, dict):
        evaluation = EvaluationResult(**evaluation)
    result = await analyze_positioning(brand_input, evaluation)
    log.info("⚙ competitive_positioning_node EXIT  %.1fs", time.perf_counter() - t0)
    return {"positioning_data": result}
