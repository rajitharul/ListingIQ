"""
Competitor Analyzer Agent (Agent 4)
Analyzes patterns across 10 competitor listings: keyword frequency,
claim patterns, trust signals, structural patterns, differentiation.
"""
from __future__ import annotations

import json
import logging
import time
from config import OPENAI_MODEL
from models.schemas import (
    CompetitorListing,
    CompetitorScoutResult,
    ScoringRubric,
    CompetitorAnalysis,
    KeywordPattern,
    ClaimPattern,
)
from agents.llm_client import logged_chat_completion

log = logging.getLogger("listingiq.agent.competitor_analyzer")


async def analyze_competitors(
    scout_result: CompetitorScoutResult,
    rubric: ScoringRubric,
) -> CompetitorAnalysis:
    """Extract competitive intelligence patterns from 10 competitor listings."""

    listings_text = ""
    for i, listing in enumerate(scout_result.listings, 1):
        bullets = "\n    ".join(f"• {b}" for b in listing.bullet_points[:5])
        listings_text += f"""
LISTING {i}: {listing.brand_name} (Rank #{listing.rank}, {listing.rating}★, {listing.review_count} reviews, {listing.price})
  Title: {listing.title}
  Bullets:
    {bullets}
  Description: {listing.description[:200]}{'...' if len(listing.description) > 200 else ''}
  Badges: {', '.join(listing.badges) if listing.badges else 'None'}
"""

    dims_text = ", ".join(d.name for d in rubric.dimensions)

    prompt = f"""You are a competitive intelligence analyst. Analyze these 10 competitor product listings and extract patterns.

{listings_text}

SCORING DIMENSIONS FOR THIS CATEGORY: {dims_text}

Analyze across ALL 10 listings and extract:

1. keyword_patterns: Keywords/phrases that appear in MULTIPLE listings. For each, count how many of the 10 listings use it and where (title, bullets, or description).

2. claim_patterns: Specific claims or statements that appear across listings. For each, count frequency and give an example brand.

3. trust_signals: Certifications, badges, testing claims, and trust markers. For each, count how many listings include it.

4. structural_patterns: Quantitative data about listing structure:
   - avg_title_length (character count)
   - avg_bullet_count
   - avg_description_length (character count)
   - common_title_format (pattern description)
   - emoji_usage (how many of 10 use emojis in bullets)

5. differentiation_insights: 3-5 specific things the top 3 listings do that the bottom 7 don't.

6. summary: A 3-sentence competitive landscape summary.

Return a JSON object:
{{
  "keyword_patterns": [
    {{"keyword": "...", "frequency": 8, "position": "title"}}
  ],
  "claim_patterns": [
    {{"claim": "...", "frequency": 7, "example_brand": "..."}}
  ],
  "trust_signals": [
    {{"signal": "...", "frequency": 6}}
  ],
  "structural_patterns": {{
    "avg_title_length": 120,
    "avg_bullet_count": 5,
    "avg_description_length": 300,
    "common_title_format": "...",
    "emoji_usage": 4
  }},
  "differentiation_insights": ["..."],
  "summary": "..."
}}

Return ONLY valid JSON."""

    response = await logged_chat_completion(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        response_format={"type": "json_object"},
        caller="competitor_analyzer.analyze",
    )
    data = json.loads(response.choices[0].message.content)

    keyword_patterns = [
        KeywordPattern(**kp)
        for kp in data.get("keyword_patterns", [])
    ]
    claim_patterns = [
        ClaimPattern(**cp)
        for cp in data.get("claim_patterns", [])
    ]

    return CompetitorAnalysis(
        keyword_patterns=keyword_patterns,
        claim_patterns=claim_patterns,
        trust_signals=data.get("trust_signals", []),
        structural_patterns=data.get("structural_patterns", {}),
        differentiation_insights=data.get("differentiation_insights", []),
        summary=data.get("summary", ""),
    )


# ── LangGraph node wrapper ────────────────────────────────────
async def competitor_analyzer_node(state: dict) -> dict:
    """LangGraph node: analyzes patterns across competitor listings."""
    log.info("⚙ competitor_analyzer_node ENTER")
    t0 = time.perf_counter()

    scout_result = state["competitor_scout_result"]
    if isinstance(scout_result, dict):
        scout_result = CompetitorScoutResult(**scout_result)

    rubric = state["rubric"]
    if isinstance(rubric, dict):
        rubric = ScoringRubric(**rubric)

    result = await analyze_competitors(scout_result, rubric)
    log.info(
        "⚙ competitor_analyzer_node EXIT  %.1fs  keywords=%d  claims=%d  trust=%d",
        time.perf_counter() - t0,
        len(result.keyword_patterns),
        len(result.claim_patterns),
        len(result.trust_signals),
    )
    return {"competitor_analysis": result}
