"""
ListingIQ API — Multi-Agent Product Listing Optimization Engine
FastAPI application with endpoints for the full pipeline and individual agents.
Powered by LangGraph with SSE streaming support.
"""
import json as _json
import logging
import time
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from sse_starlette.sse import EventSourceResponse

from config import AUTH_ENABLED, CORS_ORIGINS, SESSION_TTL_HOURS

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
    AccountOut,
    CreateAccountRequest,
    CreateKeyRequest,
    ListingInput,
    ExtractListingRequest,
    ExtractListingResponse,
    LoginRequest,
    SetPasswordRequest,
    UpdateAccountRequest,
    FullPipelineRequest,
    FullPipelineResponse,
    FeedbackEntry,
    MemoryEntry,
    AgentNodeTrace,
    AgentTrace,
)
from agents.orchestrator import run_full_pipeline, get_compiled_graph
from providers.extract.listing import extract_listing
from agents.llm_client import LLMCallError, get_usage, start_usage_tracking
from agents.feedback_memory import (
    record_feedback,
    get_memory_context,
    add_guideline,
    get_feedback_log,
)
from scoring_history import record_score, get_score_history
from data.rubrics.loader import get_available_subcategories
import accounts as accounts_mod
import auth as auth_mod
from auth import AdminDep, Caller, CallerDep, SESSION_COOKIE
from quota import (
    acquire_slot,
    check_rate_only,
    estimate_cost,
    get_usage_today,
    pipeline_slot,
    record_usage,
    release_slot,
)


# ── Agent trace builder ──────────────────────────────────────
_AGENT_CATALOG = {
    "input_parser":         {"role": "core", "parent": "START"},
    "category_classifier":  {"role": "core", "parent": "input_parser"},
    "competitor_scout":     {"role": "core", "parent": "category_classifier"},
    "competitor_analyzer":  {"role": "core", "parent": "competitor_scout"},
    "competitor_scorer":    {"role": "core", "parent": "competitor_analyzer"},
    "listing_analyzer":     {"role": "core", "parent": "competitor_scorer"},
    "benchmark_scorer":     {"role": "core", "parent": "listing_analyzer"},
    "recommendation_engine": {"role": "core", "parent": "benchmark_scorer"},
    "rewrite_generator":    {"role": "core", "parent": "recommendation_engine"},
    "rewrite_verifier":     {"role": "core", "parent": "rewrite_generator"},
}


def _assert_catalog_matches_graph() -> None:
    """
    The trace catalog and the graph must not drift apart.

    `_build_agent_trace` reports a node as "skipped" when it is absent from the
    executed list, so a node added to the graph but not here simply never
    appears in the trace — it runs, it costs money, and the UI shows nothing.
    A node here but not in the graph is permanently "skipped". Both are silent.

    CLAUDE.md has claimed a test asserts this for some time; it did not exist.
    Failing at import is loud and immediate, which is what this needs to be.
    """
    from agents.orchestrator import build_listingiq_graph

    graph_nodes = {
        n for n in build_listingiq_graph().nodes
        if not n.startswith("__")          # LangGraph's own START/END entries
    }
    catalog = set(_AGENT_CATALOG)
    if graph_nodes != catalog:
        raise RuntimeError(
            "_AGENT_CATALOG does not match the graph. "
            f"In the graph but not the catalog: {sorted(graph_nodes - catalog)}; "
            f"in the catalog but not the graph: {sorted(catalog - graph_nodes)}"
        )


_assert_catalog_matches_graph()


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


async def _settle_usage(label: str, account_id: str) -> None:
    """Log the finished run's token usage and bill it to the caller's budget."""
    usage = get_usage()
    if usage is None or not usage.calls:
        return
    retried = sum(1 for c in usage.calls if c.attempts > 1)
    cost = estimate_cost(usage.prompt_tokens, usage.completion_tokens)
    log.info(
        "%s usage [%s]: %d calls (%d retried)  tokens_in=%d  tokens_out=%d  total=%d%s",
        label, account_id, len(usage.calls), retried,
        usage.prompt_tokens, usage.completion_tokens, usage.total_tokens,
        f"  cost=${cost:.4f}" if cost is not None else "",
    )
    # Failed runs are billed too: the tokens were spent either way.
    try:
        await record_usage(account_id, usage.prompt_tokens, usage.completion_tokens)
    except Exception as ex:
        log.warning("Failed to record usage for %s: %s", account_id, ex)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("ListingIQ Engine started — %d-agent LangGraph pipeline ready", len(_AGENT_CATALOG))
    if not AUTH_ENABLED:
        log.warning("=" * 68)
        log.warning("AUTH_ENABLED=false — every /api route is OPEN and unmetered.")
        log.warning("Never run this way anywhere the service is reachable.")
        log.warning("=" * 68)
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


# -- Read a listing from its URL --
@app.post("/api/extract", response_model=ExtractListingResponse)
async def extract_listing_route(request: ExtractListingRequest, caller: Caller = CallerDep):
    """
    Read a product page into a listing, so the user does not have to paste it.

    Deliberately a route rather than a pipeline node: a fetch failure here costs
    a retry on a form instead of a failed 60-second run, and the user sees and
    can correct what we read before it becomes the basis of every score.

    Rate limited but not charged against the token budget — it spends a page
    fetch, and only calls the model if the page publishes no structured data.
    """
    url = (request.url or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="A full http(s) product URL is required")

    check_rate_only(caller)
    start_usage_tracking()
    try:
        listing, source = await extract_listing(url, existing=request.listing)
    except LLMCallError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except Exception as e:                                   # noqa: BLE001
        log.exception("extract failed for %s", url)
        raise HTTPException(status_code=500, detail=f"Could not read that page: {e}") from e
    finally:
        await _settle_usage("extract", caller.account_id)

    return ExtractListingResponse(listing=listing, source=source)


# -- Full Pipeline --
@app.post("/api/pipeline", response_model=FullPipelineResponse)
async def pipeline(request: FullPipelineRequest, caller: Caller = CallerDep):
    """Execute the complete ListingIQ agent pipeline."""
    async with pipeline_slot(caller):
        return await _run_pipeline(request, caller)


async def _run_pipeline(request: FullPipelineRequest, caller: Caller):
    start_usage_tracking()
    try:
        t0 = time.perf_counter()
        result = await run_full_pipeline(
            listing_input=request.listing_input,
            session_id=request.session_id,
        )
        total_ms = (time.perf_counter() - t0) * 1000
        await _settle_usage("pipeline", caller.account_id)
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
    except LLMCallError as e:
        # Upstream model failure that survived its retries — 502, not 500,
        # so callers can distinguish "try again" from "your request is wrong".
        await _settle_usage("pipeline (failed)", caller.account_id)
        log.error("Pipeline LLM failure in %s: %s", e.caller, e)
        raise HTTPException(
            status_code=502,
            detail=f"Upstream model call failed at {e.caller} after {e.attempts} attempts.",
        )
    except Exception as e:
        await _settle_usage("pipeline (failed)", caller.account_id)
        log.error("Pipeline error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# -- SSE Streaming Pipeline --
@app.post("/api/pipeline/stream")
async def pipeline_stream(request: FullPipelineRequest, caller: Caller = CallerDep):
    """Stream pipeline progress via Server-Sent Events."""

    # Admit the run here, not inside the generator: once EventSourceResponse
    # starts streaming, an HTTPException can no longer become a 429 response.
    await acquire_slot(caller)

    async def event_generator():
        try:
            async for event in _stream_pipeline(request, caller):
                yield event
        finally:
            # Runs on normal completion and on client disconnect alike, so a
            # dropped connection cannot leak a concurrency slot.
            release_slot(caller)

    return EventSourceResponse(event_generator())


async def _stream_pipeline(request: FullPipelineRequest, caller: Caller):
    start_usage_tracking()
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
        await _settle_usage("SSE pipeline (failed)", caller.account_id)
        if isinstance(graph_error, LLMCallError):
            detail = (
                f"Upstream model call failed at {graph_error.caller} "
                f"after {graph_error.attempts} attempts. Please retry."
            )
        else:
            detail = f"Pipeline failed: {graph_error}"
        yield {
            "event": "error",
            "data": _json.dumps({
                "detail": detail,
                "failed_after": executed_nodes,
            }),
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
            competitor_benchmark=accumulated["competitor_benchmark"],
            competitor_benchmark_all=accumulated.get("competitor_benchmark_all")
            or accumulated["competitor_benchmark"],
            listing_analysis=accumulated["listing_analysis"],
            scores=accumulated["scores"],
            recommendations=accumulated["recommendations"],
            rewrites=accumulated["rewrites"],
        )
        elapsed = time.perf_counter() - pipeline_t0
        total_ms = elapsed * 1000
        response.agent_trace = _build_agent_trace(executed_nodes, node_timings, total_ms)
        log.info("◀ SSE pipeline DONE   %.1fs  nodes=%d  keys=%s", elapsed, len(executed_nodes), list(accumulated.keys()))
        await _settle_usage("SSE pipeline", caller.account_id)

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


# -- Authentication --
def _account_out(a) -> AccountOut:
    return AccountOut(**vars(a))


@app.post("/api/auth/login")
async def login(body: LoginRequest, response: Response):
    """Exchange credentials for a session cookie."""
    account = await accounts_mod.authenticate(body.email, body.password)
    if account is None:
        # One message for unknown email, wrong password and disabled account,
        # so the endpoint cannot be used to discover which emails exist.
        log.warning("Failed login for %r", body.email)
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    token, expires_at = await accounts_mod.start_session(account.account_id)
    response.set_cookie(
        SESSION_COOKIE, token,
        max_age=SESSION_TTL_HOURS * 3600,
        httponly=True, samesite="lax", path="/",
    )
    log.info("Login: %s (%s)", account.email, account.role)
    # The token is also returned so non-browser clients can use a bearer header.
    return {"account": _account_out(account), "token": token, "expires_at": expires_at}


@app.post("/api/auth/logout")
async def logout(request: Request, response: Response):
    token = auth_mod.session_token_from(request)
    if token:
        await accounts_mod.end_session(token)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"status": "logged_out"}


@app.get("/api/auth/me")
async def me(caller: Caller = CallerDep):
    """Who the current caller is, and their quota."""
    usage = await get_usage_today(caller.account_id)
    return {
        "account_id": caller.account_id,
        "email": caller.email,
        "role": caller.role,
        "via": caller.via,
        "rpm_limit": caller.rpm_limit,
        "max_concurrent": caller.max_concurrent,
        "daily_token_limit": caller.daily_token_limit,
        "usage_today": usage,
        "tokens_remaining": max(0, caller.daily_token_limit - usage["tokens"]),
    }


# -- Admin: accounts --
@app.get("/api/admin/accounts")
async def admin_list_accounts(caller: Caller = AdminDep):
    """Every account, with its limits and today's usage."""
    out = []
    for a in await accounts_mod.list_accounts():
        usage = await get_usage_today(a.account_id)
        out.append({**_account_out(a).model_dump(), "usage_today": usage})
    return out


@app.post("/api/admin/accounts", status_code=201)
async def admin_create_account(body: CreateAccountRequest, caller: Caller = AdminDep):
    kwargs = {k: v for k, v in {
        "rpm_limit": body.rpm_limit,
        "max_concurrent": body.max_concurrent,
        "daily_token_limit": body.daily_token_limit,
    }.items() if v is not None}
    try:
        account = await accounts_mod.create_account(
            email=body.email, password=body.password, role=body.role, **kwargs)
    except accounts_mod.AccountError as e:
        raise HTTPException(status_code=400, detail=str(e))
    log.info("Admin %s created account %s", caller.email, account.email)
    return _account_out(account)


@app.patch("/api/admin/accounts/{account_id}")
async def admin_update_account(
    account_id: str, body: UpdateAccountRequest, caller: Caller = AdminDep,
):
    try:
        account = await accounts_mod.update_account(
            account_id,
            role=body.role, active=body.active, rpm_limit=body.rpm_limit,
            max_concurrent=body.max_concurrent,
            daily_token_limit=body.daily_token_limit,
        )
    except accounts_mod.AccountError as e:
        raise HTTPException(status_code=400, detail=str(e))
    log.info("Admin %s updated account %s", caller.email, account_id)
    return _account_out(account)


@app.post("/api/admin/accounts/{account_id}/password")
async def admin_set_password(
    account_id: str, body: SetPasswordRequest, caller: Caller = AdminDep,
):
    try:
        await accounts_mod.set_password(account_id, body.password)
    except accounts_mod.AccountError as e:
        raise HTTPException(status_code=400, detail=str(e))
    log.info("Admin %s reset the password for %s", caller.email, account_id)
    return {"status": "password_set", "sessions_revoked": True}


# -- Admin: API keys --
@app.get("/api/admin/keys")
async def admin_list_keys(account_id: str | None = None, caller: Caller = AdminDep):
    return await auth_mod.list_keys(account_id)


@app.post("/api/admin/keys", status_code=201)
async def admin_create_key(body: CreateKeyRequest, caller: Caller = AdminDep):
    try:
        key_id, raw = await auth_mod.create_key(body.account_id, body.label)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    log.info("Admin %s issued key %s for %s", caller.email, key_id, body.account_id)
    # The raw key is shown exactly once, here.
    return {"key_id": key_id, "api_key": raw, "label": body.label}


@app.delete("/api/admin/keys/{key_id}")
async def admin_revoke_key(key_id: str, caller: Caller = AdminDep):
    if not await auth_mod.revoke_key(key_id):
        raise HTTPException(status_code=404, detail="No such key.")
    log.info("Admin %s revoked key %s", caller.email, key_id)
    return {"status": "revoked", "key_id": key_id}


# -- Rubric Catalog --
@app.get("/api/rubrics")
async def list_rubrics(caller: Caller = CallerDep):
    """List available pre-built scoring rubrics."""
    check_rate_only(caller)
    return {"subcategories": get_available_subcategories()}


# -- Feedback & Memory --
@app.post("/api/feedback")
async def submit_feedback(entry: FeedbackEntry, caller: Caller = CallerDep):
    """Record human feedback into the memory system."""
    check_rate_only(caller)
    return record_feedback(entry)


@app.get("/api/memory/{brand_name}", response_model=list[MemoryEntry])
async def get_memory(brand_name: str, caller: Caller = CallerDep):
    """Retrieve cached guidelines and preferences for a brand."""
    check_rate_only(caller)
    return get_memory_context(brand_name)


@app.post("/api/memory/guideline")
async def add_brand_guideline(brand_name: str, guideline: str, caller: Caller = CallerDep):
    """Add a brand guideline to memory."""
    check_rate_only(caller)
    return add_guideline(brand_name, guideline)


@app.get("/api/feedback/log")
async def feedback_log(brand_name: str | None = None, caller: Caller = CallerDep):
    """Retrieve the feedback log."""
    check_rate_only(caller)
    return get_feedback_log(brand_name)


# -- Scoring History --
@app.get("/api/history/{brand_name}")
async def scoring_history(brand_name: str, limit: int = 20, caller: Caller = CallerDep):
    """Retrieve scoring history for a brand."""
    check_rate_only(caller)
    return await get_score_history(brand_name, limit=limit)


# -- Caller's own quota usage --
@app.get("/api/usage")
async def usage(caller: Caller = CallerDep):
    """Today's token spend and run count for the calling key."""
    check_rate_only(caller)
    today = await get_usage_today(caller.account_id)
    return {
        **today,
        "email": caller.email,
        "role": caller.role,
        "via": caller.via,
        "daily_token_limit": caller.daily_token_limit,
        "tokens_remaining": max(0, caller.daily_token_limit - today["tokens"]),
        "rpm_limit": caller.rpm_limit,
        "max_concurrent": caller.max_concurrent,
        "estimated_cost_usd": estimate_cost(
            today["prompt_tokens"], today["completion_tokens"]
        ),
    }


if __name__ == "__main__":
    import uvicorn
    from config import HOST, PORT
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True)
