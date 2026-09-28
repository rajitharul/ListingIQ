"""
LangGraph State Definition — ListingIQ
Central TypedDict that flows through every node in the ListingIQ graph.
"""
from __future__ import annotations

from typing import TypedDict

from models.schemas import (
    ListingInput,
    ParsedListing,
    CategoryClassification,
    ScoringRubric,
    CompetitorScoutResult,
    CompetitorAnalysis,
    CompetitorBenchmark,
    CompetitorBenchmarkSet,
    ListingAnalysis,
    ListingScore,
    RecommendationResult,
    RewriteResult,
    MemoryEntry,
)


class ListingIQState(TypedDict, total=False):
    """
    Shared state flowing through the LangGraph pipeline.
    Each node reads what it needs and writes its output keys.
    """

    # ── Inputs (set before graph invocation) ──────────────────────
    listing_input: ListingInput
    session_id: str

    # ── Agent 1: Input Parser → ──────────────────────────────────
    parsed_listing: ParsedListing

    # ── Agent 2: Category Classifier → ───────────────────────────
    category: CategoryClassification
    rubric: ScoringRubric

    # ── Agent 3: Competitor Scout → (parallel branch) ────────────
    competitor_scout_result: CompetitorScoutResult

    # ── Agent 4: Competitor Analyzer → ───────────────────────────
    competitor_analysis: CompetitorAnalysis

    # ── Competitor Scorer → measured benchmark ───────────────────
    # The cohort that drives the headline score — same-platform where there are
    # enough of them, the whole category where there are not.
    competitor_benchmark: CompetitorBenchmark
    # Every competitor found, across platforms. Context for the headline.
    competitor_benchmark_all: CompetitorBenchmark
    benchmark_cohorts: CompetitorBenchmarkSet

    # ── Agent 5: Listing Analyzer → (parallel branch) ────────────
    listing_analysis: ListingAnalysis

    # ── Agent 6: Benchmark Scorer → (merge point) ────────────────
    scores: ListingScore

    # ── Agent 7: Recommendation Engine → ─────────────────────────
    recommendations: RecommendationResult

    # ── Agent 8: Rewrite Generator → ─────────────────────────────
    rewrites: RewriteResult

    # ── Memory context (from feedback_memory node if used) ───────
    memory_context: list[MemoryEntry]
