"""
Reading Amazon listings through the product API instead of scraping them.

Verified against live pages, not assumed: an Amazon product page returns
**no `schema.org/Product` markup at all** and about 150,000 characters of
markdown, almost all of it navigation — breadcrumbs, the global menu, the footer
link columns, "open prime modalclose prime modal". Generic extraction on that
yields bullet points that are category links, which are then scored on the
rubric as though the seller had written them.

The Rainforest product endpoint returns `feature_bullets` and `description` as
clean fields. It is one request per listing, the same cost shape as a page
fetch, and the quality difference is not marginal.

So Amazon is routed here when a key is configured, and falls through to the
generic extractor when it is not. Nothing else changes: the rest of the web is
read the same way it was.
"""
from __future__ import annotations

import asyncio
import logging
import re

from config import RAINFOREST_API_KEY, RAINFOREST_MAX_CONCURRENCY, RAINFOREST_TIMEOUT_SECONDS
from providers.base import ProviderError
from providers.extract.base import DISCOVERY_ONLY, STRUCTURED, ExtractedPage
from providers.extract.structured import clean_text, strip_marketplace_prefix
from providers.rainforest import RainforestProvider, _DOMAINS

log = logging.getLogger("listingiq.providers.extract_amazon")

_ASIN_RE = re.compile(r"/(?:dp|gp/product|gp/aw/d)/([A-Z0-9]{10})(?:[/?]|$)", re.I)
_DOMAIN_RE = re.compile(r"https?://(?:www\.)?(amazon\.[a-z.]+)", re.I)


def asin_from_url(url: str) -> str:
    """The ASIN in an Amazon product URL, or "" if it is not one."""
    m = _ASIN_RE.search(url or "")
    return m.group(1).upper() if m else ""


def domain_from_url(url: str, default: str = "amazon.com") -> str:
    m = _DOMAIN_RE.search(url or "")
    return m.group(1).lower() if m else default


class AmazonExtractor:
    """Reads Amazon product pages through the Rainforest API."""

    name = "rainforest_product"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key if api_key is not None else RAINFOREST_API_KEY
        self._provider = RainforestProvider(self.api_key)

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def handles(self, url: str) -> bool:
        return bool(self.available and asin_from_url(url))

    async def extract_many(self, targets: list[tuple[str, str]]) -> list[ExtractedPage]:
        if not targets:
            return []
        if not self.available:
            return [ExtractedPage(url=u, status=DISCOVERY_ONLY,
                                  note="RAINFOREST_API_KEY is not set")
                    for u, _ in targets]

        sem = asyncio.Semaphore(max(1, RAINFOREST_MAX_CONCURRENCY))
        from providers import http as _http

        async def one(client, url: str) -> ExtractedPage:
            page = ExtractedPage(url=url)
            asin = asin_from_url(url)
            if not asin:
                page.status = DISCOVERY_ONLY
                page.note = "not an Amazon product URL"
                return page
            try:
                async with sem:
                    body = await self._provider._request(client, {
                        "type": "product",
                        "amazon_domain": domain_from_url(url),
                        "asin": asin,
                    })
            except ProviderError as e:
                # Per-listing isolation, as everywhere else: one failed lookup
                # degrades one competitor, never the run.
                page.status = DISCOVERY_ONLY
                page.note = e.detail
                return page
            except Exception as e:                              # noqa: BLE001
                page.status = DISCOVERY_ONLY
                page.note = f"unexpected error: {type(e).__name__}"
                return page

            product = body.get("product") or {}
            if not product:
                page.status = DISCOVERY_ONLY
                page.note = "no product returned for this ASIN"
                return page

            page.title = strip_marketplace_prefix(clean_text(product.get("title") or ""))
            page.description = self._provider._description(product)
            page.bullet_points = [clean_text(b) for b in (product.get("feature_bullets") or []) if b][:8]
            page.brand_name = clean_text(product.get("brand") or "")
            page.price = self._provider._price(product)
            page.rating = float(product.get("rating") or 0.0)
            page.review_count = int(product.get("ratings_total") or 0)
            page.body = "\n".join([page.title, *page.bullet_points, page.description])
            page.status = "extracted"
            page.method = STRUCTURED
            return page

        async with _http.make_client(RAINFOREST_TIMEOUT_SECONDS) as client:
            pages = await asyncio.gather(*(one(client, u) for u, _ in targets))

        read = sum(1 for p in pages if p.status == "extracted")
        log.info("✓ rainforest read %d/%d Amazon listings", read, len(pages))
        return list(pages)
