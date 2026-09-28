"""
Routing each page to whichever reader does it best.

The system is platform-agnostic, which is not the same as platform-blind. A
generic fetch is the right default and the only thing that works on the long
tail of brand stores — but where a platform has a proper product API, using it
is strictly better, and pretending otherwise costs listing quality on the
storefront that matters most to the most sellers.

The router is deliberately thin: one predicate per specialised extractor,
everything else to the generic one, results reassembled in the order asked for.
Adding a platform later is one entry.
"""
from __future__ import annotations

import asyncio
import logging

from providers.extract.amazon import AmazonExtractor
from providers.extract.base import DISCOVERY_ONLY, ExtractedPage
from providers.extract.firecrawl import FirecrawlExtractor

log = logging.getLogger("listingiq.providers.extract")


class PlatformAwareExtractor:
    """Reads any product page, using a platform's own API where one exists."""

    def __init__(self, generic=None, amazon=None):
        self._generic = generic or FirecrawlExtractor()
        self._amazon = amazon if amazon is not None else AmazonExtractor()

    @property
    def name(self) -> str:
        parts = [self._generic.name]
        if self._amazon is not None and getattr(self._amazon, "available", False):
            parts.append(self._amazon.name)
        return "+".join(parts)

    async def extract_many(self, targets: list[tuple[str, str]]) -> list[ExtractedPage]:
        if not targets:
            return []

        specialised: list[tuple[str, str]] = []
        generic: list[tuple[str, str]] = []
        for url, title in targets:
            if self._amazon is not None and self._amazon.handles(url):
                specialised.append((url, title))
            else:
                generic.append((url, title))

        if specialised:
            log.info("extraction: %d via %s, %d via %s",
                     len(specialised), self._amazon.name, len(generic), self._generic.name)

        results = await asyncio.gather(
            self._amazon.extract_many(specialised) if specialised else _none(),
            self._generic.extract_many(generic) if generic else _none(),
        )

        by_url: dict[str, ExtractedPage] = {}
        for group in results:
            for page in group:
                by_url[page.url] = page

        # A specialised reader that fails must not leave the page unread. An
        # expired key or an exhausted quota on one platform's API would
        # otherwise be worse than never having routed there at all — observed
        # live, when Rainforest credits ran out and every Amazon competitor
        # came back empty while the generic reader sat idle.
        retry = [(url, title) for url, title in specialised
                 if (by_url.get(url) or ExtractedPage(url=url)).status != "extracted"]
        if retry:
            reasons = {by_url[u].note for u, _ in retry if u in by_url and by_url[u].note}
            log.warning("%s could not read %d page(s) (%s) — retrying via %s",
                        self._amazon.name, len(retry),
                        "; ".join(sorted(reasons)) or "no reason given",
                        self._generic.name)
            for page in await self._generic.extract_many(retry):
                if page.status == "extracted" or page.url not in by_url:
                    by_url[page.url] = page

        return [by_url.get(url) or ExtractedPage(url=url, status=DISCOVERY_ONLY,
                                                 note="not read")
                for url, _ in targets]


async def _none() -> list[ExtractedPage]:
    return []
