"""
Rainforest API competitor provider — real marketplace data.

Two calls are needed per subcategory, because Amazon search results do not carry
listing copy:

  1. one `search` request   -> the top N ASINs, with title, price, rating,
                               ratings_total and badges
  2. N `product` requests   -> feature_bullets and description for each ASIN

That is 11 upstream requests for a top-10 benchmark. The product lookups run
concurrently, bounded by a semaphore, and the whole result is cached by
`providers/cache.py` so the cost is amortised across runs of the same
subcategory rather than paid per pipeline invocation.

A listing that fails its product lookup is still returned, with its title, price
and rating from the search result and empty copy — a partial competitor is more
useful than a missing one, and the analyser handles empty bullets.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx

from config import (
    RAINFOREST_API_KEY,
    RAINFOREST_BASE_URL,
    RAINFOREST_MAX_CONCURRENCY,
    RAINFOREST_TIMEOUT_SECONDS,
)
from models.schemas import (
    CategoryClassification,
    CompetitorListing,
    CompetitorScoutResult,
)
from normalize import dedupe_by_brand, registrable_domain
from providers import platforms
from providers.base import ProviderError
from providers import http as _http   # module, not `from ... import make_client`:
                                      # a bound name cannot be patched by tests

log = logging.getLogger("listingiq.providers.rainforest")

# Rainforest speaks per-marketplace domains rather than country codes.
_DOMAINS = {
    "amazon": "amazon.com",
    "amazon_us": "amazon.com",
    "amazon_uk": "amazon.co.uk",
    "amazon_de": "amazon.de",
    "amazon_ca": "amazon.ca",
    "amazon_au": "amazon.com.au",
}


class RainforestProvider:
    name = "rainforest_api"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or RAINFOREST_API_KEY

    # ── HTTP ─────────────────────────────────────────────────────
    async def _request(self, client: httpx.AsyncClient, params: dict) -> dict:
        try:
            r = await client.get(RAINFOREST_BASE_URL, params={**params, "api_key": self.api_key})
        except httpx.TimeoutException as e:
            raise ProviderError(self.name, f"timed out: {e}") from e
        except httpx.HTTPError as e:
            raise ProviderError(self.name, f"connection error: {e}") from e

        if r.status_code == 401:
            raise ProviderError(self.name, "invalid API key", retryable=False)
        if r.status_code == 402:
            raise ProviderError(self.name, "out of credits", retryable=False)
        if r.status_code == 429:
            raise ProviderError(self.name, "rate limited by provider")
        if r.status_code >= 400:
            raise ProviderError(self.name, f"HTTP {r.status_code}: {r.text[:200]}")

        try:
            body = r.json()
        except ValueError as e:
            raise ProviderError(self.name, f"non-JSON response: {e}") from e

        info = body.get("request_info") or {}
        if info.get("success") is False:
            raise ProviderError(
                self.name, info.get("message", "provider reported failure"),
                retryable=False,
            )
        return body

    # ── Field mapping ────────────────────────────────────────────
    @staticmethod
    def _price(node: dict) -> str:
        """Prefer the provider's formatted string, fall back to value+symbol."""
        price = node.get("price") or {}
        if isinstance(price, dict):
            if price.get("raw"):
                return str(price["raw"])
            if price.get("value") is not None:
                return f"{price.get('symbol', '')}{price['value']}"
        buybox = (node.get("buybox_winner") or {}).get("price") or {}
        if buybox.get("raw"):
            return str(buybox["raw"])
        return ""

    @staticmethod
    def _badges(search_item: dict, product: dict | None) -> list[str]:
        """
        Badge names vary between the search and product payloads — verified
        against live responses, where search items carry `amazons_choice` as an
        object rather than the `is_amazons_choice` flag the docs imply.
        """
        product = product or {}
        badges: list[str] = []

        # `bestsellers_rank` is a category RANKING array present on almost every
        # product — verified live: rank 118 in "Health & Household". It is not
        # the Best Seller badge. Only an explicit badge, or an actual #1 rank,
        # earns the label; otherwise every competitor looks like a bestseller
        # and the competitive analysis is meaningless.
        if search_item.get("bestseller"):
            badges.append("Best Seller")
        elif any(r.get("rank") == 1 for r in (product.get("bestsellers_rank") or [])
                 if isinstance(r, dict)):
            badges.append("#1 Best Seller")

        if (search_item.get("amazons_choice") or product.get("amazons_choice")):
            badges.append("Amazon's Choice")
        if search_item.get("is_prime") or product.get("is_prime"):
            badges.append("Prime")
        if (search_item.get("deal") or {}).get("badge_text"):
            badges.append(str(search_item["deal"]["badge_text"]))
        if search_item.get("coupon"):
            badges.append("Coupon")
        if search_item.get("climate_pledge_friendly") or product.get("climate_pledge_friendly"):
            badges.append("Climate Pledge Friendly")
        return badges

    @staticmethod
    def _description(product: dict) -> str:
        """
        Listing body copy, which is frequently absent.

        Amazon listings increasingly carry no plain description block at all —
        the copy lives in A+ content, which Rainforest returns as images rather
        than text. Verified live: a top-ranked listing with 20k reviews had 5
        bullets and zero description characters. Fall back to the A+ brand story
        text when it exists, and otherwise return empty rather than inventing
        anything.
        """
        if product.get("description"):
            return str(product["description"])[:2000]
        aplus = product.get("a_plus_content") or {}
        for key in ("company_description_text", "company_description_title"):
            if aplus.get(key):
                return str(aplus[key])[:2000]
        return ""

    @staticmethod
    def _url(search_item: dict, domain: str) -> str:
        """
        A clean, verifiable product URL.

        Rainforest returns tracking-laden `/sspa/click?...` links for some
        results. A customer clicking through to check a competitor should land
        on the product page, so the canonical /dp/ form is built from the ASIN.
        """
        asin = search_item.get("asin")
        if asin:
            return f"https://www.{domain}/dp/{asin}"
        return search_item.get("link") or ""

    # ── Fetch ────────────────────────────────────────────────────
    async def fetch(
        self,
        category: CategoryClassification,
        platform: str,
        brand_name: str = "",
        limit: int = 10,
    ) -> CompetitorScoutResult:
        if not self.api_key:
            raise ProviderError(self.name, "RAINFOREST_API_KEY is not set", retryable=False)

        domain = _DOMAINS.get(platform.lower(), "amazon.com")
        search_term = category.subcategory or category.category

        async with _http.make_client(RAINFOREST_TIMEOUT_SECONDS) as client:
            log.info("↗ rainforest search  term=%r domain=%s", search_term, domain)
            body = await self._request(client, {
                "type": "search",
                "amazon_domain": domain,
                "search_term": search_term,
                "sort_by": "featured",
            })

            results = body.get("search_results") or []
            # Sponsored placements are ads, not organic top sellers, and the
            # user's own brand is not a competitor.
            candidates = [
                r for r in results
                if not r.get("sponsored")
                and r.get("asin")
                and (not brand_name or brand_name.lower() not in (r.get("title") or "").lower())
            ]
            # Deduplicate before paying for product detail. Search returns many
            # size and flavour variants of the same brand; without this, one
            # brand can occupy half "the top 10" and drag the benchmark average
            # toward itself. Free here — the search response is already paid for.
            organic = dedupe_by_brand(candidates, limit=limit)
            duplicates = len(candidates[:limit]) - len(organic) if candidates else 0

            if not organic:
                raise ProviderError(self.name, f"no organic results for {search_term!r}")

            log.info("↙ rainforest search  %d distinct brands of %d results "
                     "(%d variant duplicates dropped); fetching copy",
                     len(organic), len(results), max(0, duplicates))

            sem = asyncio.Semaphore(RAINFOREST_MAX_CONCURRENCY)

            async def detail(item: dict) -> dict | None:
                async with sem:
                    try:
                        d = await self._request(client, {
                            "type": "product",
                            "amazon_domain": domain,
                            "asin": item["asin"],
                        })
                        return d.get("product") or {}
                    except ProviderError as e:
                        # Partial data beats dropping a competitor entirely.
                        log.warning("product lookup failed for %s: %s", item["asin"], e)
                        return None

            details = await asyncio.gather(*(detail(i) for i in organic))

        listings: list[CompetitorListing] = []
        for rank, (item, product) in enumerate(zip(organic, details), start=1):
            product = product or {}
            url = self._url(item, domain)
            # `product` is empty when the detail lookup failed, which is the
            # difference between a listing we read and one we only saw in search.
            read_in_full = bool(product)
            listings.append(CompetitorListing(
                rank=rank,
                title=product.get("title") or item.get("title") or "",
                description=self._description(product),
                bullet_points=[b for b in (product.get("feature_bullets") or []) if b][:6],
                brand_name=product.get("brand") or "",
                price=self._price(product) or self._price(item),
                rating=float(product.get("rating") or item.get("rating") or 0.0),
                review_count=int(product.get("ratings_total") or item.get("ratings_total") or 0),
                badges=self._badges(item, product),
                url=url,
                platform=platforms.detect(url) if url else "amazon",
                merchant=platforms.label_for(platform),
                domain=registrable_domain(url),
                source_position=rank,
                extraction_status="extracted" if read_in_full else "discovery_only",
                extraction_note="" if read_in_full else "product lookup failed",
            ))

        # Report data shape honestly. Missing descriptions are normal on Amazon
        # (copy lives in A+ images), but the analyser measures description
        # length, so a run where most competitors have none should say so
        # rather than letting that read as "competitors write short copy".
        missing_copy = sum(1 for l in listings if not l.bullet_points)
        missing_desc = sum(1 for l in listings if not l.description)
        notes = []
        if duplicates > 0:
            notes.append(f"{duplicates} same-brand variant(s) excluded so the top "
                         f"{len(listings)} are distinct brands")
        if missing_copy:
            notes.append(f"{missing_copy} of {len(listings)} without bullet points")
        if missing_desc:
            notes.append(
                f"{missing_desc} of {len(listings)} have no description block "
                "(Amazon A+ content is not text-extractable)"
            )
        note = "; ".join(notes)
        log.info("✓ rainforest  %d competitors, %d upstream requests%s",
                 len(listings), 1 + len(organic), f" ({note})" if note else "")

        breakdown: dict[str, int] = {}
        for l in listings:
            breakdown[l.platform or "amazon"] = breakdown.get(l.platform or "amazon", 0) + 1

        return CompetitorScoutResult(
            listings=listings,
            search_query=search_term,
            platform=platform,
            data_source=self.name,
            fetched_at=datetime.now(timezone.utc).isoformat(),
            from_cache=False,
            provider_note=note,
            platform_breakdown=breakdown,
            queries=[search_term],
            discovery_source="rainforest_search",
            extraction_source="rainforest_product",
            extracted_count=sum(1 for l in listings if l.extraction_status == "extracted"),
            discovery_only_count=sum(1 for l in listings if l.extraction_status == "discovery_only"),
            failed_count=0,
        )
