"""
Filling the gaps that structured data did not cover.

Most marketplace and Shopify pages publish `schema.org/Product` JSON-LD, so the
deterministic path in `structured.py` handles them for free. The long tail does
not: a hand-built store, a page whose markup covers only price and rating, a
marketplace that puts its selling points in a rendered list and nothing else.

One batched call handles every such page at once, through the same
`structured_completion` seam as the rest of the pipeline — so it is retried, it
is counted against the caller's token budget, and it is visible to the eval
harness. Firecrawl's own extraction endpoint would have been simpler and none of
those things.

The model transcribes; it does not compose. A page with no bullet points must
come back with none, because an invented bullet is scored as a competitor's copy
and quoted to the customer as market evidence.
"""
from __future__ import annotations

import logging

from agents.llm_client import structured_completion
from models.llm_responses import ExtractedPagesOut
from providers.extract.base import MODEL, ExtractedPage
from providers.extract.structured import clean_text

log = logging.getLogger("listingiq.providers.extract_model")

# Enough page text to contain the selling copy, bounded so a batch of ten pages
# stays within a sane prompt.
_BODY_CHARS = 3000


def _needs_model(page: ExtractedPage) -> bool:
    return page.status == "extracted" and bool(page.missing_fields()) and bool(page.body)


async def fill_gaps(pages: list[ExtractedPage], *, caller: str = "extract.fill_gaps") -> list[ExtractedPage]:
    """
    Ask the model only for fields structured data did not supply.

    Pages that are already complete are not sent at all, so a run where every
    competitor publishes proper markup costs nothing here.
    """
    pending = [p for p in pages if _needs_model(p)]
    if not pending:
        log.info("extraction: structured data covered every page — no model call")
        return pages

    blocks = []
    for i, page in enumerate(pending):
        gaps = ", ".join(page.missing_fields())
        blocks.append(
            f"PAGE id={i}\n"
            f"  URL: {page.url}\n"
            f"  Still needed: {gaps}\n"
            f"  Page text:\n{clean_text(page.body)[:_BODY_CHARS]}\n"
        )

    prompt = f"""You are transcribing product listing copy from {len(pending)} ecommerce pages.

For each page, report what the page itself says. Rules:

1. Copy text as written. Do not rewrite, summarise, improve or translate it.
2. If a field is not present on the page, return it empty. An empty field is a
   correct answer. Never infer a plausible value from the product name.
3. Bullet points must be selling points about the product. Ignore navigation,
   shipping and returns policies, cookie notices, and review text.
4. The description is the seller's own product copy, not a review and not
   specifications.
5. Echo back each page's id exactly as given.

{chr(10).join(blocks)}"""

    out = await structured_completion(
        response_model=ExtractedPagesOut,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_completion_tokens=6000,
        caller=caller,
    )

    by_id = {i: p for i, p in enumerate(pending)}
    filled = 0
    for item in out.items:
        page = by_id.get(item.item_id)
        if page is None:
            # An id the model invented cannot become a competitor's copy.
            continue
        gaps = set(page.missing_fields())
        if "title" in gaps and item.title:
            page.title = clean_text(item.title)
        if "brand_name" in gaps and item.brand_name:
            page.brand_name = clean_text(item.brand_name)
        if "bullet_points" in gaps and item.bullet_points:
            page.bullet_points = [clean_text(b) for b in item.bullet_points if b.strip()][:8]
        if "description" in gaps and item.description:
            page.description = clean_text(item.description)
        if page.method != MODEL:
            page.method = f"{page.method}+model" if page.method else MODEL
        filled += 1

    log.info("extraction: model filled gaps on %d/%d pages (%d needed no call)",
             filled, len(pending), len(pages) - len(pending))
    return pages
