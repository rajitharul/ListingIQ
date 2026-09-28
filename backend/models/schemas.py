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
    bullet_points: list[str] = Field(default_factory=list, description="Bullet points, where the platform has them")
    brand_name: str = Field("", description="Brand name, e.g. 'Nature Made'")
    platform: str = Field(
        "auto", description="auto | amazon | walmart | ebay | etsy | shopify | dtc | generic")
    target_audience: str = Field("", description="Optional target audience context")
    listing_url: str = Field(
        "", description="Optional: the listing's own URL, used to prefill the fields above")


class OwnListingSource(BaseModel):
    """
    Where the user's own listing came from, when it was read from a URL.

    Recorded and shown rather than applied silently: a customer should be able
    to see what we read off their page, and correct it, before it becomes the
    basis of every score in the report.
    """
    url: str = ""
    platform_detected: str = ""
    status: str = Field("none", description="extracted | failed | none")
    note: str = ""
    fetched_at: str = ""
    fields_filled: list[str] = Field(
        default_factory=list, description="Which fields were taken from the page")


class ExtractListingRequest(BaseModel):
    """Read a product page into a listing."""
    url: str = Field(..., description="The product page to read")
    listing: ListingInput | None = Field(
        None, description="Anything already filled in; those fields are preserved")


class ExtractListingResponse(BaseModel):
    listing: ListingInput
    source: OwnListingSource


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

# Data sources that represent something actually observed on the open web or a
# marketplace. Anything not named here is treated as an estimate.
LIVE_DATA_SOURCES: frozenset[str] = frozenset({
    "rainforest_api",
    "web_search",
})

class CompetitorListing(BaseModel):
    """A single competitor product listing."""
    rank: int = Field(0, description="Rank in the competitive set, 1 is strongest")
    title: str = Field(..., description="Product title")
    description: str = Field("", description="Product description")
    bullet_points: list[str] = Field(default_factory=list, description="Bullet points")
    brand_name: str = Field("", description="Brand name")
    price: str = Field("", description="Price as string, e.g. '$24.99'")
    rating: float = Field(0.0, ge=0.0, le=5.0, description="Star rating")
    review_count: int = Field(0, description="Number of reviews")
    badges: list[str] = Field(default_factory=list, description="Marketplace badges, e.g. Best Seller")
    url: str = Field("", description="Listing URL (empty for LLM-sourced data)")

    # Per-listing provenance. A competitor set can now span several platforms,
    # so "where did this one come from" has to travel with the listing rather
    # than being implied by the parent result.
    platform: str = Field("", description="Platform slug detected from the URL")
    merchant: str = Field("", description="Storefront or seller, as reported by discovery")
    domain: str = Field("", description="Registrable domain, for grouping and display")
    source_position: int = Field(0, description="Position within the discovery result it came from")
    extraction_status: str = Field(
        "none", description="extracted | discovery_only | failed | none")
    extraction_note: str = Field("", description="Why extraction was partial or failed")
    counts_toward_benchmark: bool = Field(
        True, description="Has enough real copy to be scored fairly")


class CompetitorScoutResult(BaseModel):
    """
    Result from the Competitor Scout agent.

    Provenance is part of the contract, not a debugging aid: the UI uses it to
    tell buyers whether they are looking at observed marketplace data or a
    model's estimate. Never set `data_source` to a live provider for data that
    was not actually fetched from it.
    """
    listings: list[CompetitorListing]
    search_query: str = Field("", description="Primary search query used to find competitors")
    platform: str = Field("", description="The user's own platform — the primary cohort")
    data_source: str = Field("llm_knowledge", description="llm_knowledge | rainforest_api | web_search")
    fetched_at: str = Field("", description="ISO timestamp of the fetch, empty if unknown")
    from_cache: bool = Field(False, description="Served from the competitor cache")
    provider_note: str = Field("", description="Why this source was used, e.g. a fallback reason")

    # A mixed result set needs to say what the mix was.
    platform_breakdown: dict = Field(
        default_factory=dict, description="platform slug -> count; sums to len(listings)")
    queries: list[str] = Field(default_factory=list, description="Every query actually issued")
    discovery_source: str = Field("", description="Which discovery channels were used")
    extraction_source: str = Field("", description="Which extractor read the pages")
    extracted_count: int = Field(0, description="Listings whose page was read in full")
    discovery_only_count: int = Field(0, description="Listings with search metadata only")
    failed_count: int = Field(0, description="Listings whose extraction produced nothing usable")

    @property
    def is_live_data(self) -> bool:
        """
        True only for data actually observed.

        An explicit allowlist, deliberately. This used to be a denylist
        (`not in ("", "llm_knowledge")`), which meant any new provider was
        labelled *live* by default and inherited the green "observed data"
        treatment in the UI without anyone choosing that. Failing closed means
        a provider that forgets to register here is called estimated — visible,
        conservative, and caught by a test.
        """
        return self.data_source in LIVE_DATA_SOURCES


# ── COMPETITOR ANALYSIS MODELS (Agent 4: Competitor Analyzer) ────

class KeywordPattern(BaseModel):
    """
    A keyword found across competitor listings.

    `frequency` is counted in Python by matching the phrase on word boundaries,
    not estimated — it appears in customer-facing evidence and has to be true.
    """
    keyword: str
    frequency: int = Field(0, description="Listings containing this keyword (counted)")
    position: str = Field("title", description="Where it appears: title | bullets | description")


class ClaimPattern(BaseModel):
    """A claim found across competitor listings, with the brands that make it."""
    claim: str
    frequency: int = Field(0, description="Listings making this claim (counted from attribution)")
    example_brand: str = Field("", description="Example brand using this claim")
    brands: list[str] = Field(default_factory=list, description="Every brand making the claim")


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


# ── COMPETITOR BENCHMARK (Agent: Competitor Scorer) ─────────────

class CompetitorDimensionStat(BaseModel):
    """
    Measured distribution of competitor scores on one rubric dimension.

    These are computed in Python from the competitors' own scores — not
    estimated. `mean` is what the user's listing is benchmarked against, so it
    has to be a real average of real listings or the whole comparison is
    theatre.
    """
    dimension: str
    mean: float = Field(0.0, description="Arithmetic mean of the competitors' scores")
    best: float = Field(0.0, description="Highest competitor score on this dimension")
    worst: float = Field(0.0, description="Lowest competitor score on this dimension")
    n: int = Field(0, description="How many competitors were scored")


class CompetitorScoreRow(BaseModel):
    """One competitor's scores across every rubric dimension."""
    rank: int = 0
    brand_name: str = ""
    title: str = ""
    platform: str = Field("", description="Platform this competitor was found on")
    overall_score: float = Field(0.0, description="Weighted overall, computed the same way as the user's")
    dimension_scores: dict = Field(default_factory=dict, description="dimension name -> score")


class CompetitorBenchmark(BaseModel):
    """
    The measured benchmark the user's listing is scored against.

    Built by scoring each fetched competitor on the same rubric, then
    aggregating in Python. Cached per subcategory because it depends only on the
    competitor set and the rubric, not on the user's listing.
    """
    dimensions: list[CompetitorDimensionStat] = Field(default_factory=list)
    competitors: list[CompetitorScoreRow] = Field(default_factory=list)
    overall_mean: float = Field(0.0, description="Mean of the competitors' overall scores")
    rubric_version: str = ""
    from_cache: bool = False

    cohort: str = Field(
        "all_competitors", description="same_platform | all_competitors")
    platforms: list[str] = Field(
        default_factory=list, description="Platform slugs represented in this cohort")
    data_source: str = Field("", description="Provenance of the competitors that were scored")
    # A plain field rather than a property: a benchmark is rebuilt from cached
    # JSON, so it must carry this fact rather than re-derive it from a
    # `data_source` string that an older payload may not have.
    is_live_data: bool = Field(
        False, description="Whether the scored competitors were observed, not estimated")

    def mean_for(self, dimension: str) -> float | None:
        for d in self.dimensions:
            if d.dimension == dimension:
                return d.mean
        return None

    def percentile_for(self, score: float) -> int:
        """
        Where `score` sits among the competitors, 0-100.

        Measured by counting how many competitors it beats, rather than asking
        a model to guess a percentile.
        """
        scores = [c.overall_score for c in self.competitors]
        if not scores:
            return 0
        beaten = sum(1 for s in scores if score > s)
        ties = sum(1 for s in scores if abs(s - score) < 1e-9)
        return round((beaten + 0.5 * ties) / len(scores) * 100)


class CompetitorBenchmarkSet(BaseModel):
    """
    Both cohorts, computed from one set of scored competitors.

    A competitive set that spans platforms cannot be averaged into one number
    honestly: a 200-character keyword-stacked marketplace title and a brand
    site's 40-character product name are good listings by different rules, and
    pooling them measures house style rather than quality.

    So the same scored rows are aggregated twice — `same_platform` for the
    headline, `all_competitors` for category context. Both are real; neither is
    an extra LLM call. They are cached together because they are computed
    together, and a half-populated pair would be worse than none.
    """
    same_platform: CompetitorBenchmark = Field(default_factory=CompetitorBenchmark)
    all_competitors: CompetitorBenchmark = Field(default_factory=CompetitorBenchmark)
    # Which cohort the headline percentile should use. Falls back to
    # all_competitors when the same-platform cohort is too small to mean anything.
    primary_cohort: str = Field("same_platform", description="same_platform | all_competitors")
    note: str = Field("", description="Why the primary cohort was chosen")

    @property
    def primary(self) -> CompetitorBenchmark:
        return (self.same_platform if self.primary_cohort == "same_platform"
                else self.all_competitors)


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
    percentile: int = Field(0, description="Where the listing ranks in the headline cohort (0-100)")
    gap_analysis: list[dict] = Field(default_factory=list, description="Gaps sorted by impact (gap * weight)")

    # Which cohort the headline percentile was measured against, and how big it
    # was. Shown to the user: "top 18% of 11 competitors" is a claim that can be
    # checked, an unqualified percentile is not.
    percentile_basis: str = Field(
        "same_platform", description="same_platform | all_competitors")
    percentile_cohort_n: int = Field(0, description="Competitors in the headline cohort")
    category_percentile: int = Field(
        0, description="Percentile against every competitor found, across platforms")
    category_cohort_n: int = Field(0, description="Competitors in the category cohort")


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
    expected_score: float = Field(
        0.0, description="The generator's own projection — kept for comparison, not authoritative")
    key_changes: list[str] = Field(default_factory=list, description="What was changed and why")

    # Measured by re-scoring the variant through the same scorer that grades the
    # competitors. `is_verified` is false when scoring failed, in which case
    # there is no measured number rather than a fabricated one.
    measured_score: float = Field(0.0, description="Score measured by re-scoring this variant")
    measured_percentile: int = Field(0, description="Rank against the measured competitor set")
    measured_category_percentile: int = Field(
        0, description="Percentile against every competitor found, across platforms")
    measured_dimension_scores: dict = Field(default_factory=dict)
    is_verified: bool = Field(False, description="Whether measured_score is real")


class RewriteResult(BaseModel):
    """All rewrite variants."""
    variants: list[ListingRewrite] = Field(default_factory=list)
    original_score: float = Field(0.0)
    best_variant_score: float = Field(
        0.0, description="Best MEASURED score once verified; the projection before that")
    scores_verified: bool = Field(
        False, description="True once variants have been re-scored rather than self-reported")


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


# ── ACCOUNT & AUTH MODELS ───────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str


class AccountOut(BaseModel):
    """An account as returned by the API. Never carries password material."""
    account_id: str
    email: str
    role: str = Field("member", description="admin | member")
    active: bool = True
    rpm_limit: int
    max_concurrent: int
    daily_token_limit: int
    created_at: str
    last_login_at: str | None = None


class CreateAccountRequest(BaseModel):
    email: str
    password: str
    role: str = Field("member", description="admin | member")
    rpm_limit: int | None = None
    max_concurrent: int | None = None
    daily_token_limit: int | None = None


class UpdateAccountRequest(BaseModel):
    """All fields optional; only those supplied are changed."""
    role: str | None = None
    active: bool | None = None
    rpm_limit: int | None = None
    max_concurrent: int | None = None
    daily_token_limit: int | None = None


class SetPasswordRequest(BaseModel):
    password: str


class CreateKeyRequest(BaseModel):
    account_id: str
    label: str


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
    competitor_benchmark: CompetitorBenchmark = Field(
        default_factory=lambda: CompetitorBenchmark(),
        description="The cohort the headline score is measured against")
    competitor_benchmark_all: CompetitorBenchmark = Field(
        default_factory=lambda: CompetitorBenchmark(),
        description="Every competitor found, across platforms — context for the headline")
    listing_analysis: ListingAnalysis
    scores: ListingScore
    recommendations: RecommendationResult
    rewrites: RewriteResult
    agent_trace: AgentTrace | None = None
