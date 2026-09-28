"""
Serper — Google Shopping and Google Search as JSON.

Two channels, because they fail in opposite directions:

  * `/shopping` returns merchant-attributed product results with price, rating
    and review count already populated. Excellent recall on marketplaces, and
    structurally weak on direct-to-consumer stores, which often have no
    merchant feed at all.
  * `/search` returns organic web results. It finds the brand's own store, and
    it carries no commercial metadata whatsoever — no price, no rating.

Running only the first gives a "whole category" cohort that is just more
marketplaces. Running only the second throws away price and rating we would
otherwise have to extract. So both run, and the results are merged.

The key travels in the `X-API-KEY` header, not a query string — unlike the
Rainforest key, which is a URL parameter and stays out of the logs only because
the httpx logger is pinned to WARNING in main.py.
"""
from __future__ import annotations

import asyncio
import logging

import httpx

from config import (
    SERPER_API_KEY,
    SERPER_BASE_URL,
    SERPER_RESULTS_PER_QUERY,
    SERPER_TIMEOUT_SECONDS,
)
from providers import http as _http
from providers.base import ProviderError
from providers import platforms
from providers.discovery.base import Candidate

log = logging.getLogger("listingiq.providers.serper")

# Web results that are never a product page, however well they rank.
_NON_PRODUCT_HOSTS = frozenset({
    "wikipedia.org", "reddit.com", "quora.com", "youtube.com", "facebook.com",
    "instagram.com", "pinterest.com", "tiktok.com", "x.com", "twitter.com",
    "nih.gov", "ncbi.nlm.nih.gov", "webmd.com", "healthline.com", "mayoclinic.org",
    "medicalnewstoday.com", "consumerreports.org", "nytimes.com", "forbes.com",
    "wirecutter.com", "news.google.com", "linkedin.com", "yelp.com",
})

# Paths that mark an index, an article or a search results page rather than one
# product. Verified against live results: a category search on a marketplace
# ranks well for a category term and is not a competitor.
_NON_PRODUCT_MARKERS = (
    "/blog/", "/news/", "/article", "/guide", "/reviews/", "/category/",
    "/collections/all", "/search", "?q=", "&q=", "/s?k=", "/b?node=",
    "/sch/", "/browse/", "/shop/", "/deals", "/best-sellers", "/gp/bestsellers",
    "/c/", "/pl/", "_verified_products", "/directory", "/brands",
)

# Hosts whose links are interstitials or aggregators, never a product page.
# Google Shopping returns every result as a google.com/search redirect, so a
# shopping link is structurally unusable for extraction.
_REDIRECT_HOSTS = frozenset({"google.com", "google.co.uk", "googleadservices.com",
                             "bing.com", "duckduckgo.com", "shopping.google.com"})


def _classify(response: httpx.Response) -> ProviderError | None:
    if response.status_code in (401, 403):
        return ProviderError("serper", "invalid API key", retryable=False)
    if response.status_code == 402:
        return ProviderError("serper", "out of credits", retryable=False)
    if response.status_code == 429:
        return ProviderError("serper", "rate limited by provider", retryable=True)
    if response.status_code >= 500:
        return ProviderError("serper", f"HTTP {response.status_code}", retryable=True)
    if response.status_code >= 400:
        return ProviderError(
            "serper", f"HTTP {response.status_code}: {response.text[:200]}", retryable=False)
    return None


def _number(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def looks_like_product(url: str) -> bool:
    """
    A cheap, conservative filter on organic web results.

    Encyclopaedia entries, clinical papers and "best of" round-ups outrank
    actual product pages for most category terms. Extracting them would spend a
    page credit and then score an article as though it were listing copy.
    """
    if not url:
        return False
    low = url.lower()
    host = low.split("//")[-1].split("/")[0].removeprefix("www.")
    if any(host == h or host.endswith("." + h) for h in _NON_PRODUCT_HOSTS):
        return False
    if any(host == h or host.endswith("." + h) for h in _REDIRECT_HOSTS):
        return False
    # A bare domain with no path is a storefront home page, not a listing.
    path = low.split("//")[-1].split("/", 1)
    if len(path) < 2 or not path[1].split("?")[0].strip("/"):
        return False
    return not any(marker in low for marker in _NON_PRODUCT_MARKERS)


class SerperDiscovery:
    name = "serper"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key if api_key is not None else SERPER_API_KEY

    async def _post(self, client: httpx.AsyncClient, path: str, body: dict) -> dict:
        return await _http.request_json(
            client, "POST", f"{SERPER_BASE_URL.rstrip('/')}/{path}",
            provider=self.name,
            classify=_classify,
            json_body=body,
            headers={"X-API-KEY": self.api_key, "Content-Type": "application/json"},
        )

    @staticmethod
    def _from_shopping(items: list[dict]) -> list[Candidate]:
        """
        Shopping results are **metadata, not addresses**.

        Verified against the live API: every `link` is a
        `google.com/search?ibp=oshop&...` interstitial, never the merchant's own
        product page. So the URL is dropped rather than carried — fetching it
        would scrape a Google Shopping page and score it as listing copy — and
        the platform comes from the merchant name in `source` instead.

        What survives is genuinely valuable and expensive to get elsewhere: who
        is actually selling this, at what price, with what rating, ranked by
        commercial relevance. `merge` grafts that onto the matching web result,
        which does have a real URL.
        """
        out: list[Candidate] = []
        for i, item in enumerate(items or [], start=1):
            title = (item.get("title") or "").strip()
            if not title:
                continue
            merchant = (item.get("source") or "").strip()
            c = Candidate(
                url="",
                title=title,
                merchant=merchant,
                # Preserved as the source string, never reformatted — currency
                # and locale are the merchant's, not ours to normalise.
                price=(item.get("price") or "").strip(),
                rating=_number(item.get("rating")),
                review_count=_int(item.get("ratingCount")),
                position=_int(item.get("position")) or i,
                channel="shopping",
                product_id=str(item.get("productId") or ""),
            )
            out.append(c)
        return out

    @staticmethod
    def _from_web(items: list[dict]) -> list[Candidate]:
        out: list[Candidate] = []
        for i, item in enumerate(items or [], start=1):
            link = (item.get("link") or "").strip()
            if not link or not looks_like_product(link):
                continue
            # Deliberately no price and no rating: an organic result carries
            # neither, and inventing a 0.0 would be read downstream as a fact.
            out.append(Candidate(
                url=link,
                title=(item.get("title") or "").strip(),
                position=_int(item.get("position")) or i,
                channel="web",
            ))
        return out

    async def discover(self, plan) -> list[Candidate]:
        """Run every query in the plan and return the candidates, in rank order."""
        if not self.api_key:
            raise ProviderError(self.name, "SERPER_API_KEY is not set", retryable=False)

        num = max(plan.limit * 2, SERPER_RESULTS_PER_QUERY)
        common = {"gl": plan.country, "hl": plan.language, "num": num}

        async with _http.make_client(SERPER_TIMEOUT_SECONDS) as client:
            async def shopping(q: str):
                body = await self._post(client, "shopping", {"q": q, **common})
                return self._from_shopping(body.get("shopping") or [])

            async def web(q: str):
                body = await self._post(client, "search", {"q": q, **common})
                return self._from_web(body.get("organic") or [])

            tasks = [shopping(q) for q in plan.shopping] + [web(q) for q in plan.web]
            log.info("↗ serper %d queries (%d shopping, %d web)",
                     len(tasks), len(plan.shopping), len(plan.web))
            # A single failing query must not lose the others: partial discovery
            # is far better than none, and the caller reports what was thin.
            settled = await asyncio.gather(*tasks, return_exceptions=True)

        candidates: list[Candidate] = []
        failures: list[BaseException] = []
        for result in settled:
            if isinstance(result, BaseException):
                failures.append(result)
                continue
            candidates.extend(result)

        if not candidates:
            # Re-raise the original error rather than wrapping it. Wrapping
            # discarded `retryable`, so a transient 429 that every query hit
            # was reported to the caller as a permanent failure.
            if failures:
                first = failures[0]
                if isinstance(first, ProviderError):
                    raise first
                raise ProviderError(self.name, str(first), retryable=True) from first
            raise ProviderError(
                self.name, f"no results for {plan.subcategory!r}", retryable=False)

        if failures:
            log.warning("serper: %d/%d queries failed — %s",
                        len(failures), len(settled), failures[0])
        log.info("✓ serper %d candidates from %d queries", len(candidates), len(settled))
        return candidates
