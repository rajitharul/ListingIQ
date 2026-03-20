from __future__ import annotations
from pydantic import BaseModel, Field


class BrandInput(BaseModel):
    brand_name: str = Field(..., description="The brand name, e.g. 'KitKat'")
    product_category: str = Field(..., description="Product category, e.g. 'Chocolate Confectionery'")
    current_tagline: str = Field(..., description="Current marketing tagline")
    current_description: str = Field("", description="Current product description")
    target_audience: str = Field("", description="Target audience description")


class Competitor(BaseModel):
    name: str
    product: str
    tagline: str
    description: str
    market_position: str


class Dimension(BaseModel):
    name: str
    description: str
    weight: float = Field(1.0, ge=0.0, le=2.0)


class DimensionScore(BaseModel):
    dimension: str
    score: float = Field(..., ge=0.0, le=10.0)
    explanation: str
    strengths: list[str] = []
    weaknesses: list[str] = []


class ContentScore(BaseModel):
    brand_name: str
    tagline: str
    dimension_scores: list[DimensionScore]
    overall_score: float
    rank: int = 0


class BenchmarkSnippet(BaseModel):
    ideal_tagline: str
    ideal_description: str
    rationale: str
    dimension_scores: list[DimensionScore]


class ImprovementSuggestion(BaseModel):
    target_dimension: str
    current_score: float
    projected_score: float
    original_text: str
    improved_text: str
    changes_made: list[str]
    trade_offs: list[str] = []


class CompetitorAnalysisResult(BaseModel):
    competitors: list[Competitor]
    market_summary: str


class EvaluationResult(BaseModel):
    user_score: ContentScore
    competitor_scores: list[ContentScore]
    benchmark: BenchmarkSnippet
    dimensions: list[Dimension]
    rankings: list[dict]
    insights: list[str]


class ImprovementRequest(BaseModel):
    brand_input: BrandInput
    target_dimension: str
    current_evaluation: EvaluationResult | None = None


class FeedbackEntry(BaseModel):
    session_id: str
    brand_name: str
    feedback_type: str
    original_content: str
    suggested_content: str = ""
    user_comment: str = ""
    dimension: str = ""


class MemoryEntry(BaseModel):
    brand_name: str
    guideline: str
    source: str
    confidence: float = 1.0


class CompetitorTrend(BaseModel):
    competitor_name: str
    search_interest: float = Field(0.0, description="Relative Google Trends interest (0-100)")
    trend_direction: str = Field("stable", description="rising | declining | stable")
    recent_headlines: list[str] = []
    sentiment_score: float = Field(0.0, ge=-1.0, le=1.0, description="-1 negative to +1 positive")


class TrendAnalysisResult(BaseModel):
    brand_trend: CompetitorTrend
    competitor_trends: list[CompetitorTrend]
    market_momentum: str = Field("", description="Overall market direction summary")
    opportunities: list[str] = []
    threats: list[str] = []


class DepthConfig(BaseModel):
    enable_trends: bool = Field(True, description="Run Trend & Sentiment branch")
    depth_level: str = Field("standard", description="quick | standard | deep")
    reasoning: str = Field("", description="Why the depth controller chose this level")


class AgentNodeTrace(BaseModel):
    """Execution trace for a single agent node."""
    name: str
    role: str = Field("", description="core | branch | meta")
    status: str = Field("skipped", description="completed | skipped")
    duration_ms: float = 0.0
    parent: str = Field("", description="Node this branches from")


class AgentTrace(BaseModel):
    """Full execution trace for the pipeline run."""
    depth_level: str = "standard"
    depth_reasoning: str = ""
    enable_trends: bool = True
    total_duration_ms: float = 0.0
    nodes_executed: int = 0
    nodes_skipped: int = 0
    nodes: list[AgentNodeTrace] = []


class FullPipelineRequest(BaseModel):
    brand_input: BrandInput
    custom_dimensions: list[Dimension] | None = None
    session_id: str = "default"
    depth_config: DepthConfig | None = None


class FullPipelineResponse(BaseModel):
    competitors: CompetitorAnalysisResult
    evaluation: EvaluationResult
    suggestions: list[ImprovementSuggestion]
    memory_context: list[MemoryEntry]
    trend_data: TrendAnalysisResult | None = None
    # Branch agent outputs (all optional — only present in deep mode)
    brand_voice_data: dict | None = None
    audience_resonance_data: dict | None = None
    creative_variants_data: dict | None = None
    linguistic_data: dict | None = None
    gap_analysis_data: dict | None = None
    positioning_data: dict | None = None
    ab_test_data: dict | None = None
    roadmap_data: dict | None = None
    trend_projection_data: dict | None = None
    agent_trace: AgentTrace | None = None
