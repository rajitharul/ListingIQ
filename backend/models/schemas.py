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


class FullPipelineRequest(BaseModel):
    brand_input: BrandInput
    custom_dimensions: list[Dimension] | None = None
    session_id: str = "default"


class FullPipelineResponse(BaseModel):
    competitors: CompetitorAnalysisResult
    evaluation: EvaluationResult
    suggestions: list[ImprovementSuggestion]
    memory_context: list[MemoryEntry]
