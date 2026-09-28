"""
Competitor Scout Agent (Agent 3)
Finds the top competitor listings for the product, on whatever platform they sell.

The actual fetching lives in `providers/` so the data source can be swapped
without touching the graph. This node's job is to call it and log provenance —
which matters, because the whole product rests on these competitors being real.
"""
from __future__ import annotations

import logging
import time

from models.schemas import (
    CategoryClassification,
    CompetitorScoutResult,
    ExtractedEntities,
)
from providers import fetch_competitors

log = logging.getLogger("listingiq.agent.competitor_scout")


async def scout_competitors(
    category: CategoryClassification,
    platform: str,
    brand_name: str = "",
    entities: ExtractedEntities | None = None,
) -> CompetitorScoutResult:
    """
    Fetch the top competitor listings via the configured provider.

    `entities` come from the input parser. Web discovery composes them into a
    search query — a bare subcategory is enough for a marketplace search box,
    which already knows it is searching products, and returns encyclopaedia
    entries on the open web.
    """
    return await fetch_competitors(category, platform, brand_name, limit=10,
                                   entities=entities)


# ── LangGraph node wrapper ────────────────────────────────────
async def competitor_scout_node(state: dict) -> dict:
    """LangGraph node: finds the top competitor listings across platforms."""
    log.info("⚙ competitor_scout_node ENTER")
    t0 = time.perf_counter()

    category = state["category"]
    if isinstance(category, dict):
        category = CategoryClassification(**category)

    parsed = state.get("parsed_listing", {})
    if isinstance(parsed, dict):
        platform = parsed.get("platform", "")
        brand_name = parsed.get("brand_name", "")
        raw_entities = parsed.get("extracted_entities")
        entities = (ExtractedEntities(**raw_entities)
                    if isinstance(raw_entities, dict) else raw_entities)
    else:
        platform = parsed.platform
        brand_name = parsed.brand_name
        entities = parsed.extracted_entities

    result = await scout_competitors(category, platform, brand_name, entities)
    log.info(
        "⚙ competitor_scout_node EXIT  %.1fs  %d listings  source=%s%s  query='%s'",
        time.perf_counter() - t0,
        len(result.listings),
        result.data_source,
        " (cached)" if result.from_cache else "",
        result.search_query,
    )
    return {"competitor_scout_result": result}
