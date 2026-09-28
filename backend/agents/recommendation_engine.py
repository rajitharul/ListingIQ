"""
Recommendation Engine Agent (Agent 7)
Generates prioritized, actionable recommendations with specific copy,
competitive evidence, and expected impact.
"""
from __future__ import annotations

import json
import logging
import time
from models.schemas import (
    ListingScore,
    CompetitorAnalysis,
    ParsedListing,
    ScoringRubric,
    Recommendation,
    RecommendationResult,
)
from models.llm_responses import RecommendationResultOut, clamp
from agents.llm_client import structured_completion

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

    # Thresholds are proportional, not absolute. "6 competitors do this" was a
    # majority when the set was always 10; against a set of 7 it is a
    # supermajority, and against a set of 20 it is a minority being reported to
    # the customer as what the market does.
    n_competitors = int(
        (competitor_analysis.structural_patterns or {}).get("listings_counted") or 0
    ) or 10

    kw_missing = []
    for kp in competitor_analysis.keyword_patterns:
        if kp.frequency >= 0.6 * n_competitors:
            kw_missing.append(
                f"'{kp.keyword}' ({kp.frequency}/{n_competitors} competitors use it)")

    claims_missing = []
    for cp in competitor_analysis.claim_patterns:
        if cp.frequency >= 0.5 * n_competitors:
            claims_missing.append(
                f"'{cp.claim}' ({cp.frequency}/{n_competitors} competitors make this claim)")

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
5. evidence_pattern: the exact keyword, claim or trust signal from COMPETITIVE
   CONTEXT above that justifies this, copied verbatim. Do NOT write a sentence
   and do NOT state any count — the frequency is measured and added afterwards.
   Leave it empty if no listed pattern applies.
6. Expected lift description

Prioritize by impact (gap_size × weight). Generate 5-8 recommendations total.

Also separate into:
- quick_wins: 2-3 easiest improvements (small effort, meaningful impact)
- strategic_moves: 2-3 bigger improvements (more effort, larger impact)

Set impact to exactly one of: high, medium, low. Scores run from 0.0 to 10.0.
quick_wins and strategic_moves each re-state entries drawn from recommendations."""

    out = await structured_completion(
        response_model=RecommendationResultOut,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_completion_tokens=6000,
        caller="recommendation_engine.generate",
    )

    # Every counted pattern, keyed by its own text, so the model's attribution
    # can be resolved to a real frequency instead of a written-out one.
    counted: dict[str, tuple[int, str]] = {}
    for kp in competitor_analysis.keyword_patterns:
        counted[kp.keyword.strip().casefold()] = (kp.frequency, f"use '{kp.keyword}'")
    for cp in competitor_analysis.claim_patterns:
        counted[cp.claim.strip().casefold()] = (cp.frequency, f"make the claim '{cp.claim}'")
    for ts in competitor_analysis.trust_signals:
        sig = str(ts.get("signal", "")).strip()
        if sig:
            counted[sig.casefold()] = (int(ts.get("frequency", 0)), f"show '{sig}'")

    def _evidence(pattern: str) -> str:
        """
        Turn the model's attribution into a counted sentence, or nothing.

        A pattern the model names but Python never counted produces no evidence
        at all. Silence is correct here: an unverifiable claim quoted to a
        customer as market evidence is worse than no claim.
        """
        hit = counted.get((pattern or "").strip().casefold())
        if not hit or hit[0] <= 0 or n_competitors <= 0:
            return ""
        freq, phrase = hit
        return f"{freq} of {n_competitors} analysed competitors {phrase}"

    def _to_domain(r) -> Recommendation:
        return Recommendation(
            priority=r.priority,
            dimension=r.dimension,
            current_score=clamp(r.current_score, 0.0, 10.0),
            projected_score=clamp(r.projected_score, 0.0, 10.0),
            impact=r.impact,
            specific_copy=r.specific_copy,
            competitive_evidence=_evidence(r.evidence_pattern),
            expected_lift=r.expected_lift,
        )

    return RecommendationResult(
        recommendations=[_to_domain(r) for r in out.recommendations],
        quick_wins=[_to_domain(r) for r in out.quick_wins],
        strategic_moves=[_to_domain(r) for r in out.strategic_moves],
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
