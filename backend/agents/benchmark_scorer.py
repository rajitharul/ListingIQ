"""
Benchmark Scorer Agent (Agent 6)
Scores the user's listing 0-10 per dimension against the competitor benchmark.
This is the merge point where both parallel branches converge.
"""
from __future__ import annotations

import logging
import time
from models.schemas import (
    CompetitorBenchmark,
    ListingAnalysis,
    CompetitorAnalysis,
    ScoringRubric,
    ListingScore,
    DimensionScore,
    ParsedListing,
)
from models.llm_responses import BenchmarkScoreOut, clamp
from agents.llm_client import structured_completion

log = logging.getLogger("listingiq.agent.benchmark_scorer")


async def score_listing(
    listing_analysis: ListingAnalysis,
    competitor_analysis: CompetitorAnalysis,
    rubric: ScoringRubric,
    parsed_listing: ParsedListing,
    benchmark: CompetitorBenchmark,
    *,
    wide_benchmark: CompetitorBenchmark | None = None,
) -> ListingScore:
    """
    Score the user's listing per dimension against the competitor benchmark.

    `benchmark` is the headline cohort — same-platform where enough competitors
    were found there, the whole category otherwise. `wide_benchmark` is every
    competitor found, and produces a second percentile shown alongside: "top
    18% of Amazon sellers, top 31% of the category" says something neither
    number says alone.

    Keyword-only with a default, so existing five-argument callers are
    unaffected.
    """

    # Build dimension extraction summary
    dim_extractions = ""
    for de in listing_analysis.dimensions:
        status = "PRESENT" if de.present else "MISSING"
        dim_extractions += f"\n  - {de.dimension_name} [{status}]: {de.extracted_value or 'Not addressed'} (completeness: {de.completeness})"

    # The real size of the competitive set. This was hardcoded to 10 while a
    # marketplace search always returned exactly ten results; web discovery does
    # not, so "8/10 competitors" could describe a set of six — and the model was
    # being asked to weigh evidence against a denominator that did not exist.
    n_competitors = int(
        (competitor_analysis.structural_patterns or {}).get("listings_counted") or 0
    ) or 10

    # Build competitive context
    kw_context = "\n".join(
        f"  - '{kp.keyword}' used by {kp.frequency}/{n_competitors} competitors in {kp.position}"
        for kp in competitor_analysis.keyword_patterns[:10]
    )
    claim_context = "\n".join(
        f"  - '{cp.claim}' made by {cp.frequency}/{n_competitors} competitors"
        for cp in competitor_analysis.claim_patterns[:10]
    )
    trust_context = "\n".join(
        f"  - '{ts['signal']}' in {ts['frequency']}/{n_competitors} competitors"
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
2. Use the scoring_criteria from the rubric as your guide, applied exactly as it was applied to the competitors
3. Judge only what the listing actually says
4. Be discriminating — a bare-minimum listing should score 1-3, a decent listing 4-6, a good listing 7-8, excellent 9+

Do NOT estimate competitor averages, gaps or percentiles. Those are measured
separately from the competitors' own scores; your job is this listing only.

Score every dimension in the rubric above, copying each dimension's weight verbatim."""

    out = await structured_completion(
        response_model=BenchmarkScoreOut,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_completion_tokens=6000,
        caller="benchmark_scorer.score",
    )

    dimension_scores = []
    for ds in out.dimension_scores:
        score = clamp(ds.score, 0.0, 10.0)
        # Measured from the competitors' own scores on this rubric. Falls back
        # to the user's own score only when a dimension could not be measured,
        # which yields a zero gap rather than a fabricated one.
        measured = benchmark.mean_for(ds.dimension)
        competitor_avg = measured if measured is not None else score
        dimension_scores.append(DimensionScore(
            dimension=ds.dimension,
            weight=clamp(ds.weight, 0.0, 1.0),
            score=score,
            explanation=ds.explanation,
            competitor_avg=round(competitor_avg, 2),
            gap=round(competitor_avg - score, 2),
            strengths=ds.strengths,
            weaknesses=ds.weaknesses,
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

    wide = wide_benchmark or benchmark
    return ListingScore(
        overall_score=overall_score,
        dimension_scores=dimension_scores,
        # Measured: how many of the scored competitors this listing beats.
        percentile=benchmark.percentile_for(overall_score),
        gap_analysis=gap_analysis,
        # Which cohort that percentile describes, and how big it was. An
        # unqualified percentile cannot be checked; "top 18% of 11" can.
        percentile_basis=benchmark.cohort,
        percentile_cohort_n=len(benchmark.competitors),
        category_percentile=wide.percentile_for(overall_score),
        category_cohort_n=len(wide.competitors),
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

    benchmark = state.get("competitor_benchmark") or CompetitorBenchmark()
    if isinstance(benchmark, dict):
        benchmark = CompetitorBenchmark(**benchmark)

    wide = state.get("competitor_benchmark_all")
    if isinstance(wide, dict):
        wide = CompetitorBenchmark(**wide)

    result = await score_listing(
        listing_analysis, competitor_analysis, rubric, parsed, benchmark,
        wide_benchmark=wide)
    log.info(
        "⚙ benchmark_scorer_node EXIT  %.1fs  overall=%.1f  percentile=%d vs %s (n=%d)  "
        "category=%d (n=%d)  gaps=%d",
        time.perf_counter() - t0,
        result.overall_score,
        result.percentile,
        result.percentile_basis,
        result.percentile_cohort_n,
        result.category_percentile,
        result.category_cohort_n,
        len(result.gap_analysis),
    )
    return {"scores": result}
