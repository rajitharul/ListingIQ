# Sitescore — Multi-Agent AI Benchmarking Engine

> **GRACE 5% Agentic AI Initiative** — Nestle Investor Demo

A **6-agent agentic AI system** that competitively benchmarks marketing taglines using **LangGraph** orchestration, **OpenAI GPT-4o**, real-time **SSE streaming**, and **LangSmith** production observability. Full-stack application with a Python FastAPI backend and a Next.js React frontend.

---

## Table of Contents

- [What It Does](#what-it-does)
- [Architecture](#architecture)
- [The 6 Agents](#the-6-agents)
- [Scoring Dimensions](#scoring-dimensions)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [API Endpoints](#api-endpoints)
- [SSE Streaming Protocol](#sse-streaming-protocol)
- [Observability & Logging](#observability--logging)
- [LangSmith Tracing](#langsmith-tracing-production-observability)
- [Agentic Memory System](#agentic-memory-system)
- [Demo Presets](#demo-presets)
- [Quick Start](#quick-start)
- [How It Was Built](#how-it-was-built)
- [Key Design Decisions](#key-design-decisions)
- [Environment Variables](#environment-variables)

---

## What It Does

1. **Takes a brand's tagline** (e.g. *"Have a Break, Have a KitKat"*)
2. **Identifies the top 3 market competitors** using seed data + LLM enrichment
3. **Generates a theoretical perfect 10/10 benchmark tagline** as a mathematical ceiling
4. **Scores every brand** (yours + competitors) across 6 dimensions on a 0–10 scale
5. **Produces surgical improvement suggestions** targeting your weakest dimensions
6. **Learns from your feedback** — accepted/rejected suggestions are stored as persistent memory and applied to future runs

All of this executes as a **LangGraph StateGraph** with parallel fan-out, a join barrier, and a linear evaluation chain — streamed to the browser in real time over SSE.

---

## Architecture

### Agentic Pipeline (LangGraph StateGraph)

```
                        ┌─────────────────────────┐
                        │       START (User Input) │
                        └──────┬──────┬──────┬─────┘
                               │      │      │
                    ┌──────────┘      │      └──────────┐
                    ▼                 ▼                  ▼
          ┌─────────────────┐ ┌─────────────┐ ┌──────────────────┐
          │  Competitor      │ │  Dimensions  │ │  Feedback &      │
          │  Analysis Agent  │ │  Agent       │ │  Memory Agent    │
          │  (LLM call)      │ │  (no LLM)    │ │  (no LLM)        │
          └────────┬─────────┘ └──────┬───────┘ └────────┬─────────┘
                   │                  │                   │
                   └──────────┬───────┘───────────────────┘
                              ▼  (barrier join — waits for all 3)
                    ┌─────────────────────┐
                    │  Benchmark Generation│
                    │  Agent (LLM call)    │
                    └─────────┬───────────┘
                              ▼
                    ┌─────────────────────┐
                    │  Evaluator Scoring   │
                    │  Agent (LLM call)    │
                    └─────────┬───────────┘
                              ▼
                    ┌─────────────────────┐
                    │  Content Improvement │
                    │  Agent (LLM call)    │
                    └─────────┬───────────┘
                              ▼
                          ┌───────┐
                          │  END  │
                          └───────┘
```

**Parallel phase:** Competitor Analysis, Dimensions, and Memory run concurrently.
**Sequential phase:** Benchmark → Evaluator → Improvement run in series, each depending on the prior node's output.

### The 6 Agents

| # | Agent | File | Purpose | LLM? |
|---|-------|------|---------|------|
| 1 | **Competitor Analysis** | `competitor_analysis.py` | Retrieves top 3 competitors from seed data; generates strategic market summary via LLM | Yes (2 calls) |
| 2 | **Evaluation Dimensions** | `evaluation_dimensions.py` | Returns the 6 scoring dimensions (configurable, mergeable with custom dims) | No |
| 3 | **Feedback & Memory** | `feedback_memory.py` | Retrieves stored guidelines, learned preferences, and past feedback for the brand | No |
| 4 | **Benchmark Generation** | `benchmark_generation.py` | Creates the theoretically perfect 10/10 tagline as the scoring ceiling | Yes |
| 5 | **Evaluator Scoring** | `evaluator_scoring.py` | Numerically scores every brand (user + competitors) across all dimensions 0–10, ranked | Yes |
| 6 | **Content Improvement** | `content_improvement.py` | Generates surgical, dimension-targeted tagline edits with projected score improvements | Yes |

### Scoring Dimensions

| Dimension | What It Measures |
|-----------|-----------------|
| **Clarity** | Immediate comprehension — can a reader grasp the proposition in <3 seconds? |
| **Memorability** | Recall and stickiness — rhythm, alliteration, unique hooks |
| **Emotional Resonance** | Feeling evoked — joy, nostalgia, aspiration, comfort |
| **Persuasiveness** | Action compulsion — desire, urgency, reason to choose |
| **Brand Alignment** | How well the tagline reinforces brand identity and values |
| **Differentiation** | Competitive uniqueness — does it own a distinct space in the consumer's mind? |

---

## Tech Stack

### Backend

| Component | Technology | Version |
|-----------|-----------|---------|
| Runtime | Python | 3.10+ |
| Web Framework | FastAPI + Uvicorn | 0.115.6 |
| Agent Orchestration | **LangGraph** (StateGraph, parallel fan-out, barrier join) | ≥0.2.60 |
| LLM | OpenAI GPT-4o via `openai` SDK (async) | 1.58.1 |
| LLM Integration | `langchain-openai` + `langchain-core` | ≥0.3.0 / ≥0.3.25 |
| Streaming | Server-Sent Events via `sse-starlette` | ≥2.0.0 |
| Validation | Pydantic v2 | 2.10.4 |
| Observability | **LangSmith** (auto-tracing via env vars) | 0.7.12 |
| HTTP Client | httpx (async) | 0.28.1 |
| Persistence (planned) | SQLite checkpointer via `aiosqlite` | ≥0.20.0 |

### Frontend

| Component | Technology | Version |
|-----------|-----------|---------|
| Framework | Next.js (App Router) | 15.1.0 |
| UI Library | React | 19.0.0 |
| Styling | Tailwind CSS | 4.0.0 |
| Charts | Recharts (Radar chart) | ≥2.15.0 |
| Streaming | Native `ReadableStream` SSE client | — |
| Icons | Lucide React | ≥0.468.0 |
| Utilities | clsx | ≥2.1.1 |
| Type System | TypeScript | 5.7.2 |

---

## Project Structure

```
GRACE_5_Percent_agentic/
├── README.md
├── backend/
│   ├── .env                         # Environment variables (API keys, config)
│   ├── config.py                    # Env loader + settings (dotenv)
│   ├── main.py                      # FastAPI app, SSE endpoint, 10 routes, logging setup
│   ├── requirements.txt             # Python dependencies (11 packages)
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── orchestrator.py          # LangGraph StateGraph definition + compilation
│   │   ├── graph_state.py           # SitescoreState TypedDict (9 fields, shared state)
│   │   ├── llm_client.py            # Singleton AsyncOpenAI + logged_chat_completion()
│   │   ├── competitor_analysis.py   # Agent 1: competitor retrieval + market summary
│   │   ├── evaluation_dimensions.py # Agent 2: scoring dimension resolution
│   │   ├── feedback_memory.py       # Agent 3: feedback store + memory retrieval
│   │   ├── benchmark_generation.py  # Agent 4: ideal 10/10 tagline generation
│   │   ├── evaluator_scoring.py     # Agent 5: multi-brand scoring engine
│   │   └── content_improvement.py   # Agent 6: surgical improvement suggestions
│   ├── models/
│   │   └── schemas.py               # 13 Pydantic models (BrandInput, ContentScore, etc.)
│   └── data/
│       └── seed_competitors.py      # Pre-loaded competitor data (5 Nestle brands)
│
└── frontend/
    ├── package.json
    └── src/
        ├── app/
        │   ├── layout.tsx           # Root layout + Inter font
        │   ├── page.tsx             # Main page — orchestrates all UI panels
        │   └── globals.css          # CSS variables (red/white light theme)
        ├── components/
        │   ├── Header.tsx           # Top nav bar with red gradient logo
        │   ├── BrandInputForm.tsx   # Input form + 3 Nestle demo presets
        │   ├── LoadingOverlay.tsx    # Real-time 6-agent progress (SSE-driven)
        │   ├── CompetitorCards.tsx   # Competitor landscape cards
        │   ├── ScoreMatrix.tsx      # Multi-dimensional score table
        │   ├── RadarChart.tsx       # Recharts radar visualization
        │   ├── ImprovementPanel.tsx  # Targeted suggestions + accept/reject
        │   └── FeedbackPanel.tsx    # Memory & guidelines management
        ├── lib/
        │   └── api.ts               # API client + SSE streaming helper
        └── types/
            └── index.ts             # TypeScript interfaces
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check — returns `{"status": "healthy", "engine": "sitescore", "version": "1.0.0"}` |
| `POST` | `/api/pipeline` | Run full 6-agent pipeline (standard JSON response) |
| `POST` | `/api/pipeline/stream` | Run full pipeline with **SSE streaming** (real-time node progress) |
| `POST` | `/api/competitors` | Run only the competitor analysis agent |
| `POST` | `/api/evaluate` | Run competitor analysis + benchmark + full evaluation |
| `POST` | `/api/improve` | Get targeted improvement suggestions for a dimension |
| `POST` | `/api/feedback` | Submit human feedback (accept/reject/guideline) to memory |
| `GET` | `/api/memory/{brand_name}` | Retrieve cached guidelines for a brand |
| `POST` | `/api/memory/guideline` | Add a brand guideline to persistent memory |
| `GET` | `/api/feedback/log` | View the feedback audit log |

### Example Request

```bash
curl -X POST http://localhost:8000/api/pipeline/stream \
  -H "Content-Type: application/json" \
  -d '{
    "brand_input": {
      "brand_name": "KitKat",
      "product_category": "Chocolate",
      "current_tagline": "Have a Break, Have a KitKat",
      "current_description": "",
      "target_audience": ""
    },
    "session_id": "demo1"
  }'
```

---

## SSE Streaming Protocol

The `/api/pipeline/stream` endpoint emits three event types:

```
event: node_complete
data: {"node": "dimensions"}

event: node_complete
data: {"node": "memory"}

event: node_complete
data: {"node": "competitor_analysis"}

event: node_complete
data: {"node": "benchmark"}

event: node_complete
data: {"node": "evaluator"}

event: node_complete
data: {"node": "improvement"}

event: result
data: { full FullPipelineResponse JSON }

event: error          (only on failure)
data: {"detail": "Pipeline failed: ..."}
```

The frontend `LoadingOverlay` consumes these events to show real-time progress — each of the 6 agents lights up with a checkmark as it completes. The `\r\n` → `\n` normalization in the SSE client handles cross-platform line ending differences.

---

## Observability & Logging

### Structured Terminal Logging

Every agent call is logged to the backend terminal with structured output:

```
14:32:01 │ INFO  │ sitescore.api                │ ▶ SSE pipeline START  brand=KitKat  session=demo
14:32:01 │ INFO  │ sitescore.agent.dimensions   │ ⚙ dimensions_node ENTER
14:32:01 │ INFO  │ sitescore.agent.dimensions   │ ⚙ dimensions_node EXIT  6 dimensions
14:32:01 │ INFO  │ sitescore.agent.memory       │ ⚙ memory_node ENTER
14:32:01 │ INFO  │ sitescore.agent.memory       │ ⚙ memory_node EXIT  brand=KitKat  entries=0
14:32:01 │ INFO  │ sitescore.agent.competitors  │ ⚙ competitor_analysis_node ENTER
14:32:01 │ INFO  │ sitescore.llm                │   ↗ LLM call  [competitors.summary]  model=gpt-4o  prompt="You are a senior..."
14:32:03 │ INFO  │ sitescore.llm                │   ↙ LLM done [competitors.summary]  2.1s  tokens_in=312  tokens_out=86
14:32:03 │ INFO  │ sitescore.agent.competitors  │ ⚙ competitor_analysis_node EXIT  2.2s  competitors=3
14:32:03 │ INFO  │ sitescore.api                │   ✓ node_complete → competitor_analysis  (keys: ['competitor_result'])
14:32:03 │ INFO  │ sitescore.agent.benchmark    │ ⚙ benchmark_node ENTER
14:32:03 │ INFO  │ sitescore.llm                │   ↗ LLM call  [benchmark.generate]  model=gpt-4o  ...
14:32:07 │ INFO  │ sitescore.llm                │   ↙ LLM done [benchmark.generate]  3.8s  tokens_in=615  tokens_out=342
...
14:32:18 │ INFO  │ sitescore.api                │ ◀ SSE pipeline DONE   brand=KitKat  17.2s  keys=[...]
```

**What's logged:**
- Node enter/exit with elapsed time
- Every LLM call with model, prompt preview, latency, token counts (in/out)
- SSE event emissions with output keys
- Pipeline-level total elapsed time
- Noisy third-party loggers (`httpcore`, `httpx`, `openai`, `uvicorn.access`) are silenced to WARNING

### LangSmith Tracing (Production Observability)

The project integrates with **[LangSmith](https://smith.langchain.com)** for full agentic observability — **zero code changes required**. LangGraph auto-traces every node, LLM call, and state transition when the env vars are set.

**What LangSmith captures automatically:**

| Trace Data | Detail |
|------------|--------|
| Graph execution | Full waterfall of all 6 nodes with timing |
| LLM calls | Complete prompt, completion, model, token counts, latency |
| State transitions | What each node read from and wrote to the shared state |
| Parallel execution | Fan-out nodes shown as concurrent spans |
| Errors & retries | Stack traces and retry metadata |
| Cost | Per-call and cumulative token costs |

**Setup (3 env vars, no code changes):**

```env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=lsv2_pt_your_key_here
LANGCHAIN_PROJECT=sitescore
```

Then open **https://smith.langchain.com** → **Projects** → **sitescore** to see the trace waterfall:

```
sitescore_graph  ─────────────────────────────────── 17.2s
├── competitor_analysis  ──────── 2.1s
│   └── ChatOpenAI (gpt-4o)  ── 1.9s  ($0.003)
├── dimensions  ── 0.01s
├── memory  ── 0.01s
├── benchmark  ──────────── 3.8s
│   └── ChatOpenAI (gpt-4o)  ── 3.6s  ($0.005)
├── evaluator  ──────────── 6.2s
│   └── ChatOpenAI (gpt-4o)  ── 6.0s  ($0.008)
└── improvement  ────────── 4.9s
    └── ChatOpenAI (gpt-4o)  ── 4.7s  ($0.006)
```

---

## Agentic Memory System

The Feedback & Memory Agent provides **persistent learning**:

| Source | How It's Created | Confidence |
|--------|-----------------|------------|
| `brand_guideline` | User manually adds (e.g. *"Never use the word cheap"*) | 1.0 |
| `human_feedback` | User rejects a suggestion with a reason | 0.9 |
| `learned_preference` | User accepts a suggestion (auto-captured) | 0.8 |

Memory entries are injected into the **Improvement Agent's** prompt on subsequent runs, ensuring the AI respects brand guidelines and avoids previously rejected patterns.

> **Current storage:** In-memory (resets on server restart). Production would use Azure Cosmos DB or a vector database.

---

## Demo Presets

Pre-loaded with **5 Nestle brands** and their real-world competitors:

| Brand | Category | Competitors |
|-------|----------|-------------|
| **KitKat** | Chocolate Confectionery | Cadbury Dairy Milk, Snickers, Kinder Bueno |
| **Nescafe** | Instant Coffee | Starbucks VIA, Lavazza, Folgers |
| **Maggi** | Instant Noodles | Indomie, Nissin Cup Noodles, Knorr |
| **Cerelac** | Baby Food / Nutrition | Gerber, Heinz Baby, Hipp Organic |
| **Pure Life** | Bottled Water | Evian, Fiji Water, Dasani |

The frontend exposes quick-select buttons for KitKat, Nescafe, and Maggi. Any brand name can also be entered manually — if no seed data exists, the Competitor Analysis agent uses GPT-4o to generate competitors dynamically.

---

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- An OpenAI API key with GPT-4o access
- (Optional) A LangSmith account for production tracing

### 1. Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux
pip install -r requirements.txt
```

Create `backend/.env`:
```env
# Required
OPENAI_API_KEY=sk-proj-your-key-here
OPENAI_MODEL=gpt-4o
CORS_ORIGINS=http://localhost:3000

# Optional — LangSmith observability
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=lsv2_pt_your_key_here
LANGCHAIN_PROJECT=sitescore
```

Start the server:
```bash
python main.py
```

Backend runs at **http://localhost:8000** — check health at `/health`.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at **http://localhost:3000**.

### 3. Use It

1. Open http://localhost:3000
2. Select a Nestle preset (KitKat, Nescafe, or Maggi) or enter your own brand
3. Click **Launch Competitive Benchmark**
4. Watch 6 agents execute in real time (SSE streaming with live progress)
5. Explore the score matrix, radar chart, and improvement suggestions
6. Accept or reject suggestions — the AI learns from your feedback
7. Check LangSmith at https://smith.langchain.com → **sitescore** project for full traces

---

## How It Was Built

This project was built incrementally through the following phases:

### Phase 1: Full-Stack Scaffolding
- Created ~30 files: Python FastAPI backend + Next.js React frontend
- Pydantic v2 data models (13 schemas) for type-safe API contracts
- Seed competitor data for 5 Nestle brands with real-world market data
- 10 REST API endpoints covering the full pipeline + individual agents

### Phase 2: LangGraph Refactor
- Migrated from hand-rolled Python `asyncio` orchestration to **LangGraph StateGraph**
- Defined `SitescoreState` as a `TypedDict(total=False)` — nodes only return the keys they produce
- Implemented parallel fan-out (3 concurrent nodes) with barrier join at benchmark
- Each agent file exports both a standalone function and a LangGraph node wrapper

### Phase 3: SSE Streaming
- Added `sse-starlette` for Server-Sent Events streaming
- LangGraph `astream(stream_mode="updates")` emits node completions in real time
- Frontend `ReadableStream` SSE client with `\r\n` → `\n` normalization fix
- `LoadingOverlay` component shows live checkmarks as each agent completes

### Phase 4: UI Theme
- Applied **red and white light theme** (CSS custom properties)
- Accent color `#dc2626` throughout — buttons, gradients, spinner, radar chart
- Light glass card effect with soft shadows and gray borders

### Phase 5: Structured Logging
- Added structured logging across all 8 backend files using Python `logging`
- Format: `HH:MM:SS │ LEVEL │ logger_name │ message`
- `logged_chat_completion()` wrapper logs every LLM call with timing + token usage
- Node wrappers log enter/exit with elapsed time
- Pipeline-level timing in the SSE endpoint
- Noisy third-party loggers silenced to WARNING

### Phase 6: LangSmith Integration
- Added 3 env vars to `.env` — zero code changes needed
- LangGraph auto-traces every node, LLM call, and state transition
- Verified working: traces confirmed in LangSmith `sitescore` project via API
- Full waterfall view with parallel execution, token costs, and latency breakdowns

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **LangGraph over raw asyncio** | Declarative graph with built-in parallel fan-out, barrier joins, state management, and checkpoint persistence |
| **Singleton OpenAI client** | Connection pooling via `AsyncOpenAI` — avoids re-creating HTTP sessions per agent call |
| **SSE over WebSockets** | Simpler protocol for unidirectional server → client streaming; no handshake overhead |
| **`total=False` TypedDict state** | LangGraph nodes only need to return the keys they produce — partial state updates merge automatically |
| **Barrier join at benchmark node** | All 3 parallel nodes must complete before scoring begins — prevents KeyError race conditions |
| **Dual function exports per agent** | Each agent exports a standalone function (for individual endpoints) + a LangGraph node wrapper (for the graph) |
| **Seed data + LLM fallback** | Demo reliability with pre-loaded competitor data; graceful fallback to LLM generation for unknown brands |
| **Structured logging** | Every LLM call logs timing + token usage — essential for cost tracking and latency debugging |
| **LangSmith tracing** | Zero-code-change integration — LangGraph auto-reports every node + LLM call to LangSmith when env vars are set |
| **Pydantic v2 response models** | Type-safe API contracts that auto-generate OpenAPI docs and validate LLM JSON outputs |

---

## Environment Variables

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `OPENAI_API_KEY` | — | **Yes** | Your OpenAI API key |
| `OPENAI_MODEL` | `gpt-4o` | No | Model to use for all LLM calls |
| `CORS_ORIGINS` | `http://localhost:3000` | No | Comma-separated list of allowed frontend origins |
| `SQLITE_CHECKPOINT_PATH` | `data/checkpoints.db` | No | Path for LangGraph checkpoint persistence |
| `LANGCHAIN_TRACING_V2` | `false` | No | Set to `true` to enable LangSmith tracing |
| `LANGCHAIN_API_KEY` | — | No | LangSmith API key (`lsv2_pt_...`) |
| `LANGCHAIN_PROJECT` | `default` | No | LangSmith project name for trace grouping |

---

## License

Internal project — GRACE 5% Agentic AI initiative.
