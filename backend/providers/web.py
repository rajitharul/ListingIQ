"""
Competitors from the open web, on whatever platform they sell.

The Amazon-only path asked one marketplace's search box for a category term.
This asks the web who is actually selling the product, and then reads each
result wherever it lives — a marketplace listing, an eBay item, a brand's own
Shopify store. The platform stops being an assumption baked into the provider
and becomes an observed property of each competitor.

    query plan  ->  discovery (Serper)  ->  merge & dedupe  ->  extraction
                    who is selling this      one row per          read the page
                    and where                real product         (Firecrawl)

Three properties this has to preserve, all of them load-bearing:

* **What we did not observe stays unobserved.** A competitor found through an
  organic web result has no price and no rating. Those stay empty rather than
  becoming zero, because the statistics layer averages them.
* **A page we could not read is still a real competitor.** It is kept and shown,
  with `extraction_status` saying why, but excluded from the benchmark so a
  failure to read cannot masquerade as a badly written listing.
* **Degrading is not the same as estimating.** If extraction fails outright,
  discovery data is still observed data. The result stays `web_search` and says
  what was thin — it never falls through to the model-estimated provider, which
  would be a lie in the opposite direction.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from config import COMPETITOR_MAX_PER_DOMAIN, SERPER_COUNTRY, SERPER_LANGUAGE
from models.schemas import (
    CategoryClassification,
    CompetitorListing,
    CompetitorScoutResult,
    ExtractedEntities,
)
from normalize import significant_tokens
from providers import platforms
from providers.base import ProviderError
from providers.discovery.merge import merge_candidates
from providers.discovery.serper import SerperDiscovery
from providers.extract.composite import PlatformAwareExtractor
from providers.extract.model import fill_gaps
from providers.query import build_query_plan

log = logging.getLogger("listingiq.providers.web")


class WebSearchProvider:
    """Discovery via search, extraction via page fetch. Platform-agnostic."""

    name = "web_search"

    def __init__(self, discovery=None, extractor=None):
        # Injected for tests; defaults are the real vendors.
        self._discovery = discovery or SerperDiscovery()
        self._extractor = extractor or PlatformAwareExtractor()

    async def fetch(
        self,
        category: CategoryClassification,
        platform: str,
        brand_name: str = "",
        limit: int = 10,
        *,
        entities: ExtractedEntities | None = None,
        country: str = "",
        language: str = "",
    ) -> CompetitorScoutResult:
        plan = build_query_plan(
            category, entities,
            platform=platform, brand_name=brand_name, limit=limit,
            country=country or SERPER_COUNTRY,
            language=language or SERPER_LANGUAGE,
        )

        candidates = await self._discovery.discover(plan)
        # Tokens every competitor in this category shares. Matching on these is
        # not evidence that two listings are the same product.
        generic = significant_tokens(plan.subcategory)

        chosen, report = merge_candidates(
            candidates, limit=limit,
            max_per_domain=COMPETITOR_MAX_PER_DOMAIN,
            brand_name=brand_name,
            generic=generic,
        )
        if not chosen:
            raise ProviderError(
                self.name,
                f"no distinct competitors for {plan.subcategory!r} "
                f"(considered {report['considered']})",
                retryable=False,
            )

        # Only candidates with a real URL are fetched. Shopping results carry
        # merchant, price and rating but no address — their link is a Google
        # interstitial — so they are real, priced competitors that simply cannot
        # be read. Sending them to the extractor would spend a page credit on a
        # search redirect and then score it as somebody's listing copy.
        fetchable = [c for c in chosen if c.url]
        pages = await self._extractor.extract_many([(c.url, c.title) for c in fetchable])
        await fill_gaps(pages, caller="web_search.extract")
        by_url = {p.url: p for p in pages}

        listings: list[CompetitorListing] = []
        for rank, cand in enumerate(chosen, start=1):
            page = by_url.get(cand.url) if cand.url else None
            read = bool(page) and page.status == "extracted"
            note = (page.note if page else
                    "found in shopping results, which carry no page address")

            # Discovery wins on commercial metadata, the page wins on copy.
            # Neither overwrites the other's better information with a blank.
            listings.append(CompetitorListing(
                rank=rank,
                title=(page.title if read and page.title else cand.title) or "",
                description=(page.description if read else "") or "",
                bullet_points=(page.bullet_points if read else []) or [],
                brand_name=(page.brand_name if read and page.brand_name else "") or "",
                price=cand.price or (page.price if read else "") or "",
                rating=cand.rating or (page.rating if read else 0.0),
                review_count=cand.review_count or (page.review_count if read else 0),
                badges=[],
                url=cand.url,
                platform=cand.platform,
                merchant=cand.merchant,
                domain=cand.domain,
                source_position=cand.position,
                extraction_status=page.status if page else "discovery_only",
                extraction_note=note,
                # A listing we could not read properly is shown but not scored:
                # grading our own extraction failure would lower the competitor
                # mean and flatter the user's percentile.
                counts_toward_benchmark=bool(read and page.has_copy),
            ))

        return self._result(plan, listings, report)

    def _result(self, plan, listings, report) -> CompetitorScoutResult:
        breakdown: dict[str, int] = {}
        for l in listings:
            key = l.platform or "unknown"
            breakdown[key] = breakdown.get(key, 0) + 1

        extracted = sum(1 for l in listings if l.extraction_status == "extracted")
        discovery_only = sum(1 for l in listings if l.extraction_status == "discovery_only")
        failed = sum(1 for l in listings if l.extraction_status == "failed")
        scoreable = sum(1 for l in listings if l.counts_toward_benchmark)

        notes: list[str] = []
        mix = ", ".join(f"{n} {platforms.label_for(p)}" for p, n in
                        sorted(breakdown.items(), key=lambda kv: -kv[1]))
        if mix:
            notes.append(f"found across {len(breakdown)} platform(s): {mix}")
        if report.get("same_product"):
            notes.append(f"{report['same_product']} duplicate listing(s) of the same product merged")
        if report.get("articles"):
            notes.append(f"{report['articles']} review article(s) excluded — "
                         "they rank for the category but sell nothing")
        if report.get("domain_capped"):
            notes.append(f"{report['domain_capped']} extra result(s) from one storefront excluded "
                         "so no single site fills the set")
        # Count what is actually excluded from the benchmark, not just what
        # errored. A page can return HTTP 200 and still yield no selling copy
        # once navigation is filtered out — it is shown as a competitor and not
        # scored, and the note has to say so or the numbers disagree.
        unscored = len(listings) - scoreable
        if unscored:
            notes.append(f"{unscored} of {len(listings)} page(s) could not be read in full; "
                         "shown as competitors but excluded from the benchmark")
        without_price = sum(1 for l in listings if not l.price)
        if without_price:
            notes.append(f"{without_price} of {len(listings)} without a published price")
        if report.get("metadata_only"):
            notes.append(f"{report['metadata_only']} found via shopping results only — "
                         "priced and ranked, but their pages could not be addressed")

        log.info("✓ web_search %d competitors across %d platforms (%d scoreable)",
                 len(listings), len(breakdown), scoreable)

        return CompetitorScoutResult(
            listings=listings,
            search_query=plan.shopping[0] if plan.shopping else plan.subcategory,
            platform=plan.platform,
            data_source=self.name,
            fetched_at=datetime.now(timezone.utc).isoformat(),
            from_cache=False,
            provider_note="; ".join(notes),
            platform_breakdown=breakdown,
            queries=list(plan.all_queries),
            discovery_source=self._discovery.name,
            extraction_source=self._extractor.name,
            extracted_count=extracted,
            discovery_only_count=discovery_only,
            failed_count=failed,
        )
