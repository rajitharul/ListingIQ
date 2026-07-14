"""
ListingIQ API — Multi-Agent Product Listing Optimization Engine
FastAPI application with endpoints for the full pipeline and individual agents.
Powered by LangGraph with SSE streaming support.
"""
import json as _json
import logging
import time
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from sse_starlette.sse import EventSourceResponse

from config import CORS_ORIGINS

# ── Logging setup ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-5s │ %(name)-35s │ %(message)s",
    datefmt="%H:%M:%S",
)
# Quiet down noisy third-party loggers
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
log = logging.getLogger("listingiq.api")

from models.schemas import (
    ListingInput,
    FullPipelineRequest,
    FullPipelineResponse,
    FeedbackEntry,
    MemoryEntry,
    AgentNodeTrace,
    AgentTrace,
)
from agents.orchestrator import run_full_pipeline, get_compiled_graph
from agents.feedback_memory import (
    record_feedback,
    get_memory_context,
    add_guideline,
    get_feedback_log,
)
from scoring_history import record_score, get_score_history
from data.rubrics.loader import get_available_subcategories


# ── Agent trace builder ──────────────────────────────────────
_AGENT_CATALOG = {
    "input_parser":         {"role": "core", "parent": "START"},
    "category_classifier":  {"role": "core", "parent": "input_parser"},
    "competitor_scout":     {"role": "core", "parent": "category_classifier"},
    "competitor_analyzer":  {"role": "core", "parent": "competitor_scout"},
    "listing_analyzer":     {"role": "core", "parent": "competitor_analyzer"},
    "benchmark_scorer":     {"role": "core", "parent": "listing_analyzer"},
    "recommendation_engine": {"role": "core", "parent": "benchmark_scorer"},
    "rewrite_generator":    {"role": "core", "parent": "recommendation_engine"},
}


def _build_agent_trace(
    executed_nodes: list[str],
    node_timings: dict[str, float],
    total_ms: float,
) -> AgentTrace:
    """Build AgentTrace from the list of nodes that actually executed."""
    nodes = []
    for name, meta in _AGENT_CATALOG.items():
        ran = name in executed_nodes
        nodes.append(AgentNodeTrace(
            name=name,
            role=meta["role"],
            status="completed" if ran else "skipped",
            duration_ms=node_timings.get(name, 0.0),
            parent=meta["parent"],
        ))
    completed = sum(1 for n in nodes if n.status == "completed")
    skipped = sum(1 for n in nodes if n.status == "skipped")
    return AgentTrace(
        total_duration_ms=total_ms,
        nodes_executed=completed,
        nodes_skipped=skipped,
        nodes=nodes,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("ListingIQ Engine started — 8-agent LangGraph pipeline ready")
    yield
    log.info("ListingIQ Engine stopped")


app = FastAPI(
    title="ListingIQ",
    description="Multi-Agent Product Listing Optimization Engine",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -- Health Check --
@app.get("/health")
async def health():
    return {"status": "healthy", "engine": "listingiq", "version": "1.0.0"}


# -- Full Pipeline --
@app.post("/api/pipeline", response_model=FullPipelineResponse)
async def pipeline(request: FullPipelineRequest):
    """Execute the complete ListingIQ 8-agent pipeline."""
    try:
        t0 = time.perf_counter()
        result = await run_full_pipeline(
            listing_input=request.listing_input,
            session_id=request.session_id,
        )
        total_ms = (time.perf_counter() - t0) * 1000
        executed = list(_AGENT_CATALOG.keys())
        result.agent_trace = _build_agent_trace(executed, {}, total_ms)

        # Record score to history
        try:
            await record_score(
                brand_name=request.listing_input.brand_name or "Unknown",
                session_id=request.session_id,
                product_title=request.listing_input.product_title,
                overall_score=result.scores.overall_score,
                dimension_scores=[ds.model_dump() for ds in result.scores.dimension_scores],
                subcategory=result.category.subcategory,
            )
        except Exception as ex:
            log.warning("Failed to record score history: %s", ex)

        return result
    except Exception as e:
        log.error("Pipeline error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# -- SSE Streaming Pipeline --
@app.post("/api/pipeline/stream")
async def pipeline_stream(request: FullPipelineRequest):
    """Stream pipeline progress via Server-Sent Events."""

    async def event_generator():
        graph = get_compiled_graph()
        initial_state = {
            "listing_input": request.listing_input,
            "session_id": request.session_id,
        }
        config = {"configurable": {"thread_id": request.session_id + "_stream"}}

        title = request.listing_input.product_title if hasattr(request.listing_input, "product_title") else request.listing_input.get("product_title", "?")
        log.info("▶ SSE pipeline START  title='%s'  session=%s", title[:60], request.session_id)
        pipeline_t0 = time.perf_counter()

        accumulated = {}
        executed_nodes: list[str] = []
        node_timings: dict[str, float] = {}
        graph_error = None
        node_t0 = time.perf_counter()

        try:
            async for event in graph.astream(
                initial_state, config=config, stream_mode="updates"
            ):
                for node_name, node_output in event.items():
                    if node_name == "__start__":
                        node_t0 = time.perf_counter()
                        continue
                    node_elapsed = (time.perf_counter() - node_t0) * 1000
                    node_timings[node_name] = node_elapsed
                    node_t0 = time.perf_counter()
                    executed_nodes.append(node_name)
                    accumulated.update(node_output)
                    log.info("  ✓ node_complete → %s  (%.0fms, keys: %s)", node_name, node_elapsed, list(node_output.keys()))
                    yield {
                        "event": "node_complete",
                        "data": _json.dumps({"node": node_name, "duration_ms": round(node_elapsed, 1)}),
                    }
        except Exception as e:
            graph_error = e
            log.error("  ✗ graph error: %s", e, exc_info=True)

        if graph_error:
            yield {
                "event": "error",
                "data": _json.dumps({"detail": f"Pipeline failed: {graph_error}"}),
            }
            return

        # Build the final response from accumulated node outputs
        try:
            response = FullPipelineResponse(
                parsed_listing=accumulated["parsed_listing"],
                category=accumulated["category"],
                rubric=accumulated["rubric"],
                competitors=accumulated["competitor_scout_result"],
                competitor_analysis=accumulated["competitor_analysis"],
                listing_analysis=accumulated["listing_analysis"],
                scores=accumulated["scores"],
                recommendations=accumulated["recommendations"],
                rewrites=accumulated["rewrites"],
            )
            elapsed = time.perf_counter() - pipeline_t0
            total_ms = elapsed * 1000
            response.agent_trace = _build_agent_trace(executed_nodes, node_timings, total_ms)
            log.info("◀ SSE pipeline DONE   %.1fs  nodes=%d  keys=%s", elapsed, len(executed_nodes), list(accumulated.keys()))

            # Record score to history
            try:
                await record_score(
                    brand_name=request.listing_input.brand_name if hasattr(request.listing_input, "brand_name") else request.listing_input.get("brand_name", "Unknown"),
                    session_id=request.session_id,
                    product_title=title,
                    overall_score=response.scores.overall_score,
                    dimension_scores=[ds.model_dump() for ds in response.scores.dimension_scores],
                    subcategory=response.category.subcategory,
                )
            except Exception as ex:
                log.warning("Failed to record SSE score history: %s", ex)

            yield {
                "event": "result",
                "data": response.model_dump_json(),
            }
        except Exception as e:
            log.error("  ✗ response build error: %s  keys=%s", e, list(accumulated.keys()))
            yield {
                "event": "error",
                "data": _json.dumps({"detail": f"Failed to build response: {e}. Keys available: {list(accumulated.keys())}"}),
            }

    return EventSourceResponse(event_generator())


# -- Rubric Catalog --
@app.get("/api/rubrics")
async def list_rubrics():
    """List available pre-built scoring rubrics."""
    return {"subcategories": get_available_subcategories()}


# -- Feedback & Memory --
@app.post("/api/feedback")
async def submit_feedback(entry: FeedbackEntry):
    """Record human feedback into the memory system."""
    return record_feedback(entry)


@app.get("/api/memory/{brand_name}", response_model=list[MemoryEntry])
async def get_memory(brand_name: str):
    """Retrieve cached guidelines and preferences for a brand."""
    return get_memory_context(brand_name)


@app.post("/api/memory/guideline")
async def add_brand_guideline(brand_name: str, guideline: str):
    """Add a brand guideline to memory."""
    return add_guideline(brand_name, guideline)


@app.get("/api/feedback/log")
async def feedback_log(brand_name: str | None = None):
    """Retrieve the feedback log."""
    return get_feedback_log(brand_name)


# -- Scoring History --
@app.get("/api/history/{brand_name}")
async def scoring_history(brand_name: str, limit: int = 20):
    """Retrieve scoring history for a brand."""
    return await get_score_history(brand_name, limit=limit)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
