"""
Rewrite Verifier — scores the generated rewrites for real.

The rewrite generator returns an `expected_score` for each variant. That number
is the model grading its own homework: it has never been through the scorer, and
it was the basis of the product's strongest marketing claim ("our rewrite takes
you from 2.9 to 9.2"). Unverified, that claim is unsellable.

Here each variant is scored through the same batch scorer that grades the
competitors, against the same rubric, and ranked against the same measured
benchmark. The model's projection is kept alongside as `expected_score` so the
gap between projected and measured is visible rather than hidden — that gap is
itself a useful signal about how much to trust the generator.
"""
from __future__ import annotations

import logging
import time

from agents.batch_scorer import BatchItem, score_batch
from models.schemas import (
    CompetitorBenchmark,
    RewriteResult,
    ScoringRubric,
)

log = logging.getLogger("listingiq.agent.rewrite_verifier")


async def verify_rewrites(
    rewrites: RewriteResult,
    rubric: ScoringRubric,
    benchmark: CompetitorBenchmark,
    *,
    wide_benchmark: CompetitorBenchmark | None = None,
) -> RewriteResult:
    """Score every variant and attach the measured result."""
    if not rewrites.variants:
        return rewrites

    scored = await score_batch(
        [BatchItem(item_id=i, label=v.variant_name or f"variant {i}",
                   title=v.title, bullet_points=v.bullet_points,
                   description=v.description)
         for i, v in enumerate(rewrites.variants)],
        rubric,
        caller="rewrite_verifier.score",
        what="rewritten listings",
    )
    by_id = {s.item_id: s for s in scored}

    verified = []
    for i, v in enumerate(rewrites.variants):
        result = by_id.get(i)
        if result is None:
            # Unscored variants stay honest: no measured number rather than a
            # fabricated one, and the UI falls back to the projection.
            verified.append(v)
            continue
        verified.append(v.model_copy(update={
            "measured_score": result.overall_score,
            "measured_percentile": benchmark.percentile_for(result.overall_score),
            "measured_category_percentile":
                (wide_benchmark or benchmark).percentile_for(result.overall_score),
            "measured_dimension_scores": result.dimension_scores,
            "is_verified": True,
        }))

    measured = [v.measured_score for v in verified if v.is_verified]
    best_measured = max(measured) if measured else 0.0

    drift = [
        round(v.expected_score - v.measured_score, 1)
        for v in verified if v.is_verified
    ]
    if drift:
        log.info("verified %d variants — measured best %.1f, model projected %.1f "
                 "(optimism %+.1f avg)",
                 len(measured), best_measured,
                 max(v.expected_score for v in verified),
                 sum(drift) / len(drift))

    return rewrites.model_copy(update={
        "variants": verified,
        "best_variant_score": best_measured or rewrites.best_variant_score,
        "scores_verified": bool(measured),
    })


# ── LangGraph node wrapper ────────────────────────────────────
async def rewrite_verifier_node(state: dict) -> dict:
    """LangGraph node: measures the generated rewrites instead of trusting them."""
    log.info("⚙ rewrite_verifier_node ENTER")
    t0 = time.perf_counter()

    rewrites = state["rewrites"]
    if isinstance(rewrites, dict):
        rewrites = RewriteResult(**rewrites)

    rubric = state["rubric"]
    if isinstance(rubric, dict):
        rubric = ScoringRubric(**rubric)

    benchmark = state.get("competitor_benchmark") or CompetitorBenchmark()
    if isinstance(benchmark, dict):
        benchmark = CompetitorBenchmark(**benchmark)

    wide = state.get("competitor_benchmark_all")
    if isinstance(wide, dict):
        wide = CompetitorBenchmark(**wide)

    result = await verify_rewrites(rewrites, rubric, benchmark, wide_benchmark=wide)
    log.info("⚙ rewrite_verifier_node EXIT  %.1fs  verified=%s  best measured=%.1f",
             time.perf_counter() - t0, result.scores_verified, result.best_variant_score)
    return {"rewrites": result}
