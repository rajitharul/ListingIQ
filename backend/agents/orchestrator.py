"""
Orchestrator Agent – LangGraph StateGraph
Defines the Sitescore multi-agent pipeline as a compiled LangGraph graph
with parallel entry nodes, SQLite checkpoint persistence, and SSE-ready streaming.
"""
from __future__ import annotations

import asyncio
from langgraph.graph import StateGraph, START, END

from agents.graph_state import SitescoreState
from models.schemas import (
    BrandInput,
    Dimension,
    FullPipelineResponse,
)

# Node functions
from agents.competitor_analysis import competitor_analysis_node
from agents.evaluation_dimensions import dimensions_node
from agents.benchmark_generation import benchmark_node
from agents.evaluator_scoring import evaluator_node
from agents.content_improvement import improvement_node
from agents.feedback_memory import memory_node


# ── Build the graph ──────────────────────────────────────────────
def build_sitescore_graph() -> StateGraph:
    """Construct (but don't compile) the Sitescore pipeline graph."""
    graph = StateGraph(SitescoreState)

    # Register every node
    graph.add_node("competitor_analysis", competitor_analysis_node)
    graph.add_node("dimensions", dimensions_node)
    graph.add_node("memory", memory_node)
    graph.add_node("benchmark", benchmark_node)
    graph.add_node("evaluator", evaluator_node)
    graph.add_node("improvement", improvement_node)

    # ── Edges ────────────────────────────────────────────────────
    # Parallel fan-out from START → three independent nodes
    graph.add_edge(START, "competitor_analysis")
    graph.add_edge(START, "dimensions")
    graph.add_edge(START, "memory")

    # Benchmark is the single join point — waits for all three parallel nodes
    graph.add_edge("competitor_analysis", "benchmark")
    graph.add_edge("dimensions", "benchmark")
    graph.add_edge("memory", "benchmark")

    # Linear chain from here — each node has exactly one incoming edge
    graph.add_edge("benchmark", "evaluator")
    graph.add_edge("evaluator", "improvement")

    # Finish
    graph.add_edge("improvement", END)

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
) -> FullPipelineResponse:
    """
    Execute the complete Sitescore pipeline via LangGraph.
    Returns the same FullPipelineResponse as before — zero breaking changes.
    """
    graph = get_compiled_graph()

    initial_state: SitescoreState = {
        "brand_input": brand_input,
        "custom_dimensions": custom_dimensions,
        "session_id": session_id,
    }

    config = {"configurable": {"thread_id": session_id}}
    result = await graph.ainvoke(initial_state, config=config)

    return FullPipelineResponse(
        competitors=result["competitor_result"],
        evaluation=result["evaluation"],
        suggestions=result["suggestions"],
        memory_context=result.get("memory_context", []),
    )
