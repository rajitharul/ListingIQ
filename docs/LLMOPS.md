# LLM Ops Design — ListingIQ

**Status:** Proposed (design only — no code written yet)
**Target cloud:** Azure (Azure Container Apps + Key Vault + ACR, Cosmos DB when scaling past single-node)
**Author:** Engineering
**Last updated:** 2026-07-24

---

> ## Delivery status — updated 2026-09-12
>
> Parts of this plan are now built. This document is kept as the strategy; the
> table below is the authority on what actually exists.
>
> | Item | Status | Where |
> |------|--------|-------|
> | Single LLM chokepoint | **Done** | `structured_completion()` in `agents/llm_client.py` (renamed from `logged_chat_completion`) |
> | Retries, backoff, timeout, token ceiling | **Done** | same function; `LLM_*` env vars |
> | Schema conformance | **Done** | OpenAI strict structured outputs + `models/llm_responses.py`; hand-rolled JSON parsing removed |
> | Score-range validation | **Done** | `clamp()` — out-of-range values corrected, not rejected |
> | Per-run token accounting | **Done** | contextvar ledger; `start_usage_tracking()` / `get_usage()` |
> | Spend cap / circuit breaker | **Done** | `quota.py`: per-account daily tokens + service-wide breaker |
> | Auth & per-customer metering | **Done** | `accounts.py`, `auth.py`; accounts own the limits, keys inherit them |
> | Evaluation harness | **Done** | `evals/` — stability, discrimination, classification-drift gates |
> | Automated tests | **Done** | six offline suites in `backend/tests/` |
> | `langsmith` pinned | **Done** | now explicit in `requirements.txt` |
> | Correlation IDs across a run's calls | Outstanding | §3 below |
> | Structured JSON logging | Outstanding | §3 below |
> | Per-run cost rows in the database | Outstanding | only daily per-account totals are persisted |
> | Response caching | Outstanding | §4 below |
> | PII scrub / injection checks | Outstanding | §8 below |
> | Container, CI/CD, readiness probes | Outstanding | §7 below |
> | Feedback memory durability | Outstanding | still an in-process dict, and no agent reads it |


## 0. TL;DR

ListingIQ runs ~9 GPT-4o calls per pipeline invocation, and **every one of them already flows through a single function** — `structured_completion()` in `backend/agents/llm_client.py`. That seam is the whole ballgame: we attach cost accounting, correlation IDs, retries, caching, budget caps, metrics, and DB persistence there, and all 8 agents inherit it without being touched.

This doc proposes 5 independently-shippable phases:

| Phase | Theme | New infra | Effort |
|---|---|---|---|
| **1** | Instrument the seam (cost, `run_id`, structured logs, `llm_calls` table, `/api/costs`) | None | ~0.5 day |
| **2** | Resilience + cost control (timeouts, retries, fallback, spend cap, cache) | None (Redis optional) | ~1 day |
| **3** | Metrics + dashboards (OpenTelemetry → App Insights, alerts) | App Insights | ~1 day |
| **4** | Evaluation in CI (golden dataset, regression gate on prompt edits) | GitHub Actions | ~1 day |
| **5** | Deployment (Docker, ACA, Key Vault, ACR, Cosmos, CI/CD) | Azure resources | ~2 days |

Design principles (per `CLAUDE.md`): minimum code that solves the problem, surgical changes, reuse existing patterns (`scoring_history.py` is the template for the new tables). No speculative abstraction.

---

## 1. Current-state assessment

### 1.1 What already works (the good bones)

| Capability | Where | Note |
|---|---|---|
| **Single LLM chokepoint** | `agents/llm_client.py` `structured_completion()` | No agent calls the OpenAI SDK directly. 9 call sites, all routed here. |
| **Token capture** | `llm_client.py:37-40` | `prompt_tokens` / `completion_tokens` read from `response.usage`, logged, then discarded. |
| **LangSmith tracing** | `llm_client.py:24` `wrap_openai(...)` | Emits LLM spans under each LangGraph node when `LANGCHAIN_TRACING_V2=true`. No-op otherwise. |
| **Per-node latency** | `main.py:181-183` | Measured in the SSE `astream` loop, surfaced to the frontend as `AgentTrace`. |
| **Score persistence** | `scoring_history.py` | Async SQLite. **This is the pattern to copy** for `llm_calls` / `runs`. |
| **Secrets hygiene** | `.gitignore` | `.env` and `*.db` are correctly ignored (verified — nothing sensitive tracked). |
| **Central config** | `config.py` | One place to add price tables, budgets, feature flags. |
| **Central schemas** | `models/schemas.py` | One place to add cost/usage models. |

### 1.2 Gaps

| Pillar | Gap | Risk |
|---|---|---|
| **Cost** | Tokens captured but never converted to $, never aggregated | Can't answer "what did this run cost?" or "what did Brand X cost this month?" |
| **Correlation** | The 9 calls of one run share no ID | Can't reconstruct a single run's spend/latency from logs |
| **Logging** | Human-readable to stdout only (`main.py:17`) | Not machine-queryable; lost on container restart |
| ~~**Resilience**~~ | ~~no timeout/retry~~ | **Closed** — bounded retries with jittered backoff, per-call timeout, token ceiling |
| ~~**Cost control**~~ | ~~No spend cap / circuit breaker~~ | **Closed** — per-account daily token budget + service-wide breaker in `quota.py` |
| **Caching** | None | Re-scoring the same listing re-runs all 9 calls (~60s, full cost) |
| ~~**Evaluation**~~ | ~~Manual only~~ | **Closed** — `evals/` gates stability, discrimination and classification drift; six offline test suites |
| **Guardrails** | Partially closed | Score-range validation via `clamp()` and schema conformance via strict structured outputs. **Still missing: PII scrub, injection checks.** |
| **Deployment** | Still open | `HOST`/`PORT` are now configurable, but there is no container, CI/CD, readiness probe or secrets manager |
| **State durability** | Partially closed | Accounts, sessions, keys and usage persist in SQLite. `feedback_memory.py` is still an in-process dict — and no agent reads it. |
| ~~**Dependency pinning**~~ | ~~`langsmith` not in `requirements.txt`~~ | **Closed** — `langsmith` and `openai` are now pinned explicitly |

---

## 2. Target architecture

Everything hangs off the seam. Correlation is carried by a `ContextVar` so we do **not** thread a `run_id` argument through all 8 agents (surgical: only `llm_client.py`, `orchestrator.py`, and `main.py` change).

```
                    ┌───────────────────────────────────────────────┐
   agent nodes ───► │  structured_completion()    ◄── THE SEAM       │
   (unchanged)      │                                                │
                    │  1. read run_id from ContextVar                │
                    │  2. cache lookup (exact hash)          [P2]    │
                    │  3. budget/circuit-breaker check       [P2]    │
                    │  4. call w/ timeout + retry + fallback  [P2]   │
                    │  5. tokens → $ via price table          [P1]   │
                    │  6. emit: structured log + metric + DB row     │
                    └───────────────┬───────────────────────────────┘
                                    │
      ┌───────────────┬─────────────┴───────┬──────────────────┐
      ▼               ▼                     ▼                  ▼
  LangSmith    OTel → App Insights   SQLite / Cosmos      JSON logs → stdout
  (traces,     (latency, tokens,     llm_calls + runs     → Log Analytics
   prompts)     cost, errors) [P3]   tables [P1]           w/ run_id [P1]
```

**Correlation model:**
- `run_id` — one per pipeline invocation (uuid4), set in `run_full_pipeline()` / the SSE generator.
- `caller` — already passed (`caller="benchmark_scorer.score"` etc.), becomes the `agent` label.
- `session_id` — already in state, joins to `scoring_history`.

One row per LLM call → aggregate to one row per run → aggregate to per-brand / per-day / per-model rollups.

---

## 3. Phase 1 — Instrument the seam

**Goal:** turn the tokens we already compute-and-discard into queryable cost, latency, and correlation data. Zero new infrastructure.

### 3.1 Price table (`config.py`)

```python
# config.py — add
# $ per 1,000,000 tokens. Keep in sync with provider pricing.
MODEL_PRICES = {
    "gpt-4o":       {"in": 2.50, "out": 10.00},
    "gpt-4o-mini":  {"in": 0.15, "out": 0.60},
}
# Azure OpenAI note: if we migrate (see §7.7), pricing is per-deployment;
# key this table by the Azure *deployment name*, not the base model id.

def cost_usd(model: str, tokens_in: int, tokens_out: int) -> float:
    p = MODEL_PRICES.get(model, MODEL_PRICES["gpt-4o"])
    return round((tokens_in * p["in"] + tokens_out * p["out"]) / 1_000_000, 6)
```

### 3.2 `run_id` via ContextVar (new file `agents/run_context.py`)

```python
import contextvars, uuid

_run_id: contextvars.ContextVar[str] = contextvars.ContextVar("run_id", default="-")

def new_run_id() -> str:
    rid = uuid.uuid4().hex[:12]
    _run_id.set(rid)
    return rid

def current_run_id() -> str:
    return _run_id.get()
```

Set it once at the top of `run_full_pipeline()` (`orchestrator.py:78`) and inside the SSE `event_generator()` (`main.py:155`). ContextVars propagate across `await`, so every downstream `structured_completion()` sees the same id without a signature change.

### 3.3 Enriched seam (`agents/llm_client.py`)

```python
async def structured_completion(*, response_model, messages, caller, **kwargs):
    client = get_openai_client()
    run_id = current_run_id()
    t0 = time.perf_counter()
    status, err_type = "ok", None
    try:
        response = await client.chat.completions.create(model=model, messages=messages, **kwargs)
    except Exception as e:
        status, err_type = "error", type(e).__name__
        await record_llm_call(run_id, caller, model, 0, 0, 0.0,
                              (time.perf_counter()-t0)*1000, status, err_type)
        raise
    elapsed_ms = (time.perf_counter() - t0) * 1000
    u = response.usage
    ti, to = (u.prompt_tokens, u.completion_tokens) if u else (0, 0)
    usd = cost_usd(model, ti, to)
    log.info('{"evt":"llm_call","run_id":"%s","agent":"%s","model":"%s",'
             '"tokens_in":%d,"tokens_out":%d,"cost_usd":%.6f,"latency_ms":%.0f}',
             run_id, caller, model, ti, to, usd, elapsed_ms)
    await record_llm_call(run_id, caller, model, ti, to, usd, elapsed_ms, status, err_type)
    return response
```

> Note: the failure path records a row too — error rate is a first-class metric, not a silent log line.

### 3.4 New persistence — `llm_calls` + `runs` (`llm_metrics.py`, mirrors `scoring_history.py`)

```sql
CREATE TABLE llm_calls (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  agent TEXT NOT NULL,          -- the `caller` value
  model TEXT NOT NULL,
  tokens_in INTEGER NOT NULL,
  tokens_out INTEGER NOT NULL,
  cost_usd REAL NOT NULL,
  latency_ms REAL NOT NULL,
  status TEXT NOT NULL,          -- 'ok' | 'error'
  error_type TEXT,
  cached INTEGER DEFAULT 0,      -- populated in Phase 2
  created_at TEXT NOT NULL
);
CREATE INDEX idx_llm_calls_run ON llm_calls(run_id);
CREATE INDEX idx_llm_calls_created ON llm_calls(created_at);
```

A `runs` rollup table (one row per pipeline: `run_id`, `session_id`, `brand_name`, `subcategory`, `num_calls`, `total_tokens_in/out`, `total_cost_usd`, `total_latency_ms`, `overall_score`, `status`, `created_at`) is written at the end of `run_full_pipeline` / the SSE generator — same place `record_score()` is already called (`main.py:133`, `main.py:222`).

### 3.5 Structured logging (`main.py`)

Swap the `logging.basicConfig` formatter (`main.py:17-21`) for `python-json-logger` so stdout is line-delimited JSON with `run_id`, `agent`, `evt`. This is what Azure **Log Analytics** ingests cleanly. Keep a `LOG_FORMAT=text|json` env flag so local dev stays readable.

### 3.6 New endpoint — `/api/costs`

```python
@app.get("/api/costs")
async def costs(group_by: str = "day", brand_name: str | None = None):
    # SELECT ... FROM runs / llm_calls GROUP BY day|brand|model|agent
    # returns totals: cost_usd, tokens, calls, avg_latency_ms, error_rate
```

Drives a future "Ops" tab in the frontend (out of scope for P1 — endpoint first).

### 3.7 Phase 1 change surface

| File | Change |
|---|---|
| `config.py` | `MODEL_PRICES`, `cost_usd()`, budget/flag env vars |
| `agents/run_context.py` | **new** — ContextVar helpers |
| `agents/llm_client.py` | enrich seam; call `record_llm_call` |
| `llm_metrics.py` | **new** — `llm_calls` + `runs` tables (copy `scoring_history.py`) |
| `orchestrator.py` | `new_run_id()` at run start; write `runs` rollup |
| `main.py` | JSON logging; `new_run_id()` in SSE; write rollup; `/api/costs` |
| `requirements.txt` | pin `langsmith`, add `python-json-logger` |
| `models/schemas.py` | `LLMCallRecord`, `RunCostSummary` (if surfacing via API) |

**Ship criterion:** after any run, `SELECT run_id, sum(cost_usd), sum(tokens_in+tokens_out), count(*) FROM llm_calls GROUP BY run_id` returns real dollars, and `GET /api/costs` rolls it up by day/brand.

---

## 4. Phase 2 — Resilience + cost control

**Goal:** no single transient error kills a 60s pipeline; spend is bounded; repeat work is free. Still no required infra (Redis optional).

### 4.1 Timeout + retry + fallback (inside the seam)

Wrap the `create()` call with `tenacity`:
- Retry on `RateLimitError`, `APITimeoutError`, `APIConnectionError`, `InternalServerError`.
- Exponential backoff w/ jitter, `stop_after_attempt(3)`.
- Explicit per-call `timeout=` (e.g. 45s) so a hung socket can't stall a node.
- Optional **fallback model**: on final failure of the primary, retry once with `OPENAI_FALLBACK_MODEL` (`gpt-4o-mini`) so a degraded answer beats a 500. Record `model` actually used, so cost stays accurate.

One decorator, all 9 call sites protected. Retries and the fallback are logged as separate `llm_calls` rows (so retry storms are visible in cost data).

### 4.2 Budget / circuit breaker (`config.py` + seam)

```python
DAILY_BUDGET_USD = float(os.getenv("DAILY_BUDGET_USD", "25"))
PER_RUN_BUDGET_USD = float(os.getenv("PER_RUN_BUDGET_USD", "0.50"))
```

Before each call, check today's `SUM(cost_usd)` (cheap indexed query, cached ~30s in-process) and the current run's accumulated cost. If either cap is exceeded, raise `BudgetExceededError` → surfaced as SSE `error` event and HTTP 429. This is the guardrail that makes the endpoint safe to expose publicly.

### 4.3 Exact-match cache (`agents/llm_cache.py`)

Key = `sha256(model + json(messages) + temperature + response_format)`. Value = the raw completion JSON. Deterministic-ish agents (low temperature, e.g. `benchmark_scorer` at `temperature=0.2`, `input_parser`, `category_classifier`) benefit most.
- **Local / single-node:** SQLite table w/ TTL, or `functools`-style in-process LRU.
- **Azure / multi-node:** **Azure Cache for Redis** (`redis.asyncio`), TTL 24h.
- On hit: return cached, record an `llm_calls` row with `cached=1, cost_usd=0` (so hit-rate and savings are measurable).

Semantic caching (embedding similarity) is explicitly **out of scope** until exact-match hit-rate proves the value — no speculative complexity.

### 4.4 Lightweight guardrails (`agents/guardrails.py`)

- **Output validation:** clamp/validate LLM scores to `0.0–10.0` and weights sum ≈ 1.0 before building `ListingScore` (`benchmark_scorer.py:126-129` already computes weighted sum — validate inputs there).
- **Input hygiene:** strip obvious PII patterns from `listing_input` before logging prompts (emails, phone numbers) so we don't persist customer data in traces.
- **Injection note:** listings are user-supplied text fed into prompts. Low risk here (we ask for JSON scoring, not tool execution), but document it and keep the system/user role separation clean.

---

## 5. Phase 3 — Metrics + dashboards (Azure-native)

**Goal:** live operational visibility and alerting.

### 5.1 OpenTelemetry → Azure Monitor / Application Insights (recommended for Azure)

Use `azure-monitor-opentelemetry` — one `configure_azure_monitor()` call auto-instruments FastAPI + `httpx` + logging. From the seam, emit custom metrics:

| Metric | Type | Labels |
|---|---|---|
| `llm.tokens` | counter | `agent`, `model`, `direction=in\|out` |
| `llm.cost_usd` | counter | `agent`, `model` |
| `llm.latency_ms` | histogram | `agent`, `model` |
| `llm.errors` | counter | `agent`, `model`, `error_type` |
| `llm.cache_hits` | counter | `agent` |
| `pipeline.duration_ms` | histogram | `subcategory` |

App Insights gives KQL queries, workbooks, and **alert rules** (e.g. "error rate > 5% over 5 min", "daily cost > $20", "p95 latency > 90s") out of the box, plus distributed traces that sit alongside LangSmith's LLM-level traces. ACA also ships container metrics + Log Analytics automatically.

### 5.2 Portable alternative (if we ever leave Azure)

`prometheus-fastapi-instrumentator` for a `/metrics` endpoint + Grafana. Documented as the escape hatch; **not** the primary path given the Azure decision.

### 5.3 Dashboard contents

Cost/day and cost/run trend · tokens by agent · p50/p95 latency by agent · error rate · cache hit-rate · top brands by spend. Sourced from `runs`/`llm_calls` (SQL) and App Insights (metrics) — the same numbers, two lenses.

---

## 6. Phase 4 — Evaluation in CI

**Goal:** editing an agent prompt cannot silently regress scoring. This is the highest-value quality control because **prompts are the product** and there's currently zero automated coverage.

### 6.1 Golden dataset

Seed from the existing demo presets ("Weak Magnesium", "Weak Vitamin C Serum", "Moderate Creatine" — already in `ListingInputForm.tsx`). Each case: fixed `ListingInput` + expected invariants, not exact strings:
- Overall score within an expected band (e.g. "Weak Magnesium" → `< 4.5`).
- All rubric dimensions present in output; weights sum ≈ 1.0.
- Every agent's JSON parses into its Pydantic model.
- `gap_analysis` sorted by impact (contract in `benchmark_scorer.py:132`).

### 6.2 Harness

Two layers:
1. **pytest smoke** — run the full graph on each golden case, assert invariants + cost ceiling per run. Fast, deterministic-ish (low temp), runs on every PR.
2. **LangSmith `evaluate()`** — LLM-as-judge scoring rubric adherence / recommendation usefulness, tracked over time. Runs nightly or on-demand (costs money, so not per-commit).

### 6.3 CI gate (GitHub Actions)

`lint (ruff) → pytest smoke (mocked or 1 live golden case) → build`. A prompt change that pushes a golden score out of band fails the PR. Keep an `OPENAI_API_KEY` repo secret scoped to a low budget for the live case; mock the rest to keep CI cheap and hermetic.

---

## 7. Phase 5 — Deployment on Azure

**Goal:** reproducible container deploy with managed secrets, durable state, and working SSE.

### 7.1 Topology

```
GitHub → Actions (OIDC) → ACR (images)
                              │
                              ▼
                    Azure Container Apps
             ┌────────────────┴─────────────────┐
        backend (FastAPI)                 frontend (Next.js)
         ingress :8000                     ingress :3000
             │                                  │
   ┌─────────┼──────────────┐                   │
   ▼         ▼              ▼                    │
Key Vault  Cosmos DB   Azure Cache        (calls backend
(secrets)  (state)     for Redis           via internal or
           [when >1    (cache) [P2]         public FQDN)
            node]
             │
             ▼
      Application Insights + Log Analytics  [P3]
```

### 7.2 Backend Dockerfile (sketch)

Multi-stage, `python:3.12-slim`, non-root user, no `--reload`, `gunicorn` w/ uvicorn workers:

```dockerfile
FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install -r requirements.txt
COPY backend/ .
RUN useradd -m app && chown -R app /app
USER app
EXPOSE 8000
CMD ["gunicorn", "main:app", "-k", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120"]
```

> **SSE caveat:** `/api/pipeline/stream` streams for ~60s. Use `--timeout 120` on gunicorn, ACA request idle timeout ≥ 120s, and avoid any proxy that buffers responses. ACA HTTP ingress supports SSE; do **not** put a buffering gateway in front.

Frontend: `next build` with `output: 'standalone'`, served on its own ACA app; `CORS_ORIGINS` (`config.py:9`) set to the frontend FQDN.

### 7.3 Local parity — `docker-compose.yml`

backend + frontend + redis (+ optional postgres) so devs run the whole stack with one command and the same images CI builds.

### 7.4 Secrets — Key Vault, never in the image

- Local: `.env` (already gitignored).
- Azure: store `OPENAI_API_KEY`, `LANGCHAIN_API_KEY`, Redis/Cosmos connection strings in **Key Vault**; reference them as ACA secrets, or (better) pull at runtime via **Managed Identity** so no secret is stored in the app config at all. `config.py` reads the same env var names either way — no code change.

### 7.5 Durable state — promote off SQLite

SQLite (`scoring_history.db`, `llm_calls`) is fine on a **single** ACA replica with a mounted volume. The moment we scale to >1 replica or want durability across revisions:
- `feedback_memory.py:10-11` (currently in-memory, lost on restart) → **Cosmos DB** container (the file even says "In production this would use a vector DB or Cosmos DB").
- `scoring_history` + `llm_calls` + `runs` → **Cosmos DB** (or Azure Database for PostgreSQL if we want SQL/aggregations; Postgres is a better fit for the `/api/costs` GROUP BYs). Recommendation: **Postgres for metrics/history (relational aggregation), Cosmos for feedback/memory (document + future vector).**
- The persistence modules already isolate SQL behind functions (`record_score`, `record_llm_call`) — swapping the driver is contained.

### 7.6 Health / readiness

Split the current single `/health` (`main.py:112`):
- `/health` (liveness) — process up. Keep as-is.
- `/ready` (readiness) — checks DB reachable + OpenAI/Azure OpenAI credential present. ACA uses this to gate traffic during rollout.

### 7.7 Decision point — OpenAI vs **Azure OpenAI**

Deploying to Azure makes **Azure OpenAI** natural: private networking (no public egress to api.openai.com), data-residency, enterprise SLA, and Managed-Identity auth instead of a static key. Trade-offs:
- Routing changes from `model="gpt-4o"` to a **deployment name**; `AsyncOpenAI` → `AsyncAzureOpenAI` (base_url + api_version). Contained to `llm_client.py:18-26`.
- `MODEL_PRICES` keys by deployment name (§3.1 already notes this).
- `wrap_openai` (LangSmith) still works with the Azure client.

**Recommendation:** keep the OpenAI SDK for Phases 1–4 (no reason to churn), and make the Azure OpenAI switch part of Phase 5 as a config-only change behind a `LLM_PROVIDER=openai|azure` flag. Flagged as a decision to confirm before P5.

### 7.8 CI/CD — GitHub Actions

```
on: push to main
jobs:
  build-test:   ruff + pytest smoke (P4)
  build-push:   docker build backend & frontend → az acr login → push
  deploy:       az containerapp update --image ...   (OIDC federated creds, no stored SP secret)
```

Blue-green via ACA revisions: deploy new revision at 0% traffic → smoke `/ready` → shift 100%. Roll back = shift traffic to previous revision.

---

## 8. Cross-cutting additions

### 8.1 `requirements.txt`

```
langsmith>=0.1.0            # currently only transitive — PIN IT (P1)
python-json-logger>=2.0     # structured logs (P1)
tenacity>=8.2               # retries (P2)
redis>=5.0                  # cache, Azure Cache for Redis (P2, optional)
azure-monitor-opentelemetry>=1.6  # App Insights (P3)
gunicorn>=22.0             # prod server (P5)
# dev: pytest, pytest-asyncio, ruff (P4)
```

### 8.2 `config.py` new env vars

```
OPENAI_FALLBACK_MODEL=gpt-4o-mini
LLM_TIMEOUT_SECONDS=45
DAILY_BUDGET_USD=25
PER_RUN_BUDGET_USD=0.50
CACHE_ENABLED=true
CACHE_TTL_SECONDS=86400
LOG_FORMAT=json            # text for local
LLM_PROVIDER=openai        # openai|azure (P5)
APPLICATIONINSIGHTS_CONNECTION_STRING=   # P3
```

### 8.3 `.env.example` — refresh

Current file still says "Sitescore" and `LANGCHAIN_PROJECT=sitescore` (`.env.example:1,8`). Update names to ListingIQ and add the new vars (cosmetic but avoids confusion; `llm_client.py` logger name `sitescore.llm` is likewise stale per `CLAUDE.md` gotchas — leave code logger as-is unless we touch it).

---

## 9. Rollout order, risks, and non-goals

### Order
1 → 2 → 3 → 4 → 5, but **1 and 5 are the two highest-value bookends**: P1 makes cost/latency real with zero infra; P5 makes it deployable. 2–4 harden it. Each phase is independently shippable and reversible.

### Risks
| Risk | Mitigation |
|---|---|
| ContextVar `run_id` doesn't propagate through LangGraph's executor | Verify early with a 1-run smoke test; fall back to explicit arg threading only if needed |
| SSE breaks behind a buffering proxy in ACA | Test streaming against a deployed revision before cutover; documented in §7.2 |
| Budget cap false-positives block legit runs | Start with generous caps + log-only mode, then enforce |
| Cost drift when prices change | `MODEL_PRICES` is the single source; add a comment linking to the pricing page and a P4 test that flags unknown models |
| SQLite write contention under load | Fine for single replica; §7.5 promotes to Postgres before scaling out |

### Non-goals (explicitly out of scope to avoid over-engineering)
- Semantic/embedding cache (until exact-match hit-rate justifies it)
- Multi-provider abstraction beyond the OpenAI↔Azure OpenAI flag
- Re-introducing parallel agent fan-out (`CLAUDE.md` documents why sequential stays)
- A full frontend Ops dashboard (P1 ships the `/api/costs` endpoint; UI is a later, separate ask)

---

## 10. Open questions to confirm before building

1. **Metrics store:** Postgres for `runs`/`llm_calls` (better aggregation) vs stay on SQLite until scale-out? (Recommendation: SQLite through P1–P4, Postgres at P5.)
2. **Azure OpenAI vs OpenAI** for production inference — confirm before P5 (§7.7).
3. **Budgets:** what daily/per-run $ caps are acceptable? (Defaults proposed: $25/day, $0.50/run.)
4. **Frontend Ops tab:** in scope now, or endpoint-only for P1?
```
