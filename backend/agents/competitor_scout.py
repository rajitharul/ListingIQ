"""
Competitor Scout Agent (Agent 3)
Finds the top 10 competitor listings in the product's subcategory.
V1 uses LLM knowledge as data source. Designed for easy swap to real API calls.
"""
from __future__ import annotations

import json
import logging
import time
from config import OPENAI_MODEL
from models.schemas import (
    CategoryClassification,
    CompetitorListing,
    CompetitorScoutResult,
    ParsedListing,
)
from agents.llm_client import logged_chat_completion

log = logging.getLogger("listingiq.agent.competitor_scout")


async def scout_competitors(
    category: CategoryClassification,
    platform: str,
    brand_name: str = "",
) -> CompetitorScoutResult:
    """Find top 10 competitor listings using LLM knowledge."""

    prompt = f"""You are a competitive intelligence agent with deep knowledge of ecommerce product listings across major platforms.

TASK: Recall the top 10 real product listings in this subcategory on {platform.upper()}, ranked by sales volume / best seller rank.

SUBCATEGORY: {category.subcategory}
VERTICAL: {category.vertical}
CATEGORY: {category.category}
PLATFORM: {platform}
{f"EXCLUDE THIS BRAND: {brand_name} (this is the user's brand — do not include it as a competitor)" if brand_name else ""}

For each of the 10 listings, provide:
- rank: 1-10 (1 = best seller)
- title: The REAL product title as it appears on {platform} (complete title with brand, product, size, count)
- description: A realistic 2-3 sentence product description
- bullet_points: 4-5 realistic bullet points as they would appear on the listing
- brand_name: The real brand name
- price: Realistic price (e.g., "$24.99")
- rating: Star rating (e.g., 4.6)
- review_count: Realistic review count
- badges: Any badges (e.g., "Amazon's Choice", "Best Seller", "Climate Pledge Friendly")

IMPORTANT:
- Use REAL brands with realistic data from your knowledge
- Titles should be realistic {platform} product titles (complete, keyword-rich)
- Bullet points should reflect what real top-selling listings actually say
- Prices, ratings, and review counts should be realistic for the category
- Include a mix of large brands and successful smaller/DTC brands

Return a JSON object:
{{
  "listings": [
    {{
      "rank": 1,
      "title": "...",
      "description": "...",
      "bullet_points": ["...", "..."],
      "brand_name": "...",
      "price": "$XX.XX",
      "rating": 4.6,
      "review_count": 12500,
      "badges": ["Best Seller"]
    }}
  ],
  "search_query": "the search query that would find these products"
}}

Return ONLY valid JSON."""

    response = await logged_chat_completion(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        response_format={"type": "json_object"},
        caller="competitor_scout.scout",
    )
    data = json.loads(response.choices[0].message.content)

    listings = []
    for item in data.get("listings", [])[:10]:
        listings.append(CompetitorListing(
            rank=item.get("rank", 0),
            title=item.get("title", ""),
            description=item.get("description", ""),
            bullet_points=item.get("bullet_points", []),
            brand_name=item.get("brand_name", ""),
            price=item.get("price", ""),
            rating=item.get("rating", 0.0),
            review_count=item.get("review_count", 0),
            badges=item.get("badges", []),
        ))

    return CompetitorScoutResult(
        listings=listings,
        search_query=data.get("search_query", category.subcategory),
        platform=platform,
        data_source="llm_knowledge",
    )


# ── LangGraph node wrapper ────────────────────────────────────
async def competitor_scout_node(state: dict) -> dict:
    """LangGraph node: finds top 10 competitor listings."""
    log.info("⚙ competitor_scout_node ENTER")
    t0 = time.perf_counter()

    category = state["category"]
    if isinstance(category, dict):
        category = CategoryClassification(**category)

    parsed = state.get("parsed_listing", {})
    if isinstance(parsed, dict):
        platform = parsed.get("platform", "amazon")
        brand_name = parsed.get("brand_name", "")
    else:
        platform = parsed.platform
        brand_name = parsed.brand_name

    result = await scout_competitors(category, platform, brand_name)
    log.info(
        "⚙ competitor_scout_node EXIT  %.1fs  %d listings found  query='%s'",
        time.perf_counter() - t0,
        len(result.listings),
        result.search_query,
    )
    return {"competitor_scout_result": result}
