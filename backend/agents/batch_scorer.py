"""
Scores a batch of listings against a rubric in one call.

Shared deliberately. Competitors and generated rewrites must be graded by the
same process as each other, or "this rewrite scores 8.4 against a competitor
average of 6.5" compares two numbers produced by different methods — which is
the flaw this module exists to remove.

One LLM call scores every listing in the batch on every dimension (scores only,
no prose, to keep tokens down). The weighted overall is then computed in Python
using the rubric's own weights, identically to how the user's listing is scored.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from models.llm_responses import ListingBatchScoresOut, clamp
from models.schemas import ScoringRubric
from agents.llm_client import structured_completion

log = logging.getLogger("listingiq.agent.batch_scorer")


@dataclass
class BatchItem:
    """One listing to score, with a stable id the model echoes back."""
    item_id: int
    label: str                      # brand or variant name, for attribution
    title: str
    bullet_points: list[str]
    description: str = ""


@dataclass
class ScoredItem:
    item_id: int
    label: str
    overall_score: float
    dimension_scores: dict[str, float]


def weighted_overall(scores: dict[str, float], rubric: ScoringRubric) -> float:
    """The same weighting the user's listing receives, so results are comparable."""
    total_weight = sum(d.weight for d in rubric.dimensions) or 1.0
    weighted = sum(scores.get(d.name, 0.0) * d.weight for d in rubric.dimensions)
    return round(weighted / total_weight, 1)


async def score_batch(
    items: list[BatchItem],
    rubric: ScoringRubric,
    *,
    caller: str,
    what: str = "listings",
) -> list[ScoredItem]:
    """Score every item on every rubric dimension. Returns one entry per item."""
    if not items:
        return []

    listings_text = ""
    for it in items:
        bullets = "\n      ".join(f"• {b}" for b in it.bullet_points[:8]) or "(none)"
        listings_text += f"""
LISTING id={it.item_id} name={it.label or "unknown"}
  Title: {it.title}
  Bullets:
      {bullets}
  Description: {(it.description or "(none)")[:800]}
"""

    dims_text = "\n".join(
        f"  {d.name}: {d.description}\n    Scoring: {d.scoring_criteria}"
        for d in rubric.dimensions
    )

    prompt = f"""You are a quantitative ecommerce listing evaluation engine. Score EACH of the {what} below on EVERY rubric dimension.

{listings_text}

SCORING RUBRIC:
{dims_text}

RULES:
1. Score each listing on each dimension from 0.0 to 10.0, one decimal place.
2. Apply the scoring_criteria literally and identically to every listing. Do not
   be more generous to one than another for any reason.
3. Judge only what the listing text actually says.
4. Do not grade on a curve and do not cluster scores.
5. Return every listing using the id given, with every dimension.

Copy each dimension name exactly as written above."""

    out = await structured_completion(
        response_model=ListingBatchScoresOut,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_completion_tokens=8000,
        caller=caller,
    )

    valid_dims = {d.name for d in rubric.dimensions}
    by_id = {it.item_id: it for it in items}

    scored: list[ScoredItem] = []
    for row in out.items:
        source = by_id.get(row.item_id)
        if source is None:          # an id the model invented
            continue
        scores = {
            d.dimension: clamp(d.score, 0.0, 10.0)
            for d in row.dimension_scores
            if d.dimension in valid_dims
        }
        if not scores:
            continue
        scored.append(ScoredItem(
            item_id=row.item_id,
            label=source.label,
            overall_score=weighted_overall(scores, rubric),
            dimension_scores=scores,
        ))

    log.info("scored %d/%d %s across %d dimensions", len(scored), len(items), what, len(valid_dims))
    return scored
