"""
ListingIQ — Pydantic v2 Data Models
All schemas for the 8-agent product listing optimization pipeline.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


# ── INPUT MODELS ─────────────────────────────────────────────────

class ListingInput(BaseModel):
    """User-submitted product listing to analyze."""
    product_title: str = Field(..., description="Product title, e.g. 'Magnesium Glycinate 200mg, 60 Capsules'")
    product_description: str = Field("", description="Full product description text")
    bullet_points: list[str] = Field(default_factory=list, description="Bullet point list (Amazon-style)")
    brand_name: str = Field("", description="Brand name, e.g. 'Nature Made'")
    platform: str = Field("amazon", description="Platform: amazon | shopify | daraz | generic")
    target_audience: str = Field("", description="Optional target audience context")


# ── PARSED INPUT (Agent 1: Input Parser output) ─────────────────

class ExtractedEntities(BaseModel):
    """Entities extracted from a product listing by the Input Parser."""
    product_type: str = Field("", description="Normalized product type, e.g. 'Magnesium Glycinate Supplement'")
    ingredients: list[str] = Field(default_factory=list, description="Ingredients mentioned")
    certifications: list[str] = Field(default_factory=list, description="Certifications mentioned (USP, NSF, GMP, etc.)")
    dosage_info: str = Field("", description="Dosage/serving information")
    target_audience: str = Field("", description="Target audience if mentioned")
    claims: list[str] = Field(default_factory=list, description="Health/benefit claims made")
    format_type: str = Field("", description="Product format: capsules, powder, serum, cream, etc.")


class ParsedListing(BaseModel):
    """Normalized and entity-extracted product listing."""
    original_title: str
    original_description: str
    original_bullets: list[str] = Field(default_factory=list)
    brand_name: str
    platform: str
    extracted_entities: ExtractedEntities


# ── CATEGORY MODELS (Agent 2: Category Classifier output) ───────

class CategoryClassification(BaseModel):
    """Product category classification result."""
    vertical: str = Field(..., description="Top-level vertical, e.g. 'Supplements & Nutraceuticals'")
    category: str = Field(..., description="Category, e.g. 'Minerals'")
    subcategory: str = Field(..., description="Subcategory, e.g. 'Magnesium Glycinate'")
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="Classification confidence")
    reasoning: str = Field("", description="Why this classification was chosen")


class RubricDimension(BaseModel):
    """A single scoring dimension in a rubric."""
    name: str = Field(..., description="Dimension name, e.g. 'Form Specificity'")
    weight: float = Field(0.1, ge=0.0, le=1.0, description="Relative weight (all weights sum to ~1.0)")
    description: str = Field("", description="What this dimension measures")
    scoring_criteria: str = Field("", description="How to score 0-10 on this dimension")


class ScoringRubric(BaseModel):
    """Complete scoring rubric for a product subcategory."""
    subcategory: str
    dimensions: list[RubricDimension]
    version: str = "1.0"


# ── COMPETITOR MODELS (Agent 3: Competitor Scout output) ─────────

class CompetitorListing(BaseModel):
    """A single competitor product listing."""
    rank: int = Field(0, description="Rank 1-10 by sales/relevance")
    title: str = Field(..., description="Product title")
    description: str = Field("", description="Product description")
    bullet_points: list[str] = Field(default_factory=list, description="Bullet points")
    brand_name: str = Field("", description="Brand name")
    price: str = Field("", description="Price as string, e.g. '$24.99'")
    rating: float = Field(0.0, ge=0.0, le=5.0, description="Star rating")
    review_count: int = Field(0, description="Number of reviews")
    badges: list[str] = Field(default_factory=list, description="Badges: Amazon's Choice, Best Seller, etc.")
    url: str = Field("", description="Listing URL (empty for LLM-sourced data)")


class CompetitorScoutResult(BaseModel):
    """Result from the Competitor Scout agent."""
    listings: list[CompetitorListing]
    search_query: str = Field("", description="Search query used to find competitors")
    platform: str = Field("amazon", description="Platform searched")
    data_source: str = Field("llm_knowledge", description="llm_knowledge | rainforest_api | scraping")


# ── COMPETITOR ANALYSIS MODELS (Agent 4: Competitor Analyzer) ────

class KeywordPattern(BaseModel):
    """A keyword pattern found across competitor listings."""
    keyword: str
    frequency: int = Field(0, description="How many of 10 listings use this keyword")
    position: str = Field("title", description="Where it appears: title | bullets | description")


class ClaimPattern(BaseModel):
    """A claim pattern found across competitor listings."""
    claim: str
    frequency: int = Field(0, description="How many of 10 listings make this claim")
    example_brand: str = Field("", description="Example brand using this claim")


class CompetitorAnalysis(BaseModel):
    """Competitive intelligence extracted from 10 competitor listings."""
    keyword_patterns: list[KeywordPattern] = Field(default_factory=list)
    claim_patterns: list[ClaimPattern] = Field(default_factory=list)
    trust_signals: list[dict] = Field(default_factory=list, description="Trust signals with frequency")
    structural_patterns: dict = Field(default_factory=dict, description="Avg title length, bullet count, etc.")
    differentiation_insights: list[str] = Field(default_factory=list, description="What top 3 have that bottom 7 don't")
    summary: str = Field("", description="Overall competitive intelligence summary")


# ── LISTING ANALYSIS MODELS (Agent 5: Listing Analyzer) ─────────

class DimensionExtraction(BaseModel):
    """What the user's listing says (or doesn't say) for one rubric dimension."""
    dimension_name: str
    present: bool = Field(False, description="Whether this dimension is addressed in the listing")
    extracted_value: str = Field("", description="What the listing says for this dimension")
    evidence: str = Field("", description="Direct quote from the listing")
    completeness: float = Field(0.0, ge=0.0, le=1.0, description="How completely this dimension is covered")


class ListingAnalysis(BaseModel):
    """Per-dimension extraction from the user's listing."""
    dimensions: list[DimensionExtraction] = Field(default_factory=list)
    overall_completeness: float = Field(0.0, description="Average completeness across all dimensions")
    missing_dimensions: list[str] = Field(default_factory=list, description="Dimensions not addressed")
    present_dimensions: list[str] = Field(default_factory=list, description="Dimensions addressed")


# ── SCORING MODELS (Agent 6: Benchmark Scorer) ──────────────────

class DimensionScore(BaseModel):
    """Score for a single dimension."""
    dimension: str
    weight: float = Field(0.0, description="Dimension weight from rubric")
    score: float = Field(0.0, ge=0.0, le=10.0, description="User's score 0-10")
    explanation: str = Field("", description="Why this score was given")
    competitor_avg: float = Field(0.0, description="Average score across 10 competitors")
    gap: float = Field(0.0, description="competitor_avg - user_score (positive = behind)")
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)


class ListingScore(BaseModel):
    """Complete scoring result for the user's listing."""
    overall_score: float = Field(0.0, description="Weighted average score")
    dimension_scores: list[DimensionScore] = Field(default_factory=list)
    percentile: int = Field(0, description="Where user ranks vs 10 competitors (0-100)")
    gap_analysis: list[dict] = Field(default_factory=list, description="Gaps sorted by impact (gap * weight)")


# ── RECOMMENDATION MODELS (Agent 7: Recommendation Engine) ──────

class Recommendation(BaseModel):
    """A single actionable recommendation."""
    priority: int = Field(0, description="1 = highest priority")
    dimension: str = Field("", description="Target dimension")
    current_score: float = Field(0.0)
    projected_score: float = Field(0.0)
    impact: str = Field("medium", description="high | medium | low")
    specific_copy: str = Field("", description="Exact text to add or change")
    competitive_evidence: str = Field("", description="E.g. '8/10 top competitors include this'")
    expected_lift: str = Field("", description="E.g. '+1.5 points on Form Specificity'")


class RecommendationResult(BaseModel):
    """All recommendations from the engine."""
    recommendations: list[Recommendation] = Field(default_factory=list)
    quick_wins: list[Recommendation] = Field(default_factory=list, description="Top 3 easiest improvements")
    strategic_moves: list[Recommendation] = Field(default_factory=list, description="Higher effort, higher impact")


# ── REWRITE MODELS (Agent 8: Rewrite Generator) ─────────────────

class ListingRewrite(BaseModel):
    """A complete rewritten listing variant."""
    variant_name: str = Field("", description="keyword-optimized | benefit-led | trust-forward")
    strategy: str = Field("", description="Description of the strategic approach")
    title: str = Field("")
    bullet_points: list[str] = Field(default_factory=list)
    description: str = Field("")
    expected_score: float = Field(0.0, description="Projected overall score for this variant")
    key_changes: list[str] = Field(default_factory=list, description="What was changed and why")


class RewriteResult(BaseModel):
    """All rewrite variants."""
    variants: list[ListingRewrite] = Field(default_factory=list)
    original_score: float = Field(0.0)
    best_variant_score: float = Field(0.0)


# ── AGENT TRACE MODELS ──────────────────────────────────────────

class AgentNodeTrace(BaseModel):
    """Execution trace for a single agent node."""
    name: str
    role: str = Field("core", description="core | meta")
    status: str = Field("skipped", description="completed | skipped")
    duration_ms: float = 0.0
    parent: str = Field("", description="Node this follows from")


class AgentTrace(BaseModel):
    """Full execution trace for the pipeline run."""
    total_duration_ms: float = 0.0
    nodes_executed: int = 0
    nodes_skipped: int = 0
    nodes: list[AgentNodeTrace] = Field(default_factory=list)


# ── FEEDBACK & MEMORY MODELS ────────────────────────────────────

class FeedbackEntry(BaseModel):
    """Human feedback submission."""
    session_id: str
    brand_name: str
    feedback_type: str  # "accepted" | "rejected" | "guideline"
    original_content: str
    suggested_content: str = ""
    user_comment: str = ""
    dimension: str = ""


class MemoryEntry(BaseModel):
    """A stored guideline or learned preference."""
    brand_name: str
    guideline: str
    source: str  # "brand_guideline" | "human_feedback" | "learned_preference"
    confidence: float = 1.0


# ── PIPELINE REQUEST/RESPONSE ───────────────────────────────────

class FullPipelineRequest(BaseModel):
    """Request to run the full ListingIQ pipeline."""
    listing_input: ListingInput
    session_id: str = "default"


class FullPipelineResponse(BaseModel):
    """Complete response from the ListingIQ pipeline."""
    parsed_listing: ParsedListing
    category: CategoryClassification
    rubric: ScoringRubric
    competitors: CompetitorScoutResult
    competitor_analysis: CompetitorAnalysis
    listing_analysis: ListingAnalysis
    scores: ListingScore
    recommendations: RecommendationResult
    rewrites: RewriteResult
    agent_trace: AgentTrace | None = None
