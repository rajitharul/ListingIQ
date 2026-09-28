"""
ListingIQ — LLM Response Schemas

These models describe exactly what each agent asks the LLM to return. They are
deliberately separate from the domain models in `schemas.py`:

  * Domain models carry computed fields (overall_score, gap_analysis, percentile
    derivation) that the LLM must never supply.
  * These models are constrained to the subset of JSON Schema that OpenAI's
    strict structured outputs supports — no numeric bounds, no bare dicts, no
    optional fields. Range clamping happens in Python after parsing, so an
    out-of-range score is corrected rather than failing the whole pipeline.

Each agent maps its *_Out model into the corresponding domain model.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


def clamp(value: float, low: float, high: float) -> float:
    """
    Correct an LLM-supplied number into its valid range.

    Strict structured outputs cannot express numeric bounds in the schema, so
    ranges are enforced here. Clamping rather than rejecting is deliberate: a
    score of 10.4 should become 10.0, not fail a 60-second pipeline run.
    """
    return max(low, min(high, value))


# ── Agent 1: Input Parser ────────────────────────────────────────

class ExtractedEntitiesOut(BaseModel):
    product_type: str = Field(description="Normalized product type, e.g. 'Magnesium Glycinate Supplement'")
    ingredients: list[str] = Field(description="Every ingredient, active compound, or key component mentioned")
    certifications: list[str] = Field(description="Certifications mentioned (USP, NSF, GMP, organic, vegan, cruelty-free)")
    dosage_info: str = Field(description="Dosage, serving size, concentration, or quantity information")
    target_audience: str = Field(description="Target audience if mentioned or implied; empty string if absent")
    claims: list[str] = Field(description="Health, benefit, or performance claims made")
    format_type: str = Field(description="Product format: capsules, powder, serum, cream, tablets, softgels, gummies")


# ── Agent 2: Category Classifier ─────────────────────────────────

class CategoryClassificationOut(BaseModel):
    vertical: str = Field(description="Top-level market vertical, e.g. 'Supplements & Nutraceuticals'")
    category: str = Field(description="Mid-level category, e.g. 'Minerals'")
    subcategory: str = Field(description="Specific product subcategory, e.g. 'Magnesium Glycinate'")
    confidence: float = Field(description="Classification confidence from 0.0 to 1.0")
    reasoning: str = Field(description="Brief explanation of why this classification was chosen")


class RubricDimensionOut(BaseModel):
    name: str = Field(description="Short, clear dimension name")
    weight: float = Field(description="Relative importance; all weights sum to approximately 1.0")
    description: str = Field(description="What this dimension measures and why it matters")
    scoring_criteria: str = Field(description="How to score 0-10, with specific examples at 0, 5, and 10")


class GeneratedRubricOut(BaseModel):
    dimensions: list[RubricDimensionOut] = Field(description="8-10 scoring dimensions tailored to this subcategory")


# ── Agent 3: Competitor Scout ────────────────────────────────────

class CompetitorListingOut(BaseModel):
    rank: int = Field(description="Rank in the result set, where 1 is the strongest")
    title: str = Field(description="Complete product title with brand, product, size, count")
    description: str = Field(description="Realistic 2-3 sentence product description")
    bullet_points: list[str] = Field(description="4-5 realistic bullet points as they appear on the listing")
    brand_name: str = Field(description="The real brand name")
    price: str = Field(description="Realistic price formatted as a string, e.g. '$24.99'")
    rating: float = Field(description="Star rating from 0.0 to 5.0, e.g. 4.6")
    review_count: int = Field(description="Realistic review count")
    badges: list[str] = Field(description="Badges such as 'Amazon's Choice', 'Best Seller'; empty list if none")


class CompetitorScoutOut(BaseModel):
    listings: list[CompetitorListingOut] = Field(description="The top competitor listings found")
    search_query: str = Field(description="The search query that would surface these products")


# ── Agent 4: Competitor Analyzer ─────────────────────────────────

# The model proposes and attributes; Python counts. Frequencies and structural
# statistics are arithmetic over text we already hold, so asking for them here
# would be asking for a fabricated statistic.

class KeywordPatternOut(BaseModel):
    keyword: str = Field(
        description="An exact keyword or phrase, written as it literally appears in the "
                    "listings so it can be counted verbatim. No paraphrasing.")


class ClaimPatternOut(BaseModel):
    claim: str = Field(description="A claim or statement appearing across listings")
    competitor_ranks: list[int] = Field(
        description="The rank numbers of every competitor that makes this claim")


class TrustSignalOut(BaseModel):
    signal: str = Field(description="Certification, badge, testing claim, or trust marker")
    competitor_ranks: list[int] = Field(
        description="The rank numbers of every competitor showing this signal")


class CompetitorAnalysisOut(BaseModel):
    keyword_patterns: list[KeywordPatternOut] = Field(
        description="Candidate keywords worth counting across the listings")
    claim_patterns: list[ClaimPatternOut]
    trust_signals: list[TrustSignalOut]
    common_title_format: str = Field(description="Description of the dominant title pattern")
    differentiation_insights: list[str] = Field(description="3-5 things the top 3 listings do that the bottom 7 don't")
    summary: str = Field(description="Three-sentence competitive landscape summary")


# ── Agent 5: Listing Analyzer ────────────────────────────────────

class DimensionExtractionOut(BaseModel):
    dimension_name: str = Field(description="The rubric dimension being analyzed")
    present: bool = Field(description="Whether this dimension is addressed at all in the listing")
    extracted_value: str = Field(description="What the listing provides for this dimension")
    evidence: str = Field(description="Direct quote from the listing; empty string if not present")
    completeness: float = Field(description="How completely the dimension is covered, from 0.0 to 1.0")


class ListingAnalysisOut(BaseModel):
    dimensions: list[DimensionExtractionOut] = Field(description="One entry per rubric dimension")


# ── Batch scorer (competitors and generated rewrites alike) ──────
# One shape for both, because they must be graded identically for the
# comparison between them to mean anything.

class BatchDimensionScoreOut(BaseModel):
    dimension: str = Field(description="The rubric dimension name, copied exactly")
    score: float = Field(description="This listing's score on the dimension, 0.0 to 10.0")


class BatchScoreRowOut(BaseModel):
    item_id: int = Field(description="The listing id, copied from the input")
    dimension_scores: list[BatchDimensionScoreOut] = Field(
        description="One entry per rubric dimension, in the order given")


class ListingBatchScoresOut(BaseModel):
    items: list[BatchScoreRowOut] = Field(
        description="One entry per listing supplied, in the same order")


# ── Agent 6: Benchmark Scorer ────────────────────────────────────

class DimensionScoreOut(BaseModel):
    dimension: str = Field(description="The rubric dimension name")
    weight: float = Field(description="The dimension's weight, copied from the rubric")
    score: float = Field(description="The listing's score on this dimension, 0.0 to 10.0, one decimal place")
    explanation: str = Field(description="Why this score was given")
    strengths: list[str] = Field(description="What the listing does well on this dimension")
    weaknesses: list[str] = Field(description="What the listing is missing on this dimension")


class BenchmarkScoreOut(BaseModel):
    """
    The model scores only the user's listing. competitor_avg, gap and percentile
    are measured from the competitors' own scores, not asked for here.
    """
    dimension_scores: list[DimensionScoreOut] = Field(description="One score per rubric dimension")


# ── Agent 7: Recommendation Engine ───────────────────────────────

class RecommendationOut(BaseModel):
    priority: int = Field(description="1 is the highest priority")
    dimension: str = Field(description="The rubric dimension this targets")
    current_score: float = Field(description="The dimension's current score")
    projected_score: float = Field(description="The dimension's score after applying this change")
    impact: str = Field(description="One of: high, medium, low")
    specific_copy: str = Field(description="The exact text to add or change, ready to paste")
    # The model names WHICH competitor pattern justifies this; Python supplies
    # the count. Asking for the sentence produced things like "8/10 top
    # competitors highlight bioavailability" against a set of three, which is a
    # fabricated statistic printed to a customer as evidence.
    evidence_pattern: str = Field(
        description="The exact competitor keyword, claim or trust signal from the "
                    "competitive context above that justifies this. Copy it verbatim "
                    "so it can be matched; empty string if none applies")
    expected_lift: str = Field(description="Expected effect, e.g. '+1.5 points on Form Specificity'")


class RecommendationResultOut(BaseModel):
    recommendations: list[RecommendationOut] = Field(description="All recommendations, highest priority first")
    quick_wins: list[RecommendationOut] = Field(description="The easiest high-value improvements")
    strategic_moves: list[RecommendationOut] = Field(description="Higher effort, higher impact changes")


# ── Agent 8: Rewrite Generator ───────────────────────────────────

class ListingRewriteOut(BaseModel):
    variant_name: str = Field(description="One of: keyword-optimized, benefit-led, trust-forward")
    strategy: str = Field(description="The strategic approach this variant takes")
    title: str = Field(description="The rewritten product title, retaining the brand name")
    bullet_points: list[str] = Field(description="5-6 scannable bullet points")
    description: str = Field(description="A 2-3 paragraph description written as prose, not bullets")
    expected_score: float = Field(description="Projected overall score for this variant, 0.0 to 10.0")
    key_changes: list[str] = Field(description="What changed versus the original, and why")


class RewriteResultOut(BaseModel):
    variants: list[ListingRewriteOut] = Field(description="Exactly three variants, one per strategy")


# ── Page extraction: filling gaps JSON-LD did not cover ──────────

class ExtractedPageOut(BaseModel):
    """
    One competitor page, read out of its own text.

    Every field is transcription, not authorship. The prompt is explicit that an
    absent field must come back empty rather than invented: a fabricated bullet
    point would be scored as though a competitor had written it, and would then
    appear in the customer's report as evidence of what the market does.
    """
    item_id: int = Field(description="Echo back the id of the page this describes")
    title: str = Field(description="The product name as the page states it; empty if unclear")
    brand_name: str = Field(description="The selling brand; empty if not stated")
    bullet_points: list[str] = Field(
        description="Selling points copied from the page, verbatim. Empty list if the page has none")
    description: str = Field(
        description="The product description as written on the page; empty if there is none")


class ExtractedPagesOut(BaseModel):
    """Every page in one batch, so the whole set costs a single call."""
    items: list[ExtractedPageOut] = Field(description="One entry per page given, in any order")
