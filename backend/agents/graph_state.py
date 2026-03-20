"""
LangGraph State Definition
Central TypedDict that flows through every node in the Sitescore graph.
"""
from __future__ import annotations

from typing import TypedDict, Annotated
from operator import add

from models.schemas import (
    BrandInput,
    Competitor,
    CompetitorAnalysisResult,
    Dimension,
    BenchmarkSnippet,
    EvaluationResult,
    ImprovementSuggestion,
    MemoryEntry,
    TrendAnalysisResult,
    DepthConfig,
)


class SitescoreState(TypedDict, total=False):
    """
    Shared state flowing through the LangGraph pipeline.
    Each node reads what it needs and writes its output keys.
    """

    # ── Inputs (set before graph invocation) ──────────────────────
    brand_input: BrandInput
    custom_dimensions: list[Dimension] | None
    session_id: str

    # ── Node outputs ──────────────────────────────────────────────
    # competitor_analysis_node →
    competitor_result: CompetitorAnalysisResult

    # dimensions_node →
    dimensions: list[Dimension]

    # memory_node →
    memory_context: list[MemoryEntry]

    # benchmark_node →
    benchmark: BenchmarkSnippet

    # evaluator_node →
    evaluation: EvaluationResult

    # improvement_node →
    suggestions: list[ImprovementSuggestion]

    # trend_sentiment_node →
    trend_data: TrendAnalysisResult | None

    # depth control
    depth_config: DepthConfig | None

    # ── Branch agent outputs ──────────────────────────────────────
    brand_voice_data: dict | None
    audience_resonance_data: dict | None
    creative_variants_data: dict | None
    linguistic_data: dict | None
    gap_analysis_data: dict | None
    positioning_data: dict | None
    ab_test_data: dict | None
    roadmap_data: dict | None
    trend_projection_data: dict | None
