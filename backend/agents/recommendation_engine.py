"""
Recommendation Engine Agent (Agent 7)
Generates prioritized, actionable recommendations with specific copy,
competitive evidence, and expected impact.
"""
from __future__ import annotations

import json
import logging
import time
from config import OPENAI_MODEL
from models.schemas import (
    ListingScore,
    CompetitorAnalysis,
    ParsedListing,
    ScoringRubric,
    Recommendation,
    RecommendationResult,
)
from agents.llm_client import logged_chat_completion

log = logging.getLogger("listingiq.agent.recommendation_engine")


async def generate_recommendations(
    scores: ListingScore,
    competitor_analysis: CompetitorAnalysis,
    parsed_listing: ParsedListing,
    rubric: ScoringRubric,
) -> RecommendationResult:
    """Generate prioritized recommendations with specific actionable copy."""

    # Build scores context
    scores_text = ""
    for ds in scores.dimension_scores:
        scores_text += f"\n  - {ds.dimension}: {ds.score}/10 (competitor avg: {ds.competitor_avg}, gap: {ds.gap})"
        if ds.weaknesses:
            scores_text += f"\n    Weaknesses: {', '.join(ds.weaknesses)}"

    # Build competitive context
    kw_missing = []
    for kp in competitor_analysis.keyword_patterns:
        if kp.frequency >= 6:
            kw_missing.append(f"'{kp.keyword}' ({kp.frequency}/10 competitors use it)")

    claims_missing = []
    for cp in competitor_analysis.claim_patterns:
        if cp.frequency >= 5:
            claims_missing.append(f"'{cp.claim}' ({cp.frequency}/10 competitors make this claim)")

    # Current listing
    bullets_text = "\n".join(f"  - {b}" for b in parsed_listing.original_bullets) if parsed_listing.original_bullets else "  (no bullets)"

    prompt = f"""You are an ecommerce listing optimization expert. Generate specific, actionable recommendations to improve this product listing.

CURRENT LISTING:
  Title: {parsed_listing.original_title}
  Bullets:
{bullets_text}
  Description: {parsed_listing.original_description[:300] or '(none)'}

CURRENT SCORES (overall: {scores.overall_score}/10, percentile: {scores.percentile}):
{scores_text}

GAP ANALYSIS (sorted by impact):
{json.dumps(scores.gap_analysis[:8], indent=2)}

COMPETITIVE INTELLIGENCE:
  High-frequency keywords you're missing: {'; '.join(kw_missing[:8]) or 'None major'}
  Common claims you're missing: {'; '.join(claims_missing[:8]) or 'None major'}
  Differentiation insights: {'; '.join(competitor_analysis.differentiation_insights[:5])}

TASK: Generate specific recommendations. Each recommendation must include:
1. The exact dimension being targeted
2. Current score and projected score after implementing
3. Impact level (high/medium/low)
4. SPECIFIC COPY to add or change — not vague advice, but actual text the brand can copy-paste
5. Competitive evidence justifying why this matters
6. Expected lift description

Prioritize by impact (gap_size × weight). Generate 5-8 recommendations total.

Also separate into:
- quick_wins: 2-3 easiest improvements (small effort, meaningful impact)
- strategic_moves: 2-3 bigger improvements (more effort, larger impact)

Return a JSON object:
{{
  "recommendations": [
    {{
      "priority": 1,
      "dimension": "Form Specificity",
      "current_score": 3.5,
      "projected_score": 7.0,
      "impact": "high",
      "specific_copy": "Add to bullet: 'Magnesium Glycinate (chelated) — the most bioavailable and gentle form, absorbed 2x better than magnesium oxide with zero digestive discomfort'",
      "competitive_evidence": "9/10 top competitors explain their magnesium form and its benefits",
      "expected_lift": "+3.5 points on Form Specificity, contributing +0.53 to overall score"
    }}
  ],
  "quick_wins": [{{...}}],
  "strategic_moves": [{{...}}]
}}

Return ONLY valid JSON."""

    response = await logged_chat_completion(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        response_format={"type": "json_object"},
        caller="recommendation_engine.generate",
    )
    data = json.loads(response.choices[0].message.content)

    recommendations = [Recommendation(**r) for r in data.get("recommendations", [])]
    quick_wins = [Recommendation(**r) for r in data.get("quick_wins", [])]
    strategic_moves = [Recommendation(**r) for r in data.get("strategic_moves", [])]

    return RecommendationResult(
        recommendations=recommendations,
        quick_wins=quick_wins,
        strategic_moves=strategic_moves,
    )


# ── LangGraph node wrapper ────────────────────────────────────
async def recommendation_engine_node(state: dict) -> dict:
    """LangGraph node: generates prioritized recommendations."""
    log.info("⚙ recommendation_engine_node ENTER")
    t0 = time.perf_counter()

    scores = state["scores"]
    if isinstance(scores, dict):
        scores = ListingScore(**scores)

    competitor_analysis = state["competitor_analysis"]
    if isinstance(competitor_analysis, dict):
        competitor_analysis = CompetitorAnalysis(**competitor_analysis)

    parsed = state["parsed_listing"]
    if isinstance(parsed, dict):
        parsed = ParsedListing(**parsed)

    rubric = state["rubric"]
    if isinstance(rubric, dict):
        rubric = ScoringRubric(**rubric)

    result = await generate_recommendations(scores, competitor_analysis, parsed, rubric)
    log.info(
        "⚙ recommendation_engine_node EXIT  %.1fs  total=%d  quick_wins=%d  strategic=%d",
        time.perf_counter() - t0,
        len(result.recommendations),
        len(result.quick_wins),
        len(result.strategic_moves),
    )
    return {"recommendations": result}
