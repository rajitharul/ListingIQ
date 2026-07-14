"""
Benchmark Scorer Agent (Agent 6)
Scores the user's listing 0-10 per dimension against the competitor benchmark.
This is the merge point where both parallel branches converge.
"""
from __future__ import annotations

import json
import logging
import time
from config import OPENAI_MODEL
from models.schemas import (
    ListingAnalysis,
    CompetitorAnalysis,
    ScoringRubric,
    ListingScore,
    DimensionScore,
    ParsedListing,
)
from agents.llm_client import logged_chat_completion

log = logging.getLogger("listingiq.agent.benchmark_scorer")


async def score_listing(
    listing_analysis: ListingAnalysis,
    competitor_analysis: CompetitorAnalysis,
    rubric: ScoringRubric,
    parsed_listing: ParsedListing,
) -> ListingScore:
    """Score the user's listing per dimension against the competitor benchmark."""

    # Build dimension extraction summary
    dim_extractions = ""
    for de in listing_analysis.dimensions:
        status = "PRESENT" if de.present else "MISSING"
        dim_extractions += f"\n  - {de.dimension_name} [{status}]: {de.extracted_value or 'Not addressed'} (completeness: {de.completeness})"

    # Build competitive context
    kw_context = "\n".join(
        f"  - '{kp.keyword}' used by {kp.frequency}/10 competitors in {kp.position}"
        for kp in competitor_analysis.keyword_patterns[:10]
    )
    claim_context = "\n".join(
        f"  - '{cp.claim}' made by {cp.frequency}/10 competitors"
        for cp in competitor_analysis.claim_patterns[:10]
    )
    trust_context = "\n".join(
        f"  - '{ts.get('signal', '')}' in {ts.get('frequency', 0)}/10 competitors"
        for ts in competitor_analysis.trust_signals[:10]
    )

    # Build rubric with scoring criteria
    rubric_text = ""
    for d in rubric.dimensions:
        rubric_text += f"\n  {d.name} (weight: {d.weight}):\n    Description: {d.description}\n    Scoring: {d.scoring_criteria}"

    prompt = f"""You are a quantitative ecommerce listing evaluation engine. Score this product listing on every dimension using the rubric and competitive benchmark data.

USER'S LISTING:
  Title: {parsed_listing.original_title}
  Brand: {parsed_listing.brand_name}

LISTING ANALYSIS (what the user's listing says per dimension):
{dim_extractions}

COMPETITIVE BENCHMARK DATA:
  Top Keywords: {kw_context}
  Common Claims: {claim_context}
  Trust Signals: {trust_context}
  Competitive Summary: {competitor_analysis.summary}

SCORING RUBRIC:
{rubric_text}

SCORING RULES:
1. Score each dimension 0.0 to 10.0 (one decimal place)
2. Use the scoring_criteria from the rubric as your guide
3. Compare against the competitive benchmark — if 9/10 competitors mention something and the user doesn't, that's a significant gap
4. Be discriminating — a bare-minimum listing should score 1-3, a decent listing 4-6, a good listing 7-8, excellent 9+
5. Calculate competitor_avg: what the average top-10 competitor would score on this dimension
6. Calculate gap: competitor_avg - user_score (positive = user is behind)

Return a JSON object:
{{
  "dimension_scores": [
    {{
      "dimension": "Form Specificity",
      "weight": 0.15,
      "score": 3.5,
      "explanation": "Listing states 'Magnesium Glycinate' in title but does not explain why glycinate form matters or compare to other forms.",
      "competitor_avg": 7.2,
      "gap": 3.7,
      "strengths": ["Form is named in title"],
      "weaknesses": ["No explanation of form benefits", "No comparison to other forms"]
    }}
  ],
  "percentile": 25
}}

The percentile is where the user's listing would rank if inserted among the 10 competitors (0 = worst, 100 = best).
Return ONLY valid JSON."""

    response = await logged_chat_completion(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        response_format={"type": "json_object"},
        caller="benchmark_scorer.score",
    )
    data = json.loads(response.choices[0].message.content)

    dimension_scores = []
    for ds in data.get("dimension_scores", []):
        dimension_scores.append(DimensionScore(
            dimension=ds.get("dimension", ""),
            weight=ds.get("weight", 0.0),
            score=ds.get("score", 0.0),
            explanation=ds.get("explanation", ""),
            competitor_avg=ds.get("competitor_avg", 0.0),
            gap=ds.get("gap", 0.0),
            strengths=ds.get("strengths", []),
            weaknesses=ds.get("weaknesses", []),
        ))

    # Calculate weighted overall score
    total_weight = sum(ds.weight for ds in dimension_scores) or 1.0
    weighted_sum = sum(ds.score * ds.weight for ds in dimension_scores)
    overall_score = round(weighted_sum / total_weight, 1)

    # Build gap analysis sorted by impact (gap * weight)
    gap_analysis = sorted(
        [
            {
                "dimension": ds.dimension,
                "score": ds.score,
                "competitor_avg": ds.competitor_avg,
                "gap": ds.gap,
                "weight": ds.weight,
                "impact": round(ds.gap * ds.weight, 3),
            }
            for ds in dimension_scores
            if ds.gap > 0
        ],
        key=lambda x: x["impact"],
        reverse=True,
    )

    return ListingScore(
        overall_score=overall_score,
        dimension_scores=dimension_scores,
        percentile=data.get("percentile", 0),
        gap_analysis=gap_analysis,
    )


# ── LangGraph node wrapper ────────────────────────────────────
async def benchmark_scorer_node(state: dict) -> dict:
    """LangGraph node: scores listing per dimension against competitive benchmark."""
    log.info("⚙ benchmark_scorer_node ENTER")
    t0 = time.perf_counter()

    listing_analysis = state["listing_analysis"]
    if isinstance(listing_analysis, dict):
        listing_analysis = ListingAnalysis(**listing_analysis)

    competitor_analysis = state["competitor_analysis"]
    if isinstance(competitor_analysis, dict):
        competitor_analysis = CompetitorAnalysis(**competitor_analysis)

    rubric = state["rubric"]
    if isinstance(rubric, dict):
        rubric = ScoringRubric(**rubric)

    parsed = state["parsed_listing"]
    if isinstance(parsed, dict):
        parsed = ParsedListing(**parsed)

    result = await score_listing(listing_analysis, competitor_analysis, rubric, parsed)
    log.info(
        "⚙ benchmark_scorer_node EXIT  %.1fs  overall=%.1f  percentile=%d  gaps=%d",
        time.perf_counter() - t0,
        result.overall_score,
        result.percentile,
        len(result.gap_analysis),
    )
    return {"scores": result}
