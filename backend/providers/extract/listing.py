"""
Reading the user's own listing from its URL.

The same extraction path used on competitors, pointed at the customer's own
product page. Two reasons it is worth having beyond convenience: it removes the
copy-paste step that is the most tedious part of using the product, and it makes
the platform an observed fact rather than a dropdown the user might get wrong —
which matters now that the platform decides which cohort they are benchmarked
against.

It deliberately does **not** run inside the pipeline. A failed fetch here costs
a red border on a form and a retry; inside the graph it would cost a failed
60-second run. More importantly, the user gets to see and correct what we read
before it becomes the basis of every score in the report.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from models.schemas import ListingInput, OwnListingSource
from providers import platforms
from providers.extract.firecrawl import FirecrawlExtractor
from providers.extract.model import fill_gaps

log = logging.getLogger("listingiq.providers.own_listing")


async def extract_listing(
    url: str, *, extractor=None, existing: ListingInput | None = None
) -> tuple[ListingInput, OwnListingSource]:
    """
    Read a product page into a `ListingInput`.

    Anything the user already typed wins. Someone who pasted a corrected title
    must not have it silently overwritten by whatever the live page says.
    """
    base = existing or ListingInput(product_title="")
    detected = platforms.detect(url)
    source = OwnListingSource(url=url, platform_detected=detected,
                              fetched_at=datetime.now(timezone.utc).isoformat())

    extractor = extractor or FirecrawlExtractor()
    pages = await extractor.extract_many([(url, base.product_title)])
    page = pages[0]

    if page.status != "extracted":
        source.status = "failed"
        source.note = page.note or "the page could not be read"
        log.warning("own listing extraction failed for %s: %s", url, source.note)
        return base, source

    await fill_gaps([page], caller="own_listing.extract")

    filled: list[str] = []

    def take(field: str, value):
        """Fill a field only if the user left it empty."""
        if not value:
            return getattr(base, field)
        current = getattr(base, field)
        if current:
            return current
        filled.append(field)
        return value

    result = base.model_copy(update={
        "product_title": take("product_title", page.title),
        "product_description": take("product_description", page.description),
        "bullet_points": take("bullet_points", page.bullet_points),
        "brand_name": take("brand_name", page.brand_name),
        "listing_url": url,
        # An explicit choice always beats detection.
        "platform": base.platform if base.platform not in ("", "auto") else detected,
    })

    source.status = "extracted"
    source.fields_filled = filled
    if not filled:
        source.note = "the page was read, but every field was already filled in"
    log.info("own listing read from %s (%s): filled %s",
             url, detected, ", ".join(filled) or "nothing")
    return result, source
