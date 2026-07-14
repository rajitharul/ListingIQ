1. Think Before Coding

Don't assume. Don't hide confusion. Surface tradeoffs.

Before implementing:

State your assumptions explicitly. If uncertain, ask.
If multiple interpretations exist, present them - don't pick silently.
If a simpler approach exists, say so. Push back when warranted.
If something is unclear, stop. Name what's confusing. Ask.
2. Simplicity First

Minimum code that solves the problem. Nothing speculative.

No features beyond what was asked.
No abstractions for single-use code.
No "flexibility" or "configurability" that wasn't requested.
No error handling for impossible scenarios.
If you write 200 lines and it could be 50, rewrite it.
Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

3. Surgical Changes

Touch only what you must. Clean up only your own mess.

When editing existing code:

Don't "improve" adjacent code, comments, or formatting.
Don't refactor things that aren't broken.
Match existing style, even if you'd do it differently.
If you notice unrelated dead code, mention it - don't delete it.
When your changes create orphans:

Remove imports/variables/functions that YOUR changes made unused.
Don't remove pre-existing dead code unless asked.
The test: Every changed line should trace directly to the user's request.




# CLAUDE.md — ListingIQ Project Context

## What is this project?

ListingIQ is an 8-agent AI pipeline that scores ecommerce product listings against the top 10 competitors in a subcategory, then generates recommendations and optimized rewrite variants. Built for Supplements and Skincare verticals with extensible rubric system.

## Quick Start

```bash
# Backend
cd backend
source venv/bin/activate
pip install -r requirements.txt
python main.py  # Runs on :8000

# Frontend
cd frontend
npm install
npm run dev  # Runs on :3000
```

Required env vars in `backend/.env`:
- `OPENAI_API_KEY` — required, GPT-4o calls
- `OPENAI_MODEL` — defaults to `gpt-4o`
- `CORS_ORIGINS` — defaults to `http://localhost:3000`

Optional:
- `LANGCHAIN_TRACING_V2=true`, `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT` — for LangSmith tracing
- `RAINFOREST_API_KEY` — placeholder for future real competitor data API

## Project Structure

```
contrem_analyser/
├── backend/                    # FastAPI + LangGraph
│   ├── main.py                 # FastAPI app, endpoints, SSE streaming
│   ├── config.py               # Env vars (OpenAI key, CORS, model)
│   ├── scoring_history.py      # SQLite score persistence
│   ├── models/
│   │   └── schemas.py          # All Pydantic v2 models
│   ├── agents/
│   │   ├── llm_client.py       # AsyncOpenAI singleton + logged_chat_completion()
│   │   ├── graph_state.py      # ListingIQState TypedDict
│   │   ├── orchestrator.py     # LangGraph StateGraph build + compile
│   │   ├── input_parser.py     # Agent 1: entity extraction
│   │   ├── category_classifier.py  # Agent 2: subcategory + rubric loading
│   │   ├── competitor_scout.py     # Agent 3: 10 competitor listings (LLM knowledge)
│   │   ├── competitor_analyzer.py  # Agent 4: keyword/claim/trust patterns
│   │   ├── listing_analyzer.py     # Agent 5: per-dimension evaluation
│   │   ├── benchmark_scorer.py     # Agent 6: weighted scoring + gaps
│   │   ├── recommendation_engine.py # Agent 7: quick wins + strategic moves
│   │   ├── rewrite_generator.py    # Agent 8: 3 rewrite variants
│   │   └── feedback_memory.py  # Brand memory + feedback store
│   └── data/rubrics/
│       ├── _index.json         # Subcategory → filename mapping
│       ├── loader.py           # load_rubric() + LLM fallback
│       └── *.json              # 10 pre-built rubrics (5 supplements, 5 skincare)
├── frontend/                   # Next.js 15 + React 19 + Tailwind CSS 4
│   └── src/
│       ├── app/
│       │   ├── page.tsx        # Main page with all result sections
│       │   ├── layout.tsx      # Root layout
│       │   └── globals.css     # CSS vars (emerald theme)
│       ├── components/
│       │   ├── ListingInputForm.tsx      # Product listing input + demo presets
│       │   ├── LoadingOverlay.tsx        # SSE progress with 8 agent steps
│       │   ├── AgentVisualizer.tsx       # SVG pipeline DAG
│       │   ├── CompetitorCards.tsx       # 10 competitor listing cards
│       │   ├── CompetitorAnalysisPanel.tsx # Keyword/claim/trust patterns
│       │   ├── ScoreMatrix.tsx          # Per-dimension score table with gaps
│       │   ├── RadarChart.tsx           # Your listing vs Top 10 avg
│       │   ├── RecommendationPanel.tsx  # Quick wins + strategic moves
│       │   ├── RewritePanel.tsx         # 3 rewrite variants with copy
│       │   ├── FeedbackPanel.tsx        # User feedback submission
│       │   └── Header.tsx               # App header
│       ├── lib/api.ts          # SSE streaming client (runPipelineStream)
│       └── types/index.ts      # TypeScript types mirroring Pydantic schemas
└── README.md
```

## Architecture

### Pipeline Topology (Sequential)

```
START → input_parser → category_classifier → competitor_scout →
competitor_analyzer → listing_analyzer → benchmark_scorer →
recommendation_engine → rewrite_generator → END
```

The pipeline is **fully sequential** — no parallel fan-out. This is a deliberate decision: LangGraph's barrier join caused KeyError and duplicate execution bugs when we tried parallel fan-in. Sequential is reliable and total runtime (~60s) is acceptable.

### Agent Pattern

Every agent follows the same pattern:
1. An `async def <name>_node(state: ListingIQState) -> dict` function that LangGraph calls
2. Inside, it reads what it needs from `state`, calls `logged_chat_completion()` with a system prompt and JSON schema
3. Parses the LLM response into Pydantic models
4. Returns a dict with its output key(s) to merge into graph state

Example state flow:
- `input_parser_node` reads `state["listing_input"]`, returns `{"parsed_listing": ...}`
- `category_classifier_node` reads `state["parsed_listing"]`, returns `{"category": ..., "rubric": ...}`
- And so on through the chain

### LLM Client

All agents use `logged_chat_completion()` from `agents/llm_client.py`. This is a thin wrapper around `AsyncOpenAI.chat.completions.create` that adds timing and token logging. The OpenAI client is a singleton.

All agents use `response_format={"type": "json_object"}` to get structured JSON back from GPT-4o.

### SSE Streaming

The `/api/pipeline/stream` endpoint uses LangGraph's `astream(stream_mode="updates")`. Each node completion emits a `node_complete` SSE event. The final accumulated state is assembled into `FullPipelineResponse` and sent as a `result` event. The frontend's `runPipelineStream()` in `lib/api.ts` consumes these via `ReadableStream`.

### Rubric System

Pre-built rubrics live in `backend/data/rubrics/*.json`. Each has 8-12 weighted dimensions specific to a product subcategory. `_index.json` maps subcategory names to filenames. If no pre-built rubric exists, the category classifier agent generates one via LLM.

Available rubrics (10):
- Supplements: Magnesium Glycinate, Creatine Monohydrate, Vitamin D3+K2, Probiotic Capsules, Collagen Peptides
- Skincare: Vitamin C Serum, Retinol Serum, Hyaluronic Acid Serum, Niacinamide Serum, Sunscreen SPF50

## Key Conventions

- **All Pydantic models** are in `backend/models/schemas.py` — don't scatter models across agent files
- **Graph state** is a single `TypedDict` in `agents/graph_state.py` — every agent reads from and writes to this
- **Agent catalog** in `main.py` (`_AGENT_CATALOG`) must stay in sync with `orchestrator.py` node registrations
- **Frontend types** in `types/index.ts` mirror the Pydantic schemas — keep them in sync when changing schemas
- **CSS variables** for theming are in `globals.css` — components use `var(--accent)`, `var(--score-high)`, etc.
- **No mocking** in the LLM calls — all agents hit the real OpenAI API

## Common Tasks

### Adding a new rubric
1. Create `backend/data/rubrics/<vertical>_<subcategory>.json` following existing format
2. Add mapping in `backend/data/rubrics/_index.json`
3. No code changes needed — the loader picks it up automatically

### Adding a new agent
1. Create `backend/agents/<name>.py` with `async def <name>_node(state) -> dict`
2. Add output fields to `ListingIQState` in `graph_state.py`
3. Register node and edges in `orchestrator.py`
4. Add to `_AGENT_CATALOG` in `main.py`
5. Update `FullPipelineResponse` in `schemas.py` if the agent produces user-facing output
6. Update frontend types, API client, and components

### Modifying an agent's prompt
Each agent file has a system prompt string. Edit it directly. The `response_format={"type": "json_object"}` constraint means the LLM always returns parseable JSON matching the schema described in the prompt.

## Important Decisions

- **Sequential over parallel**: We tried parallel fan-out (competitor_scout || listing_analyzer) and it caused LangGraph barrier join bugs. Don't re-introduce parallelism without thorough testing.
- **LLM-sourced competitors**: Competitor Scout uses GPT-4o knowledge, not real API calls. The `data_source` field is set to `"llm_knowledge"`. Rainforest API integration is planned but not implemented.
- **All agents use GPT-4o**: No cost optimization with smaller models. Every agent calls `OPENAI_MODEL` (default: `gpt-4o`).
- **Emerald theme**: Brand color is emerald (`#059669`), not the old red. This is intentional for ecommerce trust signaling.

## Testing

No automated test suite exists yet. Manual testing:
1. Start backend: `cd backend && python main.py`
2. Start frontend: `cd frontend && npm run dev`
3. Use the demo presets in the input form (Weak Magnesium, Weak Vitamin C Serum, Moderate Creatine)
4. Verify all 8 SSE events fire and all result sections render

## Gotchas

- The backend venv is at `backend/venv/` — activate it before running
- `pip install requirements.txt` won't work — use `pip install -r requirements.txt`
- The `llm_client.py` logger is still named `"sitescore.llm"` — cosmetic only, doesn't affect functionality
- `scoring_history.py` uses SQLite at `backend/data/scoring_history.db` — created automatically on first write
- Frontend build requires Node 18+
