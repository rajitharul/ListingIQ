"""
Reading competitor pages, whatever site they are on.

Firecrawl is the fetcher for every URL: one code path, and it handles the
JavaScript rendering and bot-blocking that make a plain HTTP GET useless on the
large marketplaces. What it returns is parsed here rather than by Firecrawl's
own extraction endpoint, because that would be a second model we do not control,
cannot evaluate, and would not see in our token accounting. Firecrawl fetches;
we parse.

Order of preference per page:

  1. `schema.org/Product` JSON-LD out of the raw HTML — exact and free.
  2. Bullet points as the page renders them, taken verbatim from markdown.
  3. A single batched model call for whatever is still missing (see model.py).

The quality guard is the important part. A page that returns navigation chrome
or a cookie interstitial produces plausible-looking text that flows straight
into the scorer and gets graded as listing copy — dragging the benchmark mean
down and *inflating* the user's percentile. A flattering wrong number is the
failure nobody reports as a bug, so thin pages are detected and excluded from
scoring here, while still being shown as real competitors.
"""
from __future__ import annotations

import asyncio
import logging
import re

import httpx

from config import (
    FIRECRAWL_API_KEY,
    FIRECRAWL_BASE_URL,
    FIRECRAWL_MAX_CONCURRENCY,
    FIRECRAWL_TIMEOUT_SECONDS,
    COMPETITOR_CACHE_TTL_HOURS,
    EXTRACT_DEADLINE_SECONDS,
    MIN_EXTRACTED_CHARS,
)
from normalize import significant_tokens
from providers import http as _http
from providers.base import ProviderError
from providers.extract.base import (
    DISCOVERY_ONLY, FAILED, MODEL, STRUCTURED, ExtractedPage,
)
from normalize import looks_like_article
from providers.extract.structured import (
    bullets_from_markdown, clean_text, parse_product, strip_marketplace_prefix,
)

log = logging.getLogger("listingiq.providers.firecrawl")


def _classify(response: httpx.Response) -> ProviderError | None:
    if response.status_code in (401, 403):
        return ProviderError("firecrawl", "invalid API key", retryable=False)
    if response.status_code == 402:
        return ProviderError("firecrawl", "out of credits", retryable=False)
    if response.status_code == 429:
        return ProviderError("firecrawl", "rate limited by provider", retryable=True)
    if response.status_code >= 500:
        return ProviderError("firecrawl", f"HTTP {response.status_code}", retryable=True)
    if response.status_code >= 400:
        return ProviderError(
            "firecrawl", f"HTTP {response.status_code}: {response.text[:200]}",
            retryable=False)
    return None


# An editorial round-up outranks real product pages for most category terms, and
# a domain blocklist does not scale — there is always another supplements blog.
# The shape of the title is the durable signal.
def is_usable(body: str, expected_title: str = "") -> tuple[bool, str]:
    """
    Whether extracted text is listing copy or something else entirely.

    Two silent failure modes this catches: a JS-heavy page that returns only
    navigation, and a consent interstitial that returns a wall of legal text.
    Both look like content. Neither describes the product.
    """
    text = (body or "").strip()
    if len(text) < MIN_EXTRACTED_CHARS:
        return False, f"only {len(text)} chars of body copy"

    if expected_title:
        wanted = significant_tokens(expected_title)
        if wanted:
            overlap = len(wanted & significant_tokens(text))
            # Two distinctive words shared with the title we searched for. A
            # cookie banner shares none.
            if overlap < min(2, len(wanted)):
                return False, "page content does not match the product title"
    return True, ""


class FirecrawlExtractor:
    name = "firecrawl"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key if api_key is not None else FIRECRAWL_API_KEY

    async def _scrape(self, client: httpx.AsyncClient, url: str) -> dict:
        body = await _http.request_json(
            client, "POST", f"{FIRECRAWL_BASE_URL.rstrip('/')}/scrape",
            provider=self.name,
            classify=_classify,
            json_body={
                "url": url,
                "formats": ["markdown", "rawHtml"],
                # Firecrawl's "main content" heuristic picks the wrong region on
                # storefronts whose product copy sits outside a <main>/<article>
                # landmark, and returns the nav and promo chrome instead. Measured
                # on one Shopify product page: True gave 3,245 characters that
                # never said "creatine", False gave 9,559 that did. Every page in
                # a run then failed `is_usable` and left the benchmark empty.
                # The quality guard below is what keeps the extra chrome honest.
                "onlyMainContent": False,
                "blockAds": True,
                # Let Firecrawl serve its own cache for as long as ours is
                # valid: a repeat fetch inside the TTL then costs nothing.
                "maxAge": max(0, COMPETITOR_CACHE_TTL_HOURS) * 3_600_000,
                "timeout": int(FIRECRAWL_TIMEOUT_SECONDS * 1000),
            },
            headers={"Authorization": f"Bearer {self.api_key}",
                     "Content-Type": "application/json"},
        )
        return body.get("data") or {}

    async def extract_one(
        self, client: httpx.AsyncClient, url: str, expected_title: str = ""
    ) -> ExtractedPage:
        """Read one page. Never raises: a failure is a status, not an exception."""
        page = ExtractedPage(url=url)
        try:
            data = await self._scrape(client, url)
        except ProviderError as e:
            # Credit exhaustion and rate limits are reported per page rather
            # than failing the run: discovery already gave us a real competitor.
            page.status = DISCOVERY_ONLY
            page.note = e.detail
            return page
        except Exception as e:                       # noqa: BLE001 - isolation
            page.status = DISCOVERY_ONLY
            page.note = f"unexpected error: {type(e).__name__}"
            return page

        markdown = clean_text(data.get("markdown") or "")
        raw_html = data.get("rawHtml") or ""
        meta = data.get("metadata") or {}

        ok, why = is_usable(markdown, expected_title)
        if not ok:
            page.status = FAILED
            page.note = why
            page.body = markdown
            return page

        structured = parse_product(raw_html)
        raw_title = structured.get("title") or clean_text(meta.get("title") or "")

        if looks_like_article(raw_title, bool(structured)):
            page.status = FAILED
            page.note = "this page reviews products rather than selling one"
            page.body = markdown
            return page

        # "Amazon.com: Pure Encapsulations Magnesium" is the marketplace talking,
        # not the seller, and it skews every title-length statistic.
        page.title = strip_marketplace_prefix(raw_title)
        page.description = structured.get("description") or ""
        page.brand_name = structured.get("brand_name") or ""
        page.price = structured.get("price") or ""
        page.rating = float(structured.get("rating") or 0.0)
        page.review_count = int(structured.get("review_count") or 0)
        page.bullet_points = bullets_from_markdown(markdown)
        page.body = markdown
        page.status = "extracted"
        page.method = STRUCTURED if structured else MODEL
        return page

    async def extract_many(
        self, targets: list[tuple[str, str]]
    ) -> list[ExtractedPage]:
        """
        Read many pages concurrently, bounded, under one overall deadline.

        `targets` is (url, expected_title). The deadline is the bound the
        Rainforest path never had: it has a per-request timeout but no total
        one, so a slow tail can hang a run well past the time the pipeline
        advertises. Whatever has not returned by the deadline is marked
        discovery-only and the run continues.
        """
        if not targets:
            return []
        if not self.api_key:
            return [ExtractedPage(url=u, status=DISCOVERY_ONLY,
                                  note="FIRECRAWL_API_KEY is not set")
                    for u, _ in targets]

        sem = asyncio.Semaphore(max(1, FIRECRAWL_MAX_CONCURRENCY))
        pages: dict[str, ExtractedPage] = {}

        async with _http.make_client(FIRECRAWL_TIMEOUT_SECONDS) as client:
            async def one(url: str, title: str) -> None:
                async with sem:
                    pages[url] = await self.extract_one(client, url, title)

            tasks = [asyncio.create_task(one(u, t)) for u, t in targets]
            done, pending = await asyncio.wait(tasks, timeout=EXTRACT_DEADLINE_SECONDS)
            for task in pending:
                task.cancel()
            if pending:
                log.warning("extraction deadline hit — %d/%d pages unread",
                            len(pending), len(tasks))
                await asyncio.gather(*pending, return_exceptions=True)

        out = []
        for url, title in targets:
            out.append(pages.get(url) or ExtractedPage(
                url=url, status=DISCOVERY_ONLY, note="not read before the deadline"))

        read = sum(1 for p in out if p.status == "extracted")
        log.info("✓ firecrawl read %d/%d pages", read, len(out))
        return out
