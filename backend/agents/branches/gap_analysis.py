"""
Gap Analysis Branch Agent
Identifies specific score gaps between the user's brand and competitors,
pinpointing the most impactful dimensions to improve.
"""
from __future__ import annotations

import json
import logging
import time
from config import OPENAI_MODEL
from models.schemas import BrandInput, EvaluationResult
from agents.llm_client import logged_chat_completion

log = logging.getLogger("sitescore.branch.gap_analysis")


async def analyze_gaps(
    brand_input: BrandInput,
    evaluation: EvaluationResult,
) -> dict:
    """Identify and prioritise score gaps between user and competitors."""
    user = evaluation.user_score
    user_dims = {ds.dimension: ds.score for ds in user.dimension_scores}

    # Build competitor comparison
    comp_data = []
    for cs in evaluation.competitor_scores:
        comp_dims = {ds.dimension: ds.score for ds in cs.dimension_scores}
        comp_data.append({"name": cs.brand_name, "overall": cs.overall_score, "dims": comp_dims})

    gap_table = []
    for dim, user_score in user_dims.items():
        best_comp = max((c["dims"].get(dim, 0) for c in comp_data), default=0)
        gap_table.append({"dimension": dim, "user": user_score, "best_competitor": best_comp, "gap": round(best_comp - user_score, 1)})

    gap_table.sort(key=lambda x: x["gap"], reverse=True)

    prompt = f"""You are a competitive gap analyst. Given the score gap data below, provide strategic prioritisation.

BRAND: {brand_input.brand_name} (overall: {user.overall_score}/10)
COMPETITORS: {', '.join(c['name'] + ' (' + str(c['overall']) + ')' for c in comp_data)}

SCORE GAPS (user vs best competitor per dimension):
{json.dumps(gap_table, indent=2)}

Return a JSON object:
{{
  "priority_gaps": [
    {{
      "dimension": "DimName",
      "user_score": <float>,
      "best_competitor_score": <float>,
      "gap": <float>,
      "impact": "high | medium | low",
      "recommendation": "What to focus on"
    }}
  ],
  "quick_wins": ["dimensions where small effort yields big score gains"],
  "strategic_moats": ["dimensions where user already leads"]
}}

Return ONLY valid JSON."""

    response = await logged_chat_completion(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        response_format={"type": "json_object"},
        caller="gap_analysis.analyze",
    )
    return json.loads(response.choices[0].message.content)


async def gap_analysis_node(state: dict) -> dict:
    """LangGraph node: competitive gap analysis."""
    log.info("⚙ gap_analysis_node ENTER")
    t0 = time.perf_counter()
    brand_input = BrandInput(**state["brand_input"]) if isinstance(state["brand_input"], dict) else state["brand_input"]
    evaluation = state["evaluation"]
    if isinstance(evaluation, dict):
        evaluation = EvaluationResult(**evaluation)
    result = await analyze_gaps(brand_input, evaluation)
    log.info("⚙ gap_analysis_node EXIT  %.1fs", time.perf_counter() - t0)
    return {"gap_analysis_data": result}
