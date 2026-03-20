"""
Orchestrator Agent – LangGraph StateGraph
Defines the Sitescore multi-agent pipeline as a compiled LangGraph graph
with parallel entry nodes, conditional branch agents, SQLite checkpoint
persistence, and SSE-ready streaming.

Graph topology (deep mode):
  START → [competitor_analysis, dimensions, memory]
  competitor_analysis → [trend_sentiment, brand_voice_profiler, audience_resonance] (conditional)
  [trend_sentiment, brand_voice, audience_resonance, dimensions, memory] → benchmark
  benchmark → [evaluator, creative_variants, linguistic_analysis] (conditional)
  [evaluator, creative_variants, linguistic_analysis] → evaluator_join (pass-through)
  evaluator → [improvement, gap_analysis, competitive_positioning] (conditional)
  [improvement, gap_analysis, positioning] → improvement_join (pass-through)
  improvement → [ab_test_generator, implementation_roadmap] (conditional)
  [ab_test, roadmap] → END
"""
from __future__ import annotations

import asyncio
from langgraph.graph import StateGraph, START, END

from agents.graph_state import SitescoreState
from models.schemas import (
    BrandInput,
    Dimension,
    DepthConfig,
    FullPipelineResponse,
)

# Core node functions
from agents.competitor_analysis import competitor_analysis_node
from agents.evaluation_dimensions import dimensions_node
from agents.benchmark_generation import benchmark_node
from agents.evaluator_scoring import evaluator_node
from agents.content_improvement import improvement_node
from agents.feedback_memory import memory_node

# Branch node functions
from agents.branches.trend_sentiment import trend_sentiment_node
from agents.branches.brand_voice_profiler import brand_voice_profiler_node
from agents.branches.audience_resonance import audience_resonance_node
from agents.branches.creative_variants import creative_variant_node
from agents.branches.linguistic_analysis import linguistic_analysis_node
from agents.branches.gap_analysis import gap_analysis_node
from agents.branches.competitive_positioning import competitive_positioning_node
from agents.branches.ab_test_generator import ab_test_generator_node
from agents.branches.implementation_roadmap import implementation_roadmap_node
from agents.branches.trend_projection import trend_projection_node


# ── Helper: check depth level ────────────────────────────────
def _get_depth(state: dict) -> str:
    cfg = state.get("depth_config")
    if cfg is None:
        return "standard"
    if isinstance(cfg, dict):
        return cfg.get("depth_level", "standard")
    return cfg.depth_level


def _trends_enabled(state: dict) -> bool:
    cfg = state.get("depth_config")
    if cfg is None:
        return True
    if isinstance(cfg, dict):
        return cfg.get("enable_trends", True)
    return cfg.enable_trends


# ── Routing functions ────────────────────────────────────────
def _route_after_competitor(state: dict) -> list[str]:
    """Route after competitor_analysis — always to benchmark; optionally to branches."""
    targets = ["benchmark"]
    if _trends_enabled(state):
        targets.append("trend_sentiment")
    if _get_depth(state) == "deep":
        targets.extend(["brand_voice_profiler", "audience_resonance"])
    return targets


def _route_after_benchmark(state: dict) -> list[str]:
    """Route after benchmark — always to evaluator; optionally to branches."""
    targets = ["evaluator"]
    if _get_depth(state) == "deep":
        targets.extend(["creative_variants", "linguistic_analysis"])
    return targets


def _route_after_evaluator(state: dict) -> list[str]:
    """Route after evaluator — always to improvement; optionally to branches."""
    targets = ["improvement"]
    if _get_depth(state) == "deep":
        targets.extend(["gap_analysis", "competitive_positioning", "trend_projection"])
    return targets


def _route_after_improvement(state: dict) -> list[str]:
    """Route after improvement — optionally to branches, then END."""
    if _get_depth(state) == "deep":
        return ["ab_test_generator", "implementation_roadmap"]
    return ["__end__"]


# ── Pass-through nodes for fan-in joins ──────────────────────
async def _passthrough(state: dict) -> dict:
    return {}


# ── Build the graph ──────────────────────────────────────────────
def build_sitescore_graph() -> StateGraph:
    """Construct (but don't compile) the Sitescore pipeline graph."""
    graph = StateGraph(SitescoreState)

    # ── Core nodes ────────────────────────────────────────────
    graph.add_node("competitor_analysis", competitor_analysis_node)
    graph.add_node("dimensions", dimensions_node)
    graph.add_node("memory", memory_node)
    graph.add_node("benchmark", benchmark_node)
    graph.add_node("evaluator", evaluator_node)
    graph.add_node("improvement", improvement_node)

    # ── Branch nodes ──────────────────────────────────────────
    graph.add_node("trend_sentiment", trend_sentiment_node)
    graph.add_node("brand_voice_profiler", brand_voice_profiler_node)
    graph.add_node("audience_resonance", audience_resonance_node)
    graph.add_node("creative_variants", creative_variant_node)
    graph.add_node("linguistic_analysis", linguistic_analysis_node)
    graph.add_node("gap_analysis", gap_analysis_node)
    graph.add_node("competitive_positioning", competitive_positioning_node)
    graph.add_node("ab_test_generator", ab_test_generator_node)
    graph.add_node("implementation_roadmap", implementation_roadmap_node)
    graph.add_node("trend_projection", trend_projection_node)

    # ── Edges ────────────────────────────────────────────────────
    # Parallel fan-out from START → three independent core nodes
    graph.add_edge(START, "competitor_analysis")
    graph.add_edge(START, "dimensions")
    graph.add_edge(START, "memory")

    # Conditional fan-out after competitor_analysis
    all_comp_targets = ["benchmark", "trend_sentiment", "brand_voice_profiler", "audience_resonance"]
    graph.add_conditional_edges(
        "competitor_analysis",
        _route_after_competitor,
        {t: t for t in all_comp_targets},
    )

    # All competitor branches feed into benchmark (join point)
    graph.add_edge("trend_sentiment", "benchmark")
    graph.add_edge("brand_voice_profiler", "benchmark")
    graph.add_edge("audience_resonance", "benchmark")
    graph.add_edge("dimensions", "benchmark")
    graph.add_edge("memory", "benchmark")

    # Conditional fan-out after benchmark
    all_bench_targets = ["evaluator", "creative_variants", "linguistic_analysis"]
    graph.add_conditional_edges(
        "benchmark",
        _route_after_benchmark,
        {t: t for t in all_bench_targets},
    )

    # Benchmark branches feed into evaluator (join)
    graph.add_edge("creative_variants", "evaluator")
    graph.add_edge("linguistic_analysis", "evaluator")

    # Conditional fan-out after evaluator
    all_eval_targets = ["improvement", "gap_analysis", "competitive_positioning", "trend_projection"]
    graph.add_conditional_edges(
        "evaluator",
        _route_after_evaluator,
        {t: t for t in all_eval_targets},
    )

    # Evaluator branches feed into improvement (join)
    graph.add_edge("gap_analysis", "improvement")
    graph.add_edge("competitive_positioning", "improvement")
    graph.add_edge("trend_projection", "improvement")

    # Conditional fan-out after improvement
    all_imp_targets = ["ab_test_generator", "implementation_roadmap", "__end__"]
    graph.add_conditional_edges(
        "improvement",
        _route_after_improvement,
        {t: t for t in all_imp_targets},
    )

    # Final branches go to END
    graph.add_edge("ab_test_generator", END)
    graph.add_edge("implementation_roadmap", END)

    return graph


# ── Compile with optional checkpointer ──────────────────────────
_compiled_graph = None


def get_compiled_graph(checkpointer=None):
    """Return the compiled graph, optionally with a checkpoint saver."""
    global _compiled_graph
    if _compiled_graph is None or checkpointer is not None:
        g = build_sitescore_graph()
        _compiled_graph = g.compile(checkpointer=checkpointer)
    return _compiled_graph


# ── Convenience runner (keeps the same API contract) ─────────────
async def run_full_pipeline(
    brand_input: BrandInput,
    custom_dimensions: list[Dimension] | None = None,
    session_id: str = "default",
    depth_config: DepthConfig | None = None,
) -> FullPipelineResponse:
    """
    Execute the complete Sitescore pipeline via LangGraph.
    Returns FullPipelineResponse with all core + branch agent outputs.
    """
    graph = get_compiled_graph()

    initial_state: SitescoreState = {
        "brand_input": brand_input,
        "custom_dimensions": custom_dimensions,
        "session_id": session_id,
        "depth_config": depth_config,
    }

    config = {"configurable": {"thread_id": session_id}}
    result = await graph.ainvoke(initial_state, config=config)

    return FullPipelineResponse(
        competitors=result["competitor_result"],
        evaluation=result["evaluation"],
        suggestions=result["suggestions"],
        memory_context=result.get("memory_context", []),
        trend_data=result.get("trend_data"),
        brand_voice_data=result.get("brand_voice_data"),
        audience_resonance_data=result.get("audience_resonance_data"),
        creative_variants_data=result.get("creative_variants_data"),
        linguistic_data=result.get("linguistic_data"),
        gap_analysis_data=result.get("gap_analysis_data"),
        positioning_data=result.get("positioning_data"),
        ab_test_data=result.get("ab_test_data"),
        roadmap_data=result.get("roadmap_data"),
        trend_projection_data=result.get("trend_projection_data"),
    )
