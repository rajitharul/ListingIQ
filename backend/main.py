"""
Sitescore API -- Multi-Agent Benchmarking Engine
FastAPI application with endpoints for the full pipeline and individual agents.
Now powered by LangGraph with SSE streaming support.
"""
import json as _json
import logging
import time
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from sse_starlette.sse import EventSourceResponse

from config import CORS_ORIGINS

# ── Logging setup ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-5s │ %(name)-28s │ %(message)s",
    datefmt="%H:%M:%S",
)
# Quiet down noisy third-party loggers
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
log = logging.getLogger("sitescore.api")
from models.schemas import (
    BrandInput,
    FullPipelineRequest,
    FullPipelineResponse,
    ImprovementRequest,
    ImprovementSuggestion,
    FeedbackEntry,
    MemoryEntry,
    DepthConfig,
)
from agents.orchestrator import run_full_pipeline, get_compiled_graph
from agents.competitor_analysis import analyze_competitors
from agents.evaluation_dimensions import get_dimensions, generate_dimensions
from agents.benchmark_generation import generate_benchmark
from agents.evaluator_scoring import evaluate_all
from agents.content_improvement import suggest_improvements
from agents.feedback_memory import (
    record_feedback,
    get_memory_context,
    add_guideline,
    get_feedback_log,
)
from agents.depth_controller import determine_depth
from scoring_history import record_score, get_score_history


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Sitescore Engine started — LangGraph pipeline ready")
    yield
    log.info("Sitescore Engine stopped")


app = FastAPI(
    title="Sitescore",
    description="Multi-Dimensional, Multi-Agent Benchmarking Engine for Marketing Content",
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
    return {"status": "healthy", "engine": "sitescore", "version": "1.0.0"}


# -- Full Pipeline --
@app.post("/api/pipeline", response_model=FullPipelineResponse)
async def pipeline(request: FullPipelineRequest):
    """Execute the complete Sitescore multi-agent pipeline."""
    try:
        # Auto-assign depth if not provided
        depth = request.depth_config
        if depth is None:
            depth = await determine_depth(request.brand_input)
        result = await run_full_pipeline(
            brand_input=request.brand_input,
            custom_dimensions=request.custom_dimensions,
            session_id=request.session_id,
            depth_config=depth,
        )
        # Record score to history for trend projection
        try:
            await record_score(
                brand_name=request.brand_input.brand_name,
                session_id=request.session_id,
                tagline=request.brand_input.current_tagline,
                overall_score=result.evaluation.user_score.overall_score,
                dimension_scores=[ds.model_dump() for ds in result.evaluation.user_score.dimension_scores],
                competitor_scores=[{"brand": cs.brand_name, "score": cs.overall_score} for cs in result.evaluation.competitor_scores],
                depth_level=depth.depth_level if depth else "standard",
            )
        except Exception as ex:
            log.warning("Failed to record score history: %s", ex)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -- SSE Streaming Pipeline --
@app.post("/api/pipeline/stream")
async def pipeline_stream(request: FullPipelineRequest):
    """Stream pipeline progress via Server-Sent Events.
    Each node completion emits an SSE event with the node name.
    The final event contains the full result payload.
    """

    async def event_generator():
        # Auto-assign depth if not provided
        depth = request.depth_config
        if depth is None:
            depth = await determine_depth(request.brand_input)
            yield {
                "event": "depth_assigned",
                "data": _json.dumps({"depth_level": depth.depth_level, "enable_trends": depth.enable_trends}),
            }

        graph = get_compiled_graph()
        initial_state = {
            "brand_input": request.brand_input,
            "custom_dimensions": request.custom_dimensions,
            "session_id": request.session_id,
            "depth_config": depth,
        }
        config = {"configurable": {"thread_id": request.session_id + "_stream"}}

        brand_name = request.brand_input.brand_name if hasattr(request.brand_input, "brand_name") else request.brand_input.get("brand_name", "?")
        log.info("▶ SSE pipeline START  brand=%s  session=%s", brand_name, request.session_id)
        pipeline_t0 = time.perf_counter()

        accumulated = {}
        graph_error = None
        try:
            async for event in graph.astream(
                initial_state, config=config, stream_mode="updates"
            ):
                # event shape: {"node_name": {"key": value, ...}}
                for node_name, node_output in event.items():
                    if node_name == "__start__":
                        continue
                    accumulated.update(node_output)
                    log.info("  ✓ node_complete → %s  (keys: %s)", node_name, list(node_output.keys()))
                    yield {
                        "event": "node_complete",
                        "data": _json.dumps({"node": node_name}),
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
                competitors=accumulated["competitor_result"],
                evaluation=accumulated["evaluation"],
                suggestions=accumulated["suggestions"],
                memory_context=accumulated.get("memory_context", []),
                trend_data=accumulated.get("trend_data"),
                brand_voice_data=accumulated.get("brand_voice_data"),
                audience_resonance_data=accumulated.get("audience_resonance_data"),
                creative_variants_data=accumulated.get("creative_variants_data"),
                linguistic_data=accumulated.get("linguistic_data"),
                gap_analysis_data=accumulated.get("gap_analysis_data"),
                positioning_data=accumulated.get("positioning_data"),
                ab_test_data=accumulated.get("ab_test_data"),
                roadmap_data=accumulated.get("roadmap_data"),
                trend_projection_data=accumulated.get("trend_projection_data"),
            )
            elapsed = time.perf_counter() - pipeline_t0
            log.info("◀ SSE pipeline DONE   brand=%s  %.1fs  keys=%s", brand_name, elapsed, list(accumulated.keys()))
            # Record score to history for trend projection
            try:
                await record_score(
                    brand_name=brand_name,
                    session_id=request.session_id,
                    tagline=request.brand_input.current_tagline if hasattr(request.brand_input, "current_tagline") else request.brand_input.get("current_tagline", ""),
                    overall_score=response.evaluation.user_score.overall_score,
                    dimension_scores=[ds.model_dump() for ds in response.evaluation.user_score.dimension_scores],
                    competitor_scores=[{"brand": cs.brand_name, "score": cs.overall_score} for cs in response.evaluation.competitor_scores],
                    depth_level=depth.depth_level if depth else "standard",
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


# -- Individual Agent Endpoints --
@app.post("/api/competitors")
async def get_competitors(brand_input: BrandInput):
    """Run only the competitor analysis agent."""
    result = await analyze_competitors(brand_input)
    return result


@app.post("/api/evaluate")
async def evaluate(request: FullPipelineRequest):
    """Run competitor analysis + evaluation in one call."""
    dimensions = await generate_dimensions(
        request.brand_input.brand_name,
        request.brand_input.product_category,
        request.brand_input.target_audience,
    )
    if request.custom_dimensions:
        dim_map = {d.name: d for d in dimensions}
        for cd in request.custom_dimensions:
            dim_map[cd.name] = cd
        dimensions = list(dim_map.values())
    competitor_result = await analyze_competitors(request.brand_input)
    bench = await generate_benchmark(
        request.brand_input, competitor_result.competitors, dimensions
    )
    evaluation = await evaluate_all(
        request.brand_input, competitor_result.competitors, dimensions, bench
    )
    return evaluation


@app.post("/api/improve", response_model=list[ImprovementSuggestion])
async def improve(request: ImprovementRequest):
    """Get targeted improvement suggestions for a specific dimension."""
    if not request.current_evaluation:
        raise HTTPException(status_code=400, detail="current_evaluation is required")
    memory = get_memory_context(request.brand_input.brand_name)
    result = await suggest_improvements(
        request.brand_input,
        request.current_evaluation,
        target_dimension=request.target_dimension,
        memory_context=memory,
    )
    return result


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
    """Retrieve scoring history for a brand (for trend projection)."""
    return await get_score_history(brand_name, limit=limit)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
