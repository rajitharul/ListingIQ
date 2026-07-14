"""
Rewrite Generator Agent (Agent 8)
Generates 2-3 complete listing rewrite variants:
- Keyword-Optimized: maximum search visibility
- Benefit-Led: strongest outcome claims
- Trust-Forward: certifications and social proof first
"""
from __future__ import annotations

import json
import logging
import time
from config import OPENAI_MODEL
from models.schemas import (
    ParsedListing,
    RecommendationResult,
    CompetitorAnalysis,
    ListingScore,
    ListingRewrite,
    RewriteResult,
)
from agents.llm_client import logged_chat_completion

log = logging.getLogger("listingiq.agent.rewrite_generator")


async def generate_rewrites(
    parsed_listing: ParsedListing,
    recommendations: RecommendationResult,
    competitor_analysis: CompetitorAnalysis,
    scores: ListingScore,
) -> RewriteResult:
    """Generate 3 complete listing rewrite variants."""

    # Current listing
    bullets_text = "\n".join(f"  - {b}" for b in parsed_listing.original_bullets) if parsed_listing.original_bullets else "  (no bullets)"

    # Key recommendations to incorporate
    recs_text = "\n".join(
        f"  {r.priority}. [{r.dimension}] {r.specific_copy}"
        for r in recommendations.recommendations[:8]
    )

    # Top keywords from competitors
    top_keywords = [kp.keyword for kp in competitor_analysis.keyword_patterns if kp.frequency >= 5][:15]

    # Top claims
    top_claims = [cp.claim for cp in competitor_analysis.claim_patterns if cp.frequency >= 5][:10]

    # Trust signals
    trust_list = [ts.get("signal", "") for ts in competitor_analysis.trust_signals if ts.get("frequency", 0) >= 4][:10]

    prompt = f"""You are an elite ecommerce copywriter who optimizes product listings for conversion. Generate 3 complete rewrite variants of this product listing.

CURRENT LISTING (Score: {scores.overall_score}/10):
  Title: {parsed_listing.original_title}
  Bullets:
{bullets_text}
  Description: {parsed_listing.original_description[:500] or '(no description)'}
  Brand: {parsed_listing.brand_name}

KEY RECOMMENDATIONS TO INCORPORATE:
{recs_text}

COMPETITIVE INTELLIGENCE:
  High-frequency keywords: {', '.join(top_keywords)}
  Common claims: {', '.join(top_claims)}
  Trust signals: {', '.join(trust_list)}
  Structural patterns: avg title ~{competitor_analysis.structural_patterns.get('avg_title_length', 100)} chars, avg {competitor_analysis.structural_patterns.get('avg_bullet_count', 5)} bullets

Generate exactly 3 variants:

1. KEYWORD-OPTIMIZED: Front-load high-volume search keywords. Maximize search visibility. Structure title for Amazon SEO (brand + key feature + product type + size/count). Every bullet should contain a search term.

2. BENEFIT-LED: Lead with strongest outcome claims and benefits. Focus on what the product DOES for the buyer. Emotional/aspirational language. Best for Shopify/DTC contexts.

3. TRUST-FORWARD: Lead with certifications, testing, and social proof. Build credibility before benefits. Best for categories where trust is the primary purchase barrier (supplements, skincare).

For each variant, provide:
- variant_name: "keyword-optimized", "benefit-led", or "trust-forward"
- strategy: 1-sentence description of the approach
- title: Complete product title (match competitive title length)
- bullet_points: 5-6 bullet points (each 1-2 lines)
- description: 2-3 paragraph product description
- expected_score: Projected overall score (0-10)
- key_changes: List of 3-5 specific changes from the original

Return a JSON object:
{{
  "variants": [
    {{
      "variant_name": "keyword-optimized",
      "strategy": "...",
      "title": "...",
      "bullet_points": ["...", "..."],
      "description": "...",
      "expected_score": 7.5,
      "key_changes": ["Added form specificity to title", "..."]
    }}
  ]
}}

RULES:
- Keep the brand name in all titles
- Bullet points should be scannable — lead with the key point in CAPS or bold-like formatting
- Description should be prose, not bullets
- Be specific and authentic — no generic marketing fluff
- Each variant should feel distinctly different in approach

Return ONLY valid JSON."""

    response = await logged_chat_completion(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        response_format={"type": "json_object"},
        caller="rewrite_generator.generate",
    )
    data = json.loads(response.choices[0].message.content)

    variants = [ListingRewrite(**v) for v in data.get("variants", [])]

    best_score = max((v.expected_score for v in variants), default=0.0)

    return RewriteResult(
        variants=variants,
        original_score=scores.overall_score,
        best_variant_score=best_score,
    )


# ── LangGraph node wrapper ────────────────────────────────────
async def rewrite_generator_node(state: dict) -> dict:
    """LangGraph node: generates 3 complete listing rewrite variants."""
    log.info("⚙ rewrite_generator_node ENTER")
    t0 = time.perf_counter()

    parsed = state["parsed_listing"]
    if isinstance(parsed, dict):
        parsed = ParsedListing(**parsed)

    recommendations = state["recommendations"]
    if isinstance(recommendations, dict):
        recommendations = RecommendationResult(**recommendations)

    competitor_analysis = state["competitor_analysis"]
    if isinstance(competitor_analysis, dict):
        competitor_analysis = CompetitorAnalysis(**competitor_analysis)

    scores = state["scores"]
    if isinstance(scores, dict):
        scores = ListingScore(**scores)

    result = await generate_rewrites(parsed, recommendations, competitor_analysis, scores)
    log.info(
        "⚙ rewrite_generator_node EXIT  %.1fs  variants=%d  best_score=%.1f (original=%.1f)",
        time.perf_counter() - t0,
        len(result.variants),
        result.best_variant_score,
        result.original_score,
    )
    return {"rewrites": result}
