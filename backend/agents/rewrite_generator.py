"""
Rewrite Generator Agent (Agent 8)
Generates 2-3 complete listing rewrite variants:
- Keyword-Optimized: maximum search visibility
- Benefit-Led: strongest outcome claims
- Trust-Forward: certifications and social proof first
"""
from __future__ import annotations

import logging
import time
from models.schemas import (
    ParsedListing,
    RecommendationResult,
    CompetitorAnalysis,
    ListingScore,
    ListingRewrite,
    RewriteResult,
)
from models.llm_responses import RewriteResultOut, clamp
from agents.llm_client import structured_completion
from providers import platforms

log = logging.getLogger("listingiq.agent.rewrite_generator")


async def generate_rewrites(
    parsed_listing: ParsedListing,
    recommendations: RecommendationResult,
    competitor_analysis: CompetitorAnalysis,
    scores: ListingScore,
) -> RewriteResult:
    """Generate 3 complete listing rewrite variants."""

    # The rewrite has to be shaped for the platform it will be published on. A
    # 200-character keyword-stacked title is excellent on a marketplace and
    # wrong on a brand's own product page; the reverse is equally true. This was
    # previously hardcoded to Amazon in the prompt.
    profile = platforms.profile(parsed_listing.platform)

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

PLATFORM: {profile.label}
  Titles here run roughly {profile.title_char_target[0]}-{profile.title_char_target[1]} characters.
  {"Bullet points are a first-class field; write " + str(profile.typical_bullets) + " of them." if profile.bullets_expected else "This platform has no bullet field — selling copy is prose. Bullets are supplied for reference only."}
  {profile.note}

Generate exactly 3 variants:

1. KEYWORD-OPTIMIZED: Front-load high-volume search keywords. Maximize search visibility. Structure the title the way this platform's search rewards (brand + key feature + product type + size/count). Every bullet should contain a search term.

2. BENEFIT-LED: Lead with strongest outcome claims and benefits. Focus on what the product DOES for the buyer. Emotional/aspirational language.

3. TRUST-FORWARD: Lead with certifications, testing, and social proof. Build credibility before benefits. Best for categories where trust is the primary purchase barrier (supplements, skincare).

For each variant, provide:
- variant_name: "keyword-optimized", "benefit-led", or "trust-forward"
- strategy: 1-sentence description of the approach
- title: Complete product title, within this platform's length norm
- bullet_points: 5-6 bullet points (each 1-2 lines)
- description: 2-3 paragraph product description
- expected_score: Projected overall score (0-10)
- key_changes: List of 3-5 specific changes from the original

RULES:
- Keep the brand name in all titles
- Bullet points should be scannable — lead with the key point in CAPS or bold-like formatting
- Description should be prose, not bullets
- Be specific and authentic — no generic marketing fluff
- Each variant should feel distinctly different in approach
- variant_name must be exactly one of: keyword-optimized, benefit-led, trust-forward
- expected_score runs from 0.0 to 10.0"""

    out = await structured_completion(
        response_model=RewriteResultOut,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        max_completion_tokens=8000,
        caller="rewrite_generator.generate",
    )

    variants = [
        ListingRewrite(
            variant_name=v.variant_name,
            strategy=v.strategy,
            title=v.title,
            bullet_points=v.bullet_points,
            description=v.description,
            expected_score=clamp(v.expected_score, 0.0, 10.0),
            key_changes=v.key_changes,
        )
        for v in out.variants
    ]

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
