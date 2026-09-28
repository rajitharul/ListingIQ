"""
Orchestrator — LangGraph StateGraph for ListingIQ
Defines the 8-agent product listing optimization pipeline.

Graph topology (sequential — reliable execution, no fan-in issues):
  START → input_parser → category_classifier → competitor_scout →
  competitor_analyzer → competitor_scorer → listing_analyzer →
  benchmark_scorer → recommendation_engine → rewrite_generator →
  rewrite_verifier → END

Note: listing_analyzer runs after competitor_analyzer (not in parallel)
to avoid LangGraph fan-in/barrier-join issues. listing_analyzer only
reads parsed_listing + rubric (available from agent 2), so ordering is safe.
"""
from __future__ import annotations

from langgraph.graph import StateGraph, START, END

from agents.graph_state import ListingIQState
from models.schemas import (
    ListingInput,
    FullPipelineResponse,
)

# Agent node functions
from agents.input_parser import input_parser_node
from agents.category_classifier import category_classifier_node
from agents.competitor_scout import competitor_scout_node
from agents.listing_analyzer import listing_analyzer_node
from agents.competitor_analyzer import competitor_analyzer_node
from agents.competitor_scorer import competitor_scorer_node
from agents.benchmark_scorer import benchmark_scorer_node
from agents.recommendation_engine import recommendation_engine_node
from agents.rewrite_generator import rewrite_generator_node
from agents.rewrite_verifier import rewrite_verifier_node


# ── Build the graph ──────────────────────────────────────────────
def build_listingiq_graph() -> StateGraph:
    """Construct (but don't compile) the ListingIQ pipeline graph."""
    graph = StateGraph(ListingIQState)

    # ── 8 Agent Nodes ────────────────────────────────────────────
    graph.add_node("input_parser", input_parser_node)
    graph.add_node("category_classifier", category_classifier_node)
    graph.add_node("competitor_scout", competitor_scout_node)
    graph.add_node("competitor_analyzer", competitor_analyzer_node)
    graph.add_node("competitor_scorer", competitor_scorer_node)
    graph.add_node("listing_analyzer", listing_analyzer_node)
    graph.add_node("benchmark_scorer", benchmark_scorer_node)
    graph.add_node("recommendation_engine", recommendation_engine_node)
    graph.add_node("rewrite_generator", rewrite_generator_node)
    graph.add_node("rewrite_verifier", rewrite_verifier_node)

    # ── Edges (fully sequential) ─────────────────────────────────
    graph.add_edge(START, "input_parser")
    graph.add_edge("input_parser", "category_classifier")
    graph.add_edge("category_classifier", "competitor_scout")
    graph.add_edge("competitor_scout", "competitor_analyzer")
    graph.add_edge("competitor_analyzer", "competitor_scorer")
    graph.add_edge("competitor_scorer", "listing_analyzer")
    graph.add_edge("listing_analyzer", "benchmark_scorer")
    graph.add_edge("benchmark_scorer", "recommendation_engine")
    graph.add_edge("recommendation_engine", "rewrite_generator")
    graph.add_edge("rewrite_generator", "rewrite_verifier")
    graph.add_edge("rewrite_verifier", END)

    return graph


# ── Compile with optional checkpointer ──────────────────────────
_compiled_graph = None


def get_compiled_graph(checkpointer=None):
    """Return the compiled graph, optionally with a checkpoint saver."""
    global _compiled_graph
    if _compiled_graph is None or checkpointer is not None:
        g = build_listingiq_graph()
        _compiled_graph = g.compile(checkpointer=checkpointer)
    return _compiled_graph


# ── Convenience runner ───────────────────────────────────────────
async def run_full_pipeline(
    listing_input: ListingInput,
    session_id: str = "default",
) -> FullPipelineResponse:
    """
    Execute the complete ListingIQ pipeline via LangGraph.
    Returns FullPipelineResponse with all 8 agent outputs.
    """
    graph = get_compiled_graph()

    initial_state: ListingIQState = {
        "listing_input": listing_input,
        "session_id": session_id,
    }

    config = {"configurable": {"thread_id": session_id}}
    result = await graph.ainvoke(initial_state, config=config)

    return FullPipelineResponse(
        parsed_listing=result["parsed_listing"],
        category=result["category"],
        rubric=result["rubric"],
        competitors=result["competitor_scout_result"],
        competitor_analysis=result["competitor_analysis"],
        competitor_benchmark=result["competitor_benchmark"],
        competitor_benchmark_all=result.get("competitor_benchmark_all")
        or result["competitor_benchmark"],
        listing_analysis=result["listing_analysis"],
        scores=result["scores"],
        recommendations=result["recommendations"],
        rewrites=result["rewrites"],
    )
