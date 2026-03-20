"""
Trend Projection Branch Agent
Analyses historical scoring data to project future trends and provide
data-driven recommendations based on scoring trajectory.
"""
from __future__ import annotations

import json
import logging
import time
from config import OPENAI_MODEL
from models.schemas import BrandInput
from agents.llm_client import logged_chat_completion
from scoring_history import get_score_history

log = logging.getLogger("sitescore.branch.trend_projection")


async def project_trends(
    brand_input: BrandInput,
    current_score: float,
) -> dict:
    """Analyse historical scores and project future trends."""
    history = await get_score_history(brand_input.brand_name, limit=20)

    if len(history) < 2:
        return {
            "has_history": False,
            "message": f"Insufficient history for {brand_input.brand_name}. Run more evaluations to enable trend projection.",
            "current_score": current_score,
            "data_points": len(history),
        }

    # Build history context for LLM
    history_context = "\n".join(
        f"  {h['created_at']}: score={h['overall_score']:.1f}, tagline=\"{h['tagline'][:60]}\""
        for h in reversed(history)  # oldest first
    )

    prompt = f"""You are a predictive analytics specialist for marketing performance.

Analyse the following scoring history for a brand and project future trends.

BRAND: {brand_input.brand_name}
CATEGORY: {brand_input.product_category}
CURRENT SCORE: {current_score}/10

SCORING HISTORY (oldest to newest):
{history_context}

Analyse:
1. Score trajectory (improving, declining, plateau)
2. Rate of change
3. Projected score for next evaluation
4. Key inflection points
5. Recommendations based on the trend

Return a JSON object:
{{
  "has_history": true,
  "trajectory": "improving | declining | plateau | volatile",
  "rate_of_change": <float per evaluation>,
  "projected_next_score": <float>,
  "confidence": <0.0-1.0>,
  "inflection_points": ["description of key changes"],
  "trend_summary": "1-2 sentence summary of the brand's scoring trajectory",
  "recommendations": ["data-driven recommendation 1", "recommendation 2"],
  "score_history": [
    {{"date": "ISO date", "score": <float>}}
  ]
}}

Return ONLY valid JSON."""

    response = await logged_chat_completion(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        response_format={"type": "json_object"},
        caller="trend_projection.project",
    )
    return json.loads(response.choices[0].message.content)


async def trend_projection_node(state: dict) -> dict:
    """LangGraph node: projects scoring trends from historical data."""
    log.info("⚙ trend_projection_node ENTER")
    t0 = time.perf_counter()
    brand_input = BrandInput(**state["brand_input"]) if isinstance(state["brand_input"], dict) else state["brand_input"]
    evaluation = state.get("evaluation")
    current_score = 0.0
    if evaluation:
        if isinstance(evaluation, dict):
            current_score = evaluation.get("user_score", {}).get("overall_score", 0.0)
        else:
            current_score = evaluation.user_score.overall_score
    result = await project_trends(brand_input, current_score)
    log.info("⚙ trend_projection_node EXIT  %.1fs  has_history=%s", time.perf_counter() - t0, result.get("has_history"))
    return {"trend_projection_data": result}
