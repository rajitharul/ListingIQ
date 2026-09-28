"""
Aggregating scored competitors into cohorts.

Pure arithmetic over rows that have already been scored — no I/O, no model call.
That separation is the point: scoring costs one LLM call for the whole set, and
producing two cohorts from it costs nothing, so the second cohort is free rather
than a doubling of the bill.

Why two cohorts at all: once competitors can come from anywhere, averaging them
into one number stops measuring listing quality. A marketplace title is 200
keyword-dense characters with five bullets; a brand site's product page is a
40-character name and prose. Both can be excellent. Pooled, the mean measures
which house style dominated the search results.
"""
from __future__ import annotations

import logging

from config import BENCHMARK_MIN_COHORT
from models.schemas import (
    CompetitorBenchmark,
    CompetitorBenchmarkSet,
    CompetitorDimensionStat,
    CompetitorScoreRow,
    ScoringRubric,
)
from providers import platforms

log = logging.getLogger("listingiq.agent.cohorts")


def aggregate(
    rows: list[CompetitorScoreRow],
    rubric: ScoringRubric,
    *,
    cohort: str,
    data_source: str = "",
    is_live_data: bool = False,
) -> CompetitorBenchmark:
    """
    Mean, best and worst per dimension, computed in Python.

    `n` is carried per dimension because it is not constant: a competitor whose
    page could not be read is absent from every dimension, and a small `n` is
    the difference between a benchmark and an anecdote.
    """
    stats: list[CompetitorDimensionStat] = []
    for d in rubric.dimensions:
        values = [r.dimension_scores[d.name] for r in rows if d.name in r.dimension_scores]
        if not values:
            continue
        stats.append(CompetitorDimensionStat(
            dimension=d.name,
            mean=round(sum(values) / len(values), 2),
            best=max(values),
            worst=min(values),
            n=len(values),
        ))

    overall_mean = round(sum(r.overall_score for r in rows) / len(rows), 2) if rows else 0.0

    return CompetitorBenchmark(
        dimensions=stats,
        competitors=rows,
        overall_mean=overall_mean,
        rubric_version=rubric.version,
        cohort=cohort,
        platforms=sorted({r.platform for r in rows if r.platform}),
        data_source=data_source,
        is_live_data=is_live_data,
    )


def split_cohorts(
    rows: list[CompetitorScoreRow],
    rubric: ScoringRubric,
    *,
    platform: str,
    data_source: str = "",
    is_live_data: bool = False,
) -> CompetitorBenchmarkSet:
    """
    Build both cohorts from one scored set and decide which leads.

    The same-platform cohort is matched on the canonical platform slug, so a
    user on `amazon_uk` is compared against Amazon listings regardless of which
    regional domain they were found on.
    """
    want = platforms.canonical(platform)
    same_rows = [r for r in rows if platforms.canonical(r.platform) == want] if want else []

    same = aggregate(same_rows, rubric, cohort="same_platform",
                     data_source=data_source, is_live_data=is_live_data)
    every = aggregate(rows, rubric, cohort="all_competitors",
                      data_source=data_source, is_live_data=is_live_data)

    # A percentile over two competitors is noise with a decimal point. Below the
    # floor the headline moves to the wider cohort and says so, rather than
    # quoting a precise-looking number built on nothing.
    if len(same_rows) >= BENCHMARK_MIN_COHORT:
        primary, note = "same_platform", ""
    else:
        primary = "all_competitors"
        label = platforms.label_for(platform) if want else "this platform"
        note = (f"only {len(same_rows)} competitor(s) found on {label}, "
                f"too few to benchmark against — scored against all "
                f"{len(rows)} competitors instead")

    log.info("cohorts: same_platform n=%d, all n=%d, headline=%s",
             len(same_rows), len(rows), primary)

    return CompetitorBenchmarkSet(
        same_platform=same, all_competitors=every,
        primary_cohort=primary, note=note,
    )
