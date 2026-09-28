"""
Text identity for products — pure, dependency-free normalisation.

This module exists to settle a layering problem. `brand_key` and
`dedupe_by_brand` were defined in `agents/competitor_stats.py` and imported by
`providers/rainforest.py`, so the provider layer depended on the agent layer.
Moving them into `providers/` would only invert the arrow, because the stats
module genuinely needs `brand_key` too. A neutral module both can import is the
only arrangement that is correct in both directions.

Everything here is a pure function over strings: no I/O, no model calls, no
imports from `agents/` or `providers/`.
"""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlsplit

# Words that carry no identity: they appear in most listing titles and would
# make two unrelated products look similar under token comparison.
_FILLER = frozenset("""
a an and or the for with without of in on to by from at
new premium best natural pure advanced ultra super high max maximum plus
quality grade strength potency formula supplement supplements product products
pack count ct pcs piece pieces size value bulk free non
""".split())

# Unit spellings that should collapse so "400 mg" and "400mg" are one token.
_UNITS = ("mg", "mcg", "g", "kg", "ml", "l", "oz", "fl", "iu", "ct", "count", "capsules",
          "capsule", "tablets", "tablet", "softgels", "softgel", "servings", "serving")

_UNIT_RE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(" + "|".join(sorted(_UNITS, key=len, reverse=True)) + r")\b"
)


def normalise(text: str) -> str:
    """Casefold and collapse whitespace so matching is not defeated by layout."""
    return re.sub(r"\s+", " ", text or "").casefold()


def strip_accents(text: str) -> str:
    """Fold accented characters to ASCII so 'Nutrición' matches 'Nutricion'."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def brand_key(title: str, words: int = 3) -> str:
    """
    A rough brand identity taken from the start of a title.

    Marketplace search results carry no brand field — that only arrives with the
    per-product lookup, which is the expensive call. Marketplace titles almost
    always lead with the brand ("Optimum Nutrition Micronized Creatine…"), so the
    first few words identify it well enough to deduplicate *before* paying for
    detail.

    This is a within-platform heuristic. Across platforms the same product is
    titled differently ("Nature's Bounty Magnesium 400mg" on a marketplace vs
    "Magnesium Glycinate 400mg | Nature's Bounty" on the brand's own site), and
    the leading words no longer agree — use `product_identity` for that.
    """
    # Apostrophes are deleted rather than replaced with a space: "Nature's"
    # must stay one word, or it consumes two slots of the window and a brand
    # fails to match its own variants written without the apostrophe.
    text = re.sub(r"['’ʼ`]", "", normalise(title))
    cleaned = re.sub(r"[^\w\s]", " ", text)
    return " ".join(cleaned.split()[:words])


def dedupe_by_brand(
    items: list[dict], title_key: str = "title", limit: int | None = None
) -> list[dict]:
    """
    Keep the best-ranked item per brand, preserving order.

    Marketplaces list size and flavour variants as separate items, so one brand
    can occupy several of the top 10 — which pulls the benchmark average toward
    whichever brand has the most variants and makes "the top 10" misleading.
    """
    seen: set[str] = set()
    out: list[dict] = []
    for item in items:
        key = brand_key(item.get(title_key) or "")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
        if limit and len(out) >= limit:
            break
    return out


def significant_tokens(title: str) -> frozenset[str]:
    """
    The tokens that actually identify a product, order-independent.

    Units are joined to their number ("400 mg" -> "400mg") and filler words are
    dropped, so two titles describing the same product agree regardless of how
    each platform orders or decorates them.
    """
    text = strip_accents(normalise(title))
    text = re.sub(r"['’ʼ`]", "", text)
    text = _UNIT_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}", text)
    tokens = re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", text)
    return frozenset(t for t in tokens if t not in _FILLER and len(t) > 1)


def product_identity(title: str, brand: str = "") -> str:
    """
    An order-independent identity string for cross-platform matching.

    Deliberately coarse. It is used to spot the *same* product listed on two
    different sites, where titles are written to different house styles.
    """
    tokens = significant_tokens(title)
    if brand:
        tokens = tokens | significant_tokens(brand)
    return " ".join(sorted(tokens))


def title_similarity(a: str, b: str) -> float:
    """Jaccard overlap of significant tokens. 1.0 is identical, 0.0 disjoint."""
    ta, tb = significant_tokens(a), significant_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def registrable_domain(url: str) -> str:
    """
    The domain used for grouping and display, without a `www.` prefix.

    Not a public-suffix-list implementation — it keeps the full host minus
    `www.`, which is what we need to say "three results from this one store"
    and to show the user where a competitor was found.
    """
    if not url:
        return ""
    host = urlsplit(url if "//" in url else f"//{url}").hostname or ""
    host = host.lower()
    return host[4:] if host.startswith("www.") else host


def token_containment(a: str, b: str) -> float:
    """
    How much of the *shorter* title appears in the longer one.

    Jaccard is the right test for "are these the same product" between two
    listings of similar length. It is the wrong test for matching a short
    shopping entry against a long marketplace title — "Spring Valley Magnesium
    Glycinate 120ct" against "Spring Valley High Absorption Magnesium Glycinate
    Capsules for Bone and Muscle Support" scores 0.40 by Jaccard and 0.80 by
    containment, and the second number is the true one.
    """
    ta, tb = significant_tokens(a), significant_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def distinctive_overlap(a: str, b: str, generic: frozenset[str] = frozenset()) -> set[str]:
    """
    Shared tokens that are not the category term everyone in the set shares.

    Containment alone is dangerous inside one category: every title contains
    "magnesium glycinate capsules", so two unrelated products score highly on
    words that identify the category rather than the product. What distinguishes
    them is the brand and the strength.
    """
    shared = significant_tokens(a) & significant_tokens(b)
    return {t for t in shared if t not in generic}


_ARTICLE_TITLE_RE = re.compile(
    r"^\s*(?:the\s+)?(?:\d{1,2}\s+)?best\b"        # "Best magnesium…", "12 Best…"
    r"|\btop\s+\d{1,2}\b"                            # "Top 10 …"
    r"|\bbuying guide\b|\bhow to (?:choose|pick|buy)\b"
    r"|\b(?:vs\.?|versus)\s+\w"
    r"|\b(?:20\d\d)\s*(?:guide|review|roundup)\b"
    r"|\bwe (?:tested|tried|ranked)\b"
    r"|\b(?:rd|dietitian|expert|editor)[- ](?:reviewed|approved|tested)\b",
    re.I)
# Deliberately NOT matched on their own: "tested", "reviewed", "ranked",
# "compared". Verified against live listings — "Third-Party Tested" and
# "Clinically Tested" are among the commonest real supplement claims, and
# treating them as article markers threw away genuine competitors.


def looks_like_article(title: str, has_structured_product: bool = False) -> bool:
    """
    Whether this title belongs to a page that reviews products rather than selling one.

    Used twice: at discovery, so an editorial round-up does not consume one of
    the ten competitor slots, and again after fetching, when the page's real
    title and its structured data are both known.

    A page that publishes `schema.org/Product` markup is claiming to *be* a
    product, which outweighs a promotional-sounding title — plenty of real
    listings are called "Best Magnesium Glycinate". Without that claim, an
    article-shaped title is the only evidence available, and scoring a
    journalist's round-up as a competitor's listing copy is worse than losing
    one competitor.
    """
    if has_structured_product:
        return False
    return bool(_ARTICLE_TITLE_RE.search(title or ""))


