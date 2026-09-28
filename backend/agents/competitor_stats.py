"""
Competitive statistics computed from the listings themselves.

Everything here used to be asked of the model: "how many of the 10 competitors
use this keyword?", "what is the average title length?". Those are arithmetic
over text we already hold, so a model estimate was a fabricated statistic
presented to customers as evidence — and the recommendations quote it verbatim
("8/10 top competitors include this").

The split is deliberate:

  * the model decides WHAT to look for — which keywords matter, which claims
    count as the same claim. That is semantic and it is genuinely good at it.
  * Python decides HOW MANY. That is counting, it is exact, and it is auditable.

Pure functions, no I/O and no model calls, so the arithmetic can be tested for
free in tests/test_competitor_stats.py.
"""
from __future__ import annotations

import re
import unicodedata

from models.schemas import CompetitorListing
# Brand identity lives in normalize.py so providers/ can use it without
# importing agents/. Re-exported here: this is where callers expect it.
from normalize import brand_key, dedupe_by_brand  # noqa: F401

# Emoji and pictographic symbols, used to measure how many competitors decorate
# their bullets. Matching on Unicode category is more robust than a range list.
_EMOJI_CATEGORIES = {"So", "Sk"}


def _listing_text(listing: CompetitorListing) -> str:
    parts = [listing.title or "", *(listing.bullet_points or []), listing.description or ""]
    return "\n".join(parts)


from normalize import normalise as _normalise  # noqa: E402


def contains_phrase(haystack: str, phrase: str) -> bool:
    """
    Whole-word phrase match.

    Substring matching would count "mag" inside "magnesium" and inflate every
    frequency, so the phrase must sit on word boundaries.
    """
    phrase = _normalise(phrase).strip()
    if not phrase:
        return False
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", _normalise(haystack)) is not None


def count_keyword(listings: list[CompetitorListing], keyword: str) -> tuple[int, str]:
    """
    How many listings use a keyword, and where it most often appears.

    Returns (frequency, position) where position is title, bullets or
    description — whichever carries it in the most listings.
    """
    freq = 0
    where = {"title": 0, "bullets": 0, "description": 0}
    for l in listings:
        found = False
        if contains_phrase(l.title or "", keyword):
            where["title"] += 1
            found = True
        if any(contains_phrase(b, keyword) for b in (l.bullet_points or [])):
            where["bullets"] += 1
            found = True
        if contains_phrase(l.description or "", keyword):
            where["description"] += 1
            found = True
        freq += int(found)

    position = max(where, key=lambda k: where[k]) if any(where.values()) else "title"
    return freq, position


def emoji_count(text: str) -> int:
    return sum(1 for ch in text if unicodedata.category(ch) in _EMOJI_CATEGORIES)


def structural_patterns(listings: list[CompetitorListing]) -> dict:
    """
    Exact structural statistics.

    `listings_with_description` is reported alongside the average because Amazon
    listings frequently carry no description block at all — averaging zeros
    would otherwise read as "competitors write short descriptions" when the
    truth is that the copy lives in A+ images.
    """
    n = len(listings)
    if not n:
        return {}

    titles = [l.title or "" for l in listings]
    bullet_counts = [len(l.bullet_points or []) for l in listings]
    descriptions = [l.description or "" for l in listings]
    with_desc = [d for d in descriptions if d.strip()]

    bullets_joined = ["\n".join(l.bullet_points or []) for l in listings]
    rated = [l.rating for l in listings if l.rating > 0]
    reviewed = [l.review_count for l in listings if l.review_count > 0]

    return {
        "avg_title_length": round(sum(len(t) for t in titles) / n),
        "min_title_length": min(len(t) for t in titles),
        "max_title_length": max(len(t) for t in titles),
        "avg_bullet_count": round(sum(bullet_counts) / n, 1),
        "avg_bullet_length": round(
            sum(len(b) for l in listings for b in (l.bullet_points or []))
            / max(1, sum(bullet_counts))
        ),
        # Averaged over listings that actually have one, not over zeros.
        "avg_description_length": round(sum(len(d) for d in with_desc) / len(with_desc))
        if with_desc else 0,
        "listings_with_description": len(with_desc),
        "emoji_usage": sum(1 for b in bullets_joined if emoji_count(b) > 0),
        # Averaged over listings that actually carry the figure, for the same
        # reason descriptions are: a competitor found through an open-web
        # search has no rating, and dividing by the full count would report
        # "competitors average 2.2 stars" when the truth is that we could not
        # see the rating for half of them. That number feeds the rewrite
        # generator and the recommendations, so the artefact would be quoted
        # back to the customer as a market fact.
        "avg_rating": round(sum(rated) / len(rated), 2) if rated else 0.0,
        "listings_with_rating": len(rated),
        "median_review_count": sorted(reviewed)[len(reviewed) // 2] if reviewed else 0,
        "listings_with_reviews": len(reviewed),
        "listings_with_price": sum(1 for l in listings if (l.price or "").strip()),
        "listings_counted": n,
    }


def tally_by_rank(
    listings: list[CompetitorListing], ranks: list[int]
) -> tuple[int, list[str]]:
    """
    Turn a model's attribution into a counted frequency.

    The model says which competitors make a claim; this counts them and resolves
    the brands. Unknown or duplicated ranks are dropped, so a model that invents
    an eleventh competitor cannot inflate a frequency past the sample size.
    """
    by_rank = {l.rank: l for l in listings}
    seen: list[int] = []
    for r in ranks:
        if r in by_rank and r not in seen:
            seen.append(r)
    brands = [by_rank[r].brand_name or by_rank[r].title[:40] for r in seen]
    return len(seen), brands
