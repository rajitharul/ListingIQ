"""
Competitor Scorer — measures the benchmark instead of guessing it.

Before this existed, `benchmark_scorer` asked the model "what would the average
top-10 competitor score on this dimension?" and used the answer as the
benchmark. That made the product's central claim — your listing benchmarked
against the top 10 — an estimate of an average of listings nobody had scored.

Here the competitors are scored on the same rubric as the user's listing, and
the average is computed in Python. One LLM call scores all of them at once
(scores only, no prose) to keep the cost close to a single agent call.

The result depends only on the competitor set and the rubric, never on the
user's listing, so it is cached per subcategory. A day's worth of analyses in
one subcategory pays for this once.
"""
from __future__ import annotations

import logging
import time

from agents.batch_scorer import BatchItem, score_batch
from agents.benchmark_cohorts import split_cohorts
from models.schemas import (
    CompetitorBenchmark,
    CompetitorBenchmarkSet,
    CompetitorDimensionStat,
    CompetitorScoreRow,
    CompetitorScoutResult,
    ScoringRubric,
)
from providers import benchmark_cache

log = logging.getLogger("listingiq.agent.competitor_scorer")


async def score_competitor_cohorts(
    scout: CompetitorScoutResult,
    rubric: ScoringRubric,
) -> CompetitorBenchmarkSet:
    """
    Score every scoreable competitor once, then aggregate into both cohorts.

    One LLM call, two benchmarks: the same-platform cohort that drives the
    headline and the whole-category cohort that gives it context. The second
    costs nothing because it is arithmetic over rows the first already paid for.
    """
    # A competitor whose page could not be read is a real competitor and is
    # shown as one, but grading it would grade our own extraction failure — and
    # a low score for a listing we never actually read drags the mean down and
    # *inflates* the user's percentile.
    scoreable = [l for l in scout.listings if l.counts_toward_benchmark]
    skipped = len(scout.listings) - len(scoreable)
    if skipped:
        log.info("excluding %d competitor(s) from the benchmark: page not readable", skipped)

    if not scoreable:
        return CompetitorBenchmarkSet()

    scored = await score_batch(
        [BatchItem(item_id=l.rank, label=l.brand_name or l.title[:40],
                   title=l.title, bullet_points=l.bullet_points,
                   description=l.description)
         for l in scoreable],
        rubric,
        caller="competitor_scorer.score",
        what="competitor listings",
    )

    by_rank = {l.rank: l for l in scoreable}
    rows: list[CompetitorScoreRow] = []
    for item in scored:
        listing = by_rank.get(item.item_id)
        rows.append(CompetitorScoreRow(
            rank=item.item_id,
            brand_name=item.label,
            title=(listing.title if listing else "")[:140],
            platform=(listing.platform if listing else ""),
            overall_score=item.overall_score,
            dimension_scores=item.dimension_scores,
        ))

    # Aggregate in Python. These are the numbers the user is benchmarked
    # against, so they are measured, never model-supplied. Provenance travels
    # with them, or the benchmark cache cannot tell a measured benchmark from
    # one built on estimates.
    cohorts = split_cohorts(
        rows, rubric,
        platform=scout.platform,
        data_source=scout.data_source,
        is_live_data=scout.is_live_data,
    )

    log.info("scored %d/%d competitors — same-platform mean %.2f (n=%d), "
             "category mean %.2f (n=%d)",
             len(rows), len(scout.listings),
             cohorts.same_platform.overall_mean, len(cohorts.same_platform.competitors),
             cohorts.all_competitors.overall_mean, len(cohorts.all_competitors.competitors))
    return cohorts


async def score_competitors(
    scout: CompetitorScoutResult,
    rubric: ScoringRubric,
) -> CompetitorBenchmark:
    """
    The whole-category benchmark, for callers that want a single number.

    Kept so `evals/run_eval.py` and existing tests are unaffected by the cohort
    split.
    """
    return (await score_competitor_cohorts(scout, rubric)).all_competitors


# ── LangGraph node wrapper ────────────────────────────────────
async def competitor_scorer_node(state: dict) -> dict:
    """LangGraph node: measures the competitive benchmark."""
    log.info("⚙ competitor_scorer_node ENTER")
    t0 = time.perf_counter()

    scout = state["competitor_scout_result"]
    if isinstance(scout, dict):
        scout = CompetitorScoutResult(**scout)

    rubric = state["rubric"]
    if isinstance(rubric, dict):
        rubric = ScoringRubric(**rubric)

    # Keyed on the exact competitor set as well as the rubric: web discovery can
    # return a different set for the same subcategory, and a benchmark computed
    # from one set must never be served as though it described another.
    set_fp = benchmark_cache.competitor_set_fingerprint(scout)

    cohorts = await benchmark_cache.get(scout.platform, rubric.subcategory, rubric, set_fp)
    cached = cohorts is not None
    if cohorts is None:
        cohorts = await score_competitor_cohorts(scout, rubric)
        await benchmark_cache.put(scout.platform, rubric.subcategory, rubric, cohorts, set_fp)
    else:
        cohorts = cohorts.model_copy(update={
            "same_platform": cohorts.same_platform.model_copy(update={"from_cache": True}),
            "all_competitors": cohorts.all_competitors.model_copy(update={"from_cache": True}),
        })

    primary = cohorts.primary
    log.info("⚙ competitor_scorer_node EXIT  %.1fs%s  headline=%s mean=%.2f n=%d  "
             "category mean=%.2f n=%d",
             time.perf_counter() - t0, "  CACHED" if cached else "",
             cohorts.primary_cohort, primary.overall_mean, len(primary.competitors),
             cohorts.all_competitors.overall_mean, len(cohorts.all_competitors.competitors))

    # `competitor_benchmark` keeps meaning "the benchmark that drives the
    # headline", so benchmark_scorer and rewrite_verifier read it unchanged.
    return {
        "competitor_benchmark": primary,
        "competitor_benchmark_all": cohorts.all_competitors,
        "benchmark_cohorts": cohorts,
    }
