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
