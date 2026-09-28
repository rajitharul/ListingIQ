"""
Turning many search results into one competitive set.

Two search channels across any number of storefronts produce duplicates that the
old Amazon-only path never had to handle. `brand_key` — the first three words of
the title — collapses a marketplace's own size and flavour variants, which is
what it was written for. It does **not** collapse the same product sold in two
places, because the titles are written to different house styles:

    "Nature's Bounty Magnesium Glycinate 400 mg, 120 Capsules"   (marketplace)
    "Magnesium Glycinate 400mg | Natures Bounty"                 (brand site)

Left alone, that product is scored twice and counted twice in the mean. So the
passes below layer an exact identity, an order-independent token identity, and a
per-storefront cap on top of the original heuristic.

Where the two disagree the code **under-collapses on purpose**: keeping two
listings that turn out to be one product overstates the cohort slightly, while
merging two genuinely different products from one brand deletes a real
competitor. The count of near-duplicates is reported rather than hidden.
"""
from __future__ import annotations

import logging

from normalize import (
    brand_key, distinctive_overlap, looks_like_article, title_similarity,
    token_containment,
)
from providers.discovery.base import Candidate

log = logging.getLogger("listingiq.providers.merge")

# Above this token overlap, two titles from different storefronts are treated as
# the same product. Measured against real pairs: a genuine cross-platform match
# scores ~0.83, two different SKUs from one brand ~0.5.
SAME_PRODUCT_THRESHOLD = 0.72


def _preference(c: Candidate) -> tuple:
    """
    Shopping results first: they arrive with price, rating and review count
    already populated, so choosing them over an equivalent web result saves an
    extraction and yields strictly more data.
    """
    return (0 if c.channel == "shopping" else 1, c.position or 999)


# Containment needed before a shopping entry is believed to describe a web
# result. Lower than the same-product threshold because the two titles come from
# different sources and differ in length; the distinctiveness test below is what
# stops it matching on the category term alone.
GRAFT_THRESHOLD = 0.6


def graft_shopping_metadata(
    candidates: list[Candidate],
    generic: frozenset[str] = frozenset(),
    threshold: float = GRAFT_THRESHOLD,
) -> tuple[list[Candidate], list[Candidate]]:
    """
    Move price, rating and review count from shopping results onto web results.

    Shopping and web answer different halves of the question. Shopping knows who
    is selling the product, at what price, with what rating — but its links are
    all `google.com/search` interstitials, so there is nothing to fetch. Web
    search knows the real product URL and nothing commercial at all.

    Matching them by title recovers both. Returns (extractable, metadata_only):
    the first have URLs and can be read, the second are real competitors we can
    price but not read.
    """
    web = [c for c in candidates if c.url]
    shopping = [c for c in candidates if not c.url]
    used: set[int] = set()

    for c in web:
        if c.has_commercial_signal:
            continue
        best, best_score, best_i = None, 0.0, -1
        for i, s in enumerate(shopping):
            if i in used:
                continue
            score = token_containment(c.title, s.title)
            if score <= best_score:
                continue
            # Agreement on the category term is not evidence — every title in
            # the set contains it. Require shared tokens that actually identify
            # the product, or a storefront that corroborates the match.
            distinctive = distinctive_overlap(c.title, s.title, generic)
            corroborated = bool(s.platform) and s.platform == c.platform
            if len(distinctive) >= 2 or (corroborated and distinctive):
                best, best_score, best_i = s, score, i

        if best is not None and best_score >= threshold:
            used.add(best_i)
            c.price = c.price or best.price
            c.rating = c.rating or best.rating
            c.review_count = c.review_count or best.review_count
            c.product_id = c.product_id or best.product_id
            # Only adopt the merchant name when the storefronts agree. A
            # shopping entry saying "Target" grafted onto an amazon.com URL
            # produced a competitor labelled Target that lives on Amazon.
            if best.merchant and best.platform == c.platform:
                c.merchant = best.merchant
            log.debug("grafted %s onto %s (containment %.2f)",
                      best.title[:40], c.url[:60], best_score)

    leftover = [s for i, s in enumerate(shopping) if i not in used]
    return web, leftover


def exclude_own_brand(candidates: list[Candidate], brand_name: str) -> list[Candidate]:
    """
    Drop the user's own listings — they are not competitors.

    Anchored to the start of the title, because that is where a brand goes.
    A containment test is not enough: the brand "Pure" appears inside "Doctors
    Best Pure Magnesium", which belongs to somebody else, and deleting it would
    remove a real competitor from the benchmark. A multi-word brand may also
    match as a contiguous phrase anywhere, since some storefronts suffix it.
    """
    brand_tokens = [t for t in (brand_name or "").strip().casefold().split() if t]
    if not brand_tokens:
        return list(candidates)

    n = len(brand_tokens)
    # A brand's own store is its own listing even when the title never names the
    # brand: "High Absorption Magnesium Glycinate Capsules" on naturemade.com is
    # Nature Made's page. Observed live — the title-only check let it through.
    squashed = "".join(brand_tokens)

    kept = []
    for c in candidates:
        if squashed and len(squashed) >= 5:
            host = (c.domain or "").replace("-", "").replace(".", "")
            if squashed in host:
                continue
        title_tokens = c.title.casefold().replace(",", " ").replace("|", " ").split()
        leads = title_tokens[:n] == brand_tokens
        # "Magnesium Glycinate | Nature Made" — only for names distinctive
        # enough that a coincidental match is unlikely.
        contiguous = n >= 2 and any(
            title_tokens[i:i + n] == brand_tokens
            for i in range(max(0, len(title_tokens) - n + 1)))
        if leads or contiguous:
            continue
        kept.append(c)
    return kept


def merge_candidates(
    candidates: list[Candidate],
    *,
    limit: int = 10,
    max_per_domain: int = 4,
    brand_name: str = "",
    generic: frozenset[str] = frozenset(),
) -> tuple[list[Candidate], dict]:
    """
    Deduplicate, cap per storefront and select the final set.

    Returns the chosen candidates and a report of what was dropped, so the
    provider can explain the shape of the result instead of silently presenting
    a thinner cohort than it looks.
    """
    report = {"duplicates": 0, "same_product": 0, "own_brand": 0,
              "domain_capped": 0, "metadata_only": 0, "priced": 0,
              "articles": 0, "considered": len(candidates)}

    before = len(candidates)
    pool = exclude_own_brand(candidates, brand_name)
    report["own_brand"] = before - len(pool)

    # Recover the commercial metadata that shopping has and web results lack.
    extractable, metadata_only = graft_shopping_metadata(pool, generic)
    report["metadata_only"] = len(metadata_only)
    report["priced"] = sum(1 for c in extractable if c.has_commercial_signal)

    # Extractable results first: a competitor whose page we can read is worth
    # more than one we can only price. Metadata-only results still fill out the
    # set when web search found too few.
    pool = sorted(extractable, key=_preference) + sorted(metadata_only, key=_preference)

    chosen: list[Candidate] = []
    seen_urls: set[str] = set()
    seen_product_ids: set[str] = set()
    seen_brand_keys: set[tuple[str, str]] = set()
    per_domain: dict[str, int] = {}

    for c in pool:
        # 0. An editorial round-up is not a competitor. This was already caught
        #    after fetching, but by then it had consumed one of the slots — two
        #    of ten in an observed run. The title is enough to judge it, and the
        #    title is available before anything is spent.
        if looks_like_article(c.title):
            report["articles"] += 1
            continue

        # 1. The same URL twice, usually from two queries. Metadata-only
        #    candidates have no URL and are deduped by title alone, below.
        if c.url:
            url_key = c.url.split("?")[0].rstrip("/").casefold()
            if url_key in seen_urls:
                report["duplicates"] += 1
                continue
        else:
            url_key = ""

        # 2. The engine's own product id — an exact cross-merchant match.
        if c.product_id and c.product_id in seen_product_ids:
            report["duplicates"] += 1
            continue

        # 3. Same brand, same platform: a size or flavour variant. Scoped to one
        #    platform because that is the assumption brand_key rests on.
        bkey = (c.platform, brand_key(c.title))
        if bkey[1] and bkey in seen_brand_keys:
            report["duplicates"] += 1
            continue

        # 4. The same product on a different storefront. Order-independent, so
        #    it survives the two house styles above.
        if any(title_similarity(c.title, other.title) >= SAME_PRODUCT_THRESHOLD
               for other in chosen):
            report["same_product"] += 1
            continue

        # 5. No single storefront may fill the cohort. Without this, a search
        #    returns eight results from one marketplace and the "whole category"
        #    cohort says nothing the same-platform one did not.
        domain = c.domain or f"merchant:{(c.merchant or '?').casefold()}"
        if per_domain.get(domain, 0) >= max_per_domain:
            report["domain_capped"] += 1
            continue

        if url_key:
            seen_urls.add(url_key)
        if c.product_id:
            seen_product_ids.add(c.product_id)
        if bkey[1]:
            seen_brand_keys.add(bkey)
        per_domain[domain] = per_domain.get(domain, 0) + 1
        chosen.append(c)

        if len(chosen) >= limit:
            break

    # Rank is assigned only now, and must stay dense 1..N: it is the join key
    # between listings, scored rows and the model's own attribution by rank.
    for i, c in enumerate(chosen, start=1):
        c.position = c.position or i

    log.info("merged %d candidates -> %d (%d dup, %d same-product, %d own-brand, "
             "%d capped, %d articles)",
             report["considered"], len(chosen), report["duplicates"],
             report["same_product"], report["own_brand"], report["domain_capped"],
             report["articles"])
    return chosen, report
