"""
LLM competitor provider — estimated data, never observed.

This asks the model to recall plausible listings. It is useful for development,
for subcategories a marketplace API cannot reach, and as a labelled fallback
when the live provider is down. It is **not** market data: brands, prices,
ratings and review counts are generated, and `data_source` stays
`llm_knowledge` so the UI says so.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from agents.llm_client import structured_completion
from models.llm_responses import CompetitorScoutOut, clamp
from models.schemas import (
    CategoryClassification,
    CompetitorListing,
    CompetitorScoutResult,
)

log = logging.getLogger("listingiq.providers.llm")


class LLMProvider:
    name = "llm_knowledge"

    async def fetch(
        self,
        category: CategoryClassification,
        platform: str,
        brand_name: str = "",
        limit: int = 10,
    ) -> CompetitorScoutResult:
        prompt = f"""You are a competitive intelligence agent with deep knowledge of ecommerce product listings across major platforms.

TASK: Recall the top {limit} real product listings in this subcategory on {platform.upper()}, ranked by sales volume / best seller rank.

SUBCATEGORY: {category.subcategory}
VERTICAL: {category.vertical}
CATEGORY: {category.category}
PLATFORM: {platform}
{f"EXCLUDE THIS BRAND: {brand_name} (this is the user's brand — do not include it as a competitor)" if brand_name else ""}

For each listing, provide the real brand and a realistic complete title, description,
4-5 bullet points, price, rating, review count and any badges.

IMPORTANT:
- Use REAL brands with realistic data from your knowledge
- Titles should be realistic {platform} product titles (complete, keyword-rich)
- Bullet points should reflect what real top-selling listings actually say
- Include a mix of large brands and successful smaller/DTC brands

Return exactly {limit} listings."""

        out = await structured_completion(
            response_model=CompetitorScoutOut,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_completion_tokens=8000,
            caller="competitor_scout.llm",
        )

        listings = [
            CompetitorListing(
                rank=item.rank,
                title=item.title,
                description=item.description,
                bullet_points=item.bullet_points,
                brand_name=item.brand_name,
                price=item.price,
                rating=clamp(item.rating, 0.0, 5.0),
                review_count=max(0, item.review_count),
                badges=item.badges,
            )
            for item in out.listings[:limit]
        ]

        return CompetitorScoutResult(
            listings=listings,
            search_query=out.search_query or category.subcategory,
            platform=platform,
            data_source=self.name,
            fetched_at=datetime.now(timezone.utc).isoformat(),
            from_cache=False,
            provider_note="AI-estimated from model knowledge, not observed marketplace data",
        )
