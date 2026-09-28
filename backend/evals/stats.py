"""
Statistics for the eval harness.

Deliberately free of any I/O, model calls or project imports, so the maths can
be tested offline (tests/test_eval_stats.py) without spending a cent.

Two questions matter, and they are independent:

  * STABILITY — does the same listing score the same on repeat runs? An
    unstable score is not a score, it is a sample from a distribution.
  * DISCRIMINATION — does the scorer rank a strong listing above a weak one?
    A perfectly stable scorer that cannot tell good from bad is still useless,
    so stability alone is never sufficient evidence that scoring works.
"""
from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass

# Score stability thresholds, in points on the 0-10 scale.
# A listing whose overall score moves by more than SD_UNSTABLE between runs
# cannot be reported to a customer as a single number.
SD_STABLE = 0.35
SD_UNSTABLE = 0.75

# Per-dimension scores are noisier than the weighted overall, so they get more
# room before a dimension's scoring_criteria prose is considered too loose.
DIM_SD_STABLE = 0.75
DIM_SD_UNSTABLE = 1.50

# Rank correlation between human tier and mean score, below which the scorer
# is not reliably telling strong listings from weak ones.
MIN_TIER_CORRELATION = 0.70

TIER_RANK = {"weak": 0, "moderate": 1, "strong": 2}


@dataclass
class Summary:
    """Descriptive statistics for one set of repeated measurements."""
    n: int
    mean: float
    sd: float
    lo: float
    hi: float

    @property
    def spread(self) -> float:
        return self.hi - self.lo


def summarize(values: list[float]) -> Summary:
    """Mean and sample standard deviation. A single value has sd 0."""
    if not values:
        return Summary(0, 0.0, 0.0, 0.0, 0.0)
    sd = statistics.stdev(values) if len(values) > 1 else 0.0
    return Summary(
        n=len(values),
        mean=round(statistics.fmean(values), 3),
        sd=round(sd, 3),
        lo=round(min(values), 3),
        hi=round(max(values), 3),
    )


def verdict(sd: float, stable: float = SD_STABLE, unstable: float = SD_UNSTABLE) -> str:
    """Bucket a standard deviation into stable / acceptable / UNSTABLE."""
    if sd <= stable:
        return "stable"
    if sd <= unstable:
        return "acceptable"
    return "UNSTABLE"


def consistency(values: list) -> tuple[object, float]:
    """
    Most common value and the fraction of observations matching it.

    Used for categorical outputs like the chosen subcategory, where anything
    below 1.0 means repeat runs of one listing loaded different rubrics — and
    therefore were never scored on comparable criteria at all.
    """
    if not values:
        return None, 0.0
    modal, count = Counter(values).most_common(1)[0]
    return modal, round(count / len(values), 3)


def _ranks(values: list[float]) -> list[float]:
    """Average ranks, so ties share a rank rather than splitting arbitrarily."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        shared = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = shared
        i = j + 1
    return ranks


def spearman(xs: list[float], ys: list[float]) -> float | None:
    """
    Spearman rank correlation, or None when it is undefined.

    Returns None for fewer than three pairs or when either series is constant,
    rather than a misleading 0.0.
    """
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    if len(set(xs)) < 2 or len(set(ys)) < 2:
        return None

    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = statistics.fmean(rx), statistics.fmean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx)
    dy = sum((b - my) ** 2 for b in ry)
    if dx == 0 or dy == 0:
        return None
    return round(num / (dx * dy) ** 0.5, 3)


def tier_correlation(tiers: list[str], scores: list[float]) -> float | None:
    """Rank correlation between human quality tier and mean score."""
    pairs = [(TIER_RANK[t], s) for t, s in zip(tiers, scores) if t in TIER_RANK]
    if len(pairs) < 3:
        return None
    return spearman([p[0] for p in pairs], [p[1] for p in pairs])
