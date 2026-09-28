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

ListingIQ is a 10-stage agent pipeline that scores an ecommerce product listing against the **real** top 10 competitors in its subcategory, then generates recommendations and optimized rewrite variants.

Competitors are fetched from a marketplace API and scored on the same rubric, so the benchmark is measured rather than estimated — see "Measured, not estimated" below, which is the principle the pipeline is built around. Built for Supplements and Skincare verticals with an extensible rubric system.

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

The whole app is behind a login. Bootstrap the first administrator, then sign in
at the frontend — no key handling required for browser use:

```bash
cd backend && python manage_accounts.py create-admin you@example.com
```

`PORT` and `HOST` are configurable (default `0.0.0.0:8000`). Point the frontend at
the backend with `BACKEND_URL` in `frontend/.env.local`.

Optional:
- `LANGCHAIN_TRACING_V2=true`, `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT` — for LangSmith tracing
- `RAINFOREST_API_KEY` — placeholder for future real competitor data API

## Project Structure

```
sitescore_agentic/
├── backend/                          # FastAPI + LangGraph
│   ├── main.py                       # App, pipeline + auth + admin routes, SSE
│   ├── config.py                     # Env: model, CORS, HOST/PORT, auth, quotas, resilience
│   ├── store.py                      # Shared SQLite schema + forward-migrations
│   ├── accounts.py                   # Accounts, scrypt passwords, login sessions
│   ├── auth.py                       # Caller resolution (session or API key) + deps
│   ├── quota.py                      # Rate, concurrency and token budgets per account
│   ├── manage_accounts.py            # CLI: bootstrap admin, accounts, limits, keys
│   ├── scoring_history.py            # SQLite score persistence
│   ├── models/
│   │   ├── schemas.py                # Domain + API models (Pydantic v2)
│   │   └── llm_responses.py          # Strict structured-output schemas + clamp()
│   ├── providers/                    # Where competitors come from
│   │   ├── base.py                   # Provider protocol + typed ProviderError
│   │   ├── rainforest.py             # Live marketplace data (1 search + N products)
│   │   ├── llm.py                    # Model estimates; labelled fallback only
│   │   ├── cache.py                  # Competitor listings by platform+subcategory
│   │   └── benchmark_cache.py        # Measured benchmarks, keyed by rubric hash
│   ├── agents/
│   │   ├── llm_client.py             # structured_completion(): retries, timeout, usage
│   │   ├── graph_state.py            # ListingIQState TypedDict
│   │   ├── orchestrator.py           # LangGraph StateGraph build + compile
│   │   ├── input_parser.py           # Agent 1: entity extraction
│   │   ├── category_classifier.py    # Agent 2: subcategory + rubric loading
│   │   ├── competitor_scout.py       # Agent 3: 10 competitor listings (LLM knowledge)
│   │   ├── competitor_analyzer.py    # Agent 4: patterns; frequencies COUNTED in Python
│   │   ├── competitor_stats.py       # Pure counting/arithmetic over listing text
│   │   ├── batch_scorer.py           # Shared: scores N listings on a rubric in one call
│   │   ├── competitor_scorer.py      # Measures the benchmark from real competitors
│   │   ├── listing_analyzer.py       # Agent 5: per-dimension evaluation
│   │   ├── benchmark_scorer.py       # Agent 6: weighted scoring + gaps
│   │   ├── recommendation_engine.py  # Agent 7: quick wins + strategic moves
│   │   ├── rewrite_generator.py      # Agent 8: 3 rewrite variants
│   │   ├── rewrite_verifier.py       # Re-scores the variants; no self-reported scores
│   │   └── feedback_memory.py        # Brand memory + feedback store (not yet wired in)
│   ├── data/
│   │   ├── auth.db                   # Accounts, sessions, keys, usage, caches
│   │   ├── scoring_history.db        # Score history per brand
│   │   └── rubrics/
│   │       ├── _index.json           # Subcategory → filename mapping + aliases
│   │       ├── loader.py             # load_rubric() + generic fallback
│   │       └── *.json                # 10 pre-built rubrics (5 supplements, 5 skincare)
│   ├── evals/                        # Score stability harness (calls the real model)
│   │   ├── fixtures.json             # 12 listings, 4 each weak/moderate/strong
│   │   ├── run_eval.py               # Runner: --mode scorer|full, --analyze
│   │   ├── stats.py                  # Pure statistics + gate thresholds
│   │   ├── report.py                 # Report rendering + pass/fail verdict
│   │   └── results/                  # Raw run output (gitignored)
│   └── tests/                        # All offline; none call OpenAI
│       ├── check_schemas.py          # Response models → valid strict JSON schema
│       ├── smoke_resilience.py       # Full graph, stubbed model: retry, clamp
│       ├── test_auth_quota.py        # Rate, concurrency, budget over real ASGI
│       ├── test_accounts_auth.py     # Accounts, sessions, roles, admin routes
│       ├── test_migration.py         # Pre-accounts database upgrade path
│       ├── test_providers.py         # Rainforest mapping, cache, honest fallback
│       ├── test_benchmark.py         # Measured competitor averages and percentile
│       ├── test_competitor_stats.py  # Counting, dedupe, structural arithmetic
│       ├── test_rewrite_verifier.py  # Measured rewrite scores
│       └── test_eval_harness.py      # Eval statistics, gates, runner plumbing
├── frontend/                         # Next.js 15 + React 19 + Tailwind CSS 4
│   └── src/
│       ├── middleware.ts             # Redirects visitors without a session to /login
│       ├── app/
│       │   ├── page.tsx              # Analyser: all result sections
│       │   ├── login/page.tsx        # Email + password sign-in
│       │   ├── admin/page.tsx        # Account management (admin only)
│       │   ├── api/auth/login/route.ts    # Sets the httpOnly session cookie
│       │   ├── api/auth/logout/route.ts   # Ends the session, clears the cookie
│       │   ├── api/[...path]/route.ts     # Proxy: forwards session, streams SSE
│       │   ├── layout.tsx            # Root layout
│       │   └── globals.css           # CSS vars (emerald theme)
│       ├── components/
│       │   ├── DataProvenance.tsx    # Live vs AI-estimated competitor data banner
│       │   ├── Header.tsx            # Branding, budget remaining, admin link, sign out
│       │   ├── ListingInputForm.tsx  # Product listing input + demo presets
│       │   ├── LoadingOverlay.tsx    # SSE progress with 8 agent steps
│       │   ├── AgentVisualizer.tsx   # SVG pipeline DAG
│       │   ├── CompetitorCards.tsx   # 10 competitor listing cards
│       │   ├── CompetitorAnalysisPanel.tsx  # Keyword/claim/trust patterns
│       │   ├── ScoreMatrix.tsx       # Per-dimension score table with gaps
│       │   ├── RadarChart.tsx        # Your listing vs Top 10 avg
│       │   ├── RecommendationPanel.tsx    # Quick wins + strategic moves
│       │   ├── RewritePanel.tsx      # 3 rewrite variants with copy
│       │   └── FeedbackPanel.tsx     # User feedback submission
│       ├── lib/api.ts                # SSE streaming client (runPipelineStream)
│       └── types/index.ts            # TS types mirroring the Pydantic schemas
├── docs/
│   ├── LANGGRAPH_GUIDE.md
│   └── LLMOPS.md
├── CLAUDE.md
└── README.md
```

## Architecture

### Pipeline Topology (Sequential)

```
START → input_parser → category_classifier → competitor_scout →
competitor_analyzer → competitor_scorer → listing_analyzer →
benchmark_scorer → recommendation_engine → rewrite_generator →
rewrite_verifier → END
```

The pipeline is **fully sequential** — no parallel fan-out. This is a deliberate decision: LangGraph's barrier join caused KeyError and duplicate execution bugs when we tried parallel fan-in. Sequential is reliable and total runtime (~60s) is acceptable.

### Agent Pattern

Every agent follows the same pattern:
1. An `async def <name>_node(state: ListingIQState) -> dict` function that LangGraph calls
2. Inside, it reads what it needs from `state`, calls `structured_completion()` with a prompt and a response model from `models/llm_responses.py`
3. Maps the validated response model into the domain models in `schemas.py`, clamping any bounded numbers
4. Returns a dict with its output key(s) to merge into graph state

Example state flow:
- `input_parser_node` reads `state["listing_input"]`, returns `{"parsed_listing": ...}`
- `category_classifier_node` reads `state["parsed_listing"]`, returns `{"category": ..., "rubric": ...}`
- And so on through the chain

### LLM Client

All agents call `structured_completion()` from `agents/llm_client.py`. The OpenAI client is a singleton wrapped by `wrap_openai` for LangSmith tracing.

`structured_completion()` takes a Pydantic response model and uses OpenAI **strict structured outputs** (`chat.completions.parse`) — the API guarantees the response conforms to the schema, so agents never hand-parse JSON or defend against missing keys. It also provides:

- bounded retries with exponential backoff + jitter on transient errors (timeout, connection, rate limit, 5xx), honouring `Retry-After`
- a per-call wall-clock `timeout`, so a hung request cannot hang a run
- a required `max_completion_tokens` ceiling per agent
- per-run token accounting via a contextvar (`start_usage_tracking()` / `get_usage()`)

A call that exhausts its retries raises `LLMCallError`, which `main.py` maps to HTTP 502. Truncated output (`LengthFinishReasonError`), content filtering, and model refusals fail immediately rather than retrying.

Response schemas live in `models/llm_responses.py`, separate from the domain models in `schemas.py`. Two reasons: domain models carry computed fields the LLM must never supply (`overall_score`, `gap_analysis`), and strict structured outputs support only a subset of JSON Schema — no numeric bounds, no bare dicts, no optional fields. Ranges are corrected after parsing with `clamp()` rather than rejected, so an out-of-range score does not fail a 60-second run.

### Measured, not estimated

The product sells a number, so a number it shows a customer must be either
measured or explicitly labelled as a projection. Three stages exist purely to
honour that, and each replaced a model estimate:

| Number | How it is produced |
|--------|--------------------|
| Competitor listings | Fetched from a marketplace API (`providers/`), with provenance on the result |
| `competitor_avg`, `gap` | `competitor_scorer` scores every fetched competitor on the rubric; Python averages them |
| `percentile` | Counted — how many scored competitors the listing beats |
| Keyword / claim / trust frequencies | Counted in Python (`agents/competitor_stats.py`) from the listing text |
| Structural stats (title length, bullet count, emoji use) | Exact arithmetic over the listings |
| Rewrite scores | `rewrite_verifier` re-scores each variant through the same batch scorer used on competitors |

**The rule when adding anything to the pipeline:** if a number can be computed
from data already held, compute it. Ask the model for judgement and attribution,
never for arithmetic. A model's estimate of a count it could not verify is a
fabricated statistic, however plausible it looks — and these numbers are quoted
to customers as evidence.

`agents/batch_scorer.py` is shared by the competitor scorer and the rewrite
verifier deliberately: variants and competitors must be graded by the same
process, or comparing their scores is meaningless.

### Competitor data providers

`providers/` decides where competitors come from and records it honestly. The
system is **platform-agnostic**: competitors are discovered on the open web and
each one is read wherever it lives, so a result set routinely spans a
marketplace, a second marketplace and a brand's own store.

| Module | Role |
|--------|------|
| `base.py` | Provider protocol, typed `ProviderError` (retryable vs not) |
| `http.py` | The single HTTP seam. **Tests patch `providers.http.make_client` and nothing else** |
| `platforms.py` | Domain → platform slug, and the per-platform format profile |
| `query.py` | `QueryPlan` — the searches to run, and the cache's identity |
| `discovery/serper.py` | Google Shopping + Google Search → candidates |
| `discovery/merge.py` | Dedupe and per-storefront cap → one row per real product |
| `extract/composite.py` | Routes each URL to the best reader for its platform |
| `extract/firecrawl.py` | The generic reader — any storefront on the open web |
| `extract/amazon.py` | Amazon via the product API, because scraping it does not work |
| `extract/structured.py` | `schema.org/Product` JSON-LD, parsed in Python |
| `extract/model.py` | One batched call for fields the page did not publish |
| `extract/listing.py` | The same path pointed at the user's own URL |
| `web.py` | `WebSearchProvider` — composes the above. The production default |
| `rainforest.py` | Amazon only. Still supported, no longer the default |
| `llm.py` | Model estimates; dev use and a labelled fallback |
| `cache.py` | Competitor listings, keyed by platform + subcategory + request |
| `benchmark_cache.py` | Both cohorts, keyed additionally by rubric **and competitor set** |

**Cost shape.** Roughly 3 search queries plus one page fetch per competitor —
about a cent per uncached subcategory, against 11 requests for the Amazon-only
path. Caching is still load-bearing: the first analysis in a subcategory pays,
the rest of the day does not.

**Reach `make_client` through the module** (`_http.make_client(...)`), never
`from providers.http import make_client`. A name bound at import cannot be
patched, so a test stub is silently ignored and the suite hits the live network
— which is exactly what happened to `test_providers.py` and went unnoticed
because everything still passed.

Rules that must not regress:

- **Estimated data is never cached.** This holds for listings *and* for the
  benchmark computed from them — the benchmark cache carries its own
  `is_live_data` and refuses anything that is not observed.
- **`is_live_data` is an allowlist** (`LIVE_DATA_SOURCES` in `models/schemas.py`),
  so it fails closed. A new provider that forgets to register is labelled
  *estimated*, which is visible and conservative. As a denylist it was the
  reverse: any unfamiliar source was automatically presented as observed.
- A fallback sets `data_source` to `llm_knowledge` and explains itself in
  `provider_note`. It never inherits the live provider's name.
- **Degrading is not estimating.** If page extraction fails entirely, the result
  stays `web_search` — discovery data is still *observed* data, and relabelling
  it "AI-estimated" would be a lie in the other direction.
- **A page we could not read is never scored.** It is shown as a real
  competitor with `counts_toward_benchmark=False`. Grading our own extraction
  failure lowers the competitor mean and *inflates* the user's percentile — a
  flattering wrong number, which nobody reports as a bug.
- **What we did not observe stays unobserved.** A competitor found through an
  organic web result has no price and no rating. Those stay empty; they never
  become `0.0`. `structural_patterns` averages over the listings that carry a
  figure, not over the whole cohort.
- The **discovery fingerprint excludes the generated query strings.** Queries
  are built from model-extracted entities and drift between runs; keying on them
  would make almost every lookup a miss and quietly destroy the cache hit rate.
  Bump `DISCOVERY_VERSION` in `providers/query.py` to invalidate deliberately.
- Same-brand variants are deduplicated **before** a page is fetched. Across
  platforms `brand_key` cannot collapse the same product (different house
  styles), so `title_similarity` and a per-domain cap do that instead — and
  where they disagree the code **under-collapses on purpose**: keeping a
  duplicate overstates the set slightly, merging two real SKUs deletes a
  competitor.

### What the live APIs actually do

Every item here was found by running against the real vendors, and each one
silently corrupted the data before it was fixed. They are recorded because none
of them is discoverable from the API documentation.

- **Google Shopping returns no merchant URLs.** Every `link` in a Serper
  `/shopping` response is a `google.com/search?ibp=oshop` interstitial. So
  shopping is treated as *metadata* — who sells this, at what price, with what
  rating — and the platform comes from the `source` merchant name. Web search
  supplies the addresses. `merge.graft_shopping_metadata` joins them by title
  containment; a shopping result that matches nothing stays as a priced
  competitor whose page cannot be read.
- **Matching titles needs containment, not Jaccard.** "Spring Valley Magnesium
  Glycinate 120ct" against "Spring Valley High Absorption Magnesium Glycinate
  Capsules for Bone and Muscle Support" scores 0.40 by Jaccard and 0.80 by
  containment. Containment alone is unsafe inside one category — every title
  shares "magnesium glycinate" — so a match also needs shared tokens that are
  *not* the category term.
- **Amazon publishes no `schema.org` markup** and returns ~150,000 characters of
  markdown, nearly all navigation. Generic extraction yields category links as
  bullet points. Amazon is therefore routed to the product API, and falls back
  to the generic reader when that key is missing or exhausted — a specialised
  reader failing must never be worse than not having one.
- **Navigation is well-formed markdown.** Breadcrumbs, footer columns, variant
  pickers and *browser error messages* all arrive as valid list items.
  `"Try disabling your extensions."` was captured as a competitor's only selling
  point and scored on the rubric. Hence `_is_chrome`, and hence
  `MIN_SCOREABLE_BULLETS` — one surviving bullet is an extraction artefact far
  more often than a listing with exactly one selling point.
- **"Tested" and "reviewed" are product claims, not article markers.**
  "Third-Party Tested" is one of the commonest real supplement claims. The
  article filter matches shapes like "Best N", "Top N" and "we tested", and any
  page publishing `schema.org/Product` is exempt regardless of its title.
- **Offline suites must be enforced, not assumed.** `test_web_provider.py`
  passed for a long time without stubbing the model, because structured data
  covered every fixture — then reached the live OpenAI API the moment a test
  removed the JSON-LD. Every suite is verified to pass with outbound sockets
  blocked.

### Two cohorts, one scoring call

A competitive set spanning platforms cannot honestly be averaged into one
number: a 200-character keyword-stacked marketplace title and a brand site's
40-character product name are good listings by different rules, and the pooled
mean measures whichever house style dominated the search.

`agents/benchmark_cohorts.py` aggregates the **same scored rows** twice —
`same_platform` and `all_competitors`. One LLM call, two benchmarks; the second
is arithmetic, not cost. `competitor_benchmark` in state still means "the cohort
the headline uses", so `benchmark_scorer` and `rewrite_verifier` read it
unchanged.

Below `BENCHMARK_MIN_COHORT` the same-platform cohort is not a benchmark — a
percentile over two competitors is noise with a decimal point — so the headline
falls back to the wider cohort and `ListingScore.percentile_basis` says so.

### The trace catalog must match the graph

`main._assert_catalog_matches_graph()` runs at import. Without it, a node added
to the graph but not to `_AGENT_CATALOG` runs, costs money, and never appears in
the trace, while a catalog entry with no node shows as permanently "skipped" —
both silent. This file previously claimed a test enforced that; none did.

### Accounts, Authentication & Quotas

Every `/api` route requires an authenticated caller; `/health` stays public for load balancers.

Four modules, each with one job:

| Module | Answers |
|--------|---------|
| `store.py` | the shared SQLite schema and its forward-migrations |
| `accounts.py` | accounts, passwords, login sessions |
| `auth.py` | who is calling (`Caller`), via session or API key |
| `quota.py` | how much they may spend |

**Two credentials, one identity.** A browser sends a session (httpOnly cookie, or `Authorization: Bearer`); a script sends `X-API-Key`. Both resolve to a `Caller` carrying the *owning account's* limits, so a customer's web and programmatic usage draw down one budget rather than two. Use the `CallerDep` dependency for any authenticated route and `AdminDep` where a role check is needed.

**Passwords** use `hashlib.scrypt` (memory-hard, standard library — no new dependency, no hand-rolled crypto) with a per-password salt and constant-time verification. Minimum length 10.

**Sessions** are opaque random tokens stored as SHA-256 hashes, deliberately *not* JWTs: revocation is immediate, there is no signing algorithm to misconfigure, and the token carries no readable claims. Default lifetime 7 days (`SESSION_TTL_HOURS`).

**API keys belong to accounts.** A key inherits its account's limits at issue time. A key with no owning account — one issued before accounts existed — is refused rather than assigned a guessed owner.

Invariants worth preserving:

- Login returns one identical message for wrong password, unknown email and disabled account, and hashes even when the account is missing, so the endpoint cannot be used to discover which emails exist.
- Changing a password or disabling an account revokes every session for it immediately, and its API keys stop working on the next request.
- **The last active admin cannot be demoted or disabled.** Without that guard you can lock everyone out of the admin panel with only the CLI as a way back.

`quota.py` enforces three limits against three different failure modes:

| Limit | Default | Storage | Guards against |
|-------|---------|---------|----------------|
| requests/minute | 10 | in-process sliding window | looping the endpoint |
| concurrent runs | 2 | in-process counter | many parallel 60s pipelines |
| tokens/day per account | 2,000,000 | SQLite | sustained spend |
| tokens/day service-wide | 20,000,000 | SQLite | one customer draining the OpenAI account |

Two properties worth preserving when editing this:

1. **Admission happens before the response starts.** `acquire_slot()` must be awaited in the endpoint body, not inside the SSE generator — once `EventSourceResponse` begins streaming, an `HTTPException` can no longer become a 429. The generator's `finally` calls `release_slot()`, so a client that disconnects mid-run still frees its slot.
2. **Budgets are checked before a run and recorded after**, so one run can overshoot its cap by its own cost. The alternative is refusing work on a guess. Failed runs are billed too — the tokens were spent either way.

The rate and concurrency limits are per-process and are **not** shared across instances: a multi-instance deploy needs Redis, and until then the effective limit is (per-key limit × instance count).

Quotas are enforced in **tokens**, not dollars, so no pricing table can go stale. Set `OPENAI_COST_PER_1M_INPUT` / `OPENAI_COST_PER_1M_OUTPUT` to also get runs logged in dollars and surfaced on `GET /api/usage`.

`AUTH_ENABLED=false` bypasses all of it for local development and logs a loud startup warning. Never set it anywhere reachable.

### Frontend auth & proxy

The browser never holds a token it can read. Logging in via `src/app/api/auth/login/route.ts` stores the session in an **httpOnly** cookie and strips the raw token from the response body; `src/app/api/[...path]/route.ts` then forwards that cookie to the backend as a bearer header on every proxied call. `lib/api.ts` therefore calls same-origin `/api/*` with no credentials of its own.

`src/middleware.ts` redirects visitors without a session cookie to `/login`. That is a **UX guard, not the security boundary** — it only checks the cookie exists. Every `/api` route is enforced by the backend, which validates the session properly and rejects expired or revoked ones.

Pages:

| Route | Purpose |
|-------|---------|
| `/login` | email + password sign-in |
| `/` | the analyser (requires any account) |
| `/admin` | account management (requires `role: admin`) |

The admin panel creates accounts, edits all three limits inline, promotes/demotes, disables/enables, sets passwords, and shows each account's tokens used today against its budget.

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

### Changing a scoring prompt or rubric
Run the eval harness before and after, and diff the reports:

```bash
python evals/run_eval.py --mode scorer --repeats 5     # baseline, before the edit
# ... make the change ...
python evals/run_eval.py --mode scorer --repeats 5     # after
```

A dimension appearing in "worst dimensions overall" is telling you which `scoring_criteria` text to tighten. Vague criteria ("is this well written?") produce high variance; criteria with anchored examples at 0, 5 and 10 produce low variance.

### Adding a new rubric
1. Create `backend/data/rubrics/<vertical>_<subcategory>.json` following existing format
2. Add mapping in `backend/data/rubrics/_index.json`
3. No code changes needed — the loader picks it up automatically
4. Optionally add weak/moderate/strong fixtures for it in `evals/fixtures.json` so the new rubric is covered by the stability gates

### Managing accounts
Everything below is also in the admin panel at `/admin`; the CLI exists for
bootstrapping and for scripted use.

```bash
cd backend
python manage_accounts.py create-admin you@example.com   # first admin only
python manage_accounts.py create user@example.com --rpm 20 --daily-tokens 500000
python manage_accounts.py list
python manage_accounts.py set-limits acct_ab12cd34 --daily-tokens 1000000
python manage_accounts.py password acct_ab12cd34         # revokes their sessions
python manage_accounts.py deactivate acct_ab12cd34
python manage_accounts.py issue-key acct_ab12cd34 "CI"   # spends that account's quota
python manage_accounts.py list-keys
```

Passwords are prompted for, never passed as arguments, so they stay out of shell
history and the process list. An issued key is printed once and stored only as a
hash — if it is lost, revoke and reissue.

### Changing the database schema
Edit `ensure_schema` in `store.py`. It runs on every connection and must stay
idempotent. `CREATE TABLE IF NOT EXISTS` will **not** alter an existing table, so
a changed column needs an explicit migration next to the existing ones — and a
case in `tests/test_migration.py`, which is the only suite that starts from a
populated database.

### Adding a new agent
1. Create `backend/agents/<name>.py` with `async def <name>_node(state) -> dict`
2. Add output fields to `ListingIQState` in `graph_state.py`
3. Register node and edges in `orchestrator.py`
4. Add to `_AGENT_CATALOG` in `main.py` (a test asserts it matches the graph exactly)
5. Update `FullPipelineResponse` in `schemas.py` if the agent produces user-facing output
6. Update frontend types, API client, and components — including the stage list in `LoadingOverlay.tsx` and the node/edge/layout in `AgentVisualizer.tsx` (remember to extend the SVG `viewBox` and `END_POS`)

### Modifying an agent's prompt
Each agent file has a prompt string. Edit it directly. Do NOT re-add a literal JSON shape to the prompt — the response model in `models/llm_responses.py` is the single source of truth for output shape, and a duplicated shape in the prompt is a second place to drift. To change the output shape, edit the response model and the mapping into the domain model.

After changing a response model, run `python tests/check_schemas.py       # response models -> valid strict JSON schema (auto-discovered)
python tests/smoke_resilience.py    # full graph, stubbed model: retry, exhaustion, clamping
python tests/test_auth_quota.py     # rate / concurrency / budget limits over real ASGI
python tests/test_accounts_auth.py  # accounts, sessions, roles, admin routes
python tests/test_migration.py      # upgrading a pre-accounts database
python tests/test_eval_harness.py   # eval statistics, report gates, runner plumbing
python tests/test_platforms.py      # domain -> platform; an unknown domain is never a marketplace
python tests/test_provider_http.py  # retryable actually retries; non-retryable does not
python tests/test_query_plan.py     # query composition; fingerprint survives model drift
python tests/test_discovery.py      # Serper mapping, dedupe, per-domain cap, cost contract
python tests/test_extraction.py     # JSON-LD first, thin-content guard, deadline, gap-fill
python tests/test_web_provider.py   # end to end: multi-platform, honest degradation
python tests/test_cohorts.py        # two cohorts from one call; thin-cohort fallback
python tests/test_own_listing.py    # reading a listing from its URL; catalog/graph assertion
python tests/test_providers.py      # Rainforest field mapping, caching, honest fallback
python tests/test_benchmark.py      # measured competitor averages, gaps, percentile
python tests/test_competitor_stats.py   # counting, brand dedupe, structural arithmetic
python tests/test_rewrite_verifier.py   # measured rewrite scores
```

Every suite uses a temporary database, so none of them touch `data/auth.db`.

**That isolation has a cost worth knowing:** because each suite starts from an empty database, migration paths are invisible to them. A real bug shipped this way — `CREATE TABLE IF NOT EXISTS` silently skips an existing table, so a schema change to `daily_usage` passed every test and then 500'd against a real database. `test_migration.py` exists specifically to cover that gap. **When you change the schema in `store.py`, add a case there**, not only to the suite that uses the new column.

### Eval harness (costs money)

Separate from the suites above, because it is the one thing that **must** call the real model — a stubbed model would only measure the stub.

```bash
cd backend
python evals/run_eval.py --mode scorer --repeats 5     # ~120 calls for all 12 listings
python evals/run_eval.py --mode full --repeats 3       # ~288 calls; end-to-end variance
python evals/run_eval.py --analyze evals/results/<f>.json   # re-report, free
```

It prints a call estimate and waits for confirmation before spending. Raw per-run results are always saved to `evals/results/` so the analysis can be re-run or diffed without paying again.

**Two modes.** `scorer` runs the setup stages — including the measured competitor benchmark — once per listing and reuses them, so every repeat scores *identical* inputs. That isolates the scorer's own variance, which is what a `benchmark_scorer` prompt edit changes. `full` re-runs every stage per repeat, so the variance includes classification flips and competitor-set churn, which is what a customer actually experiences. Use `scorer` routinely; `full` before a release.

**What it gates.** Stability (does one listing score the same twice?) and discrimination (does it rank strong above weak?) are independent — a perfectly stable scorer that cannot tell good from bad still fails. Thresholds live at the top of `evals/stats.py`:

| Gate | Limit | Meaning when it fails |
|------|-------|----------------------|
| overall score sd | 0.75 | the headline number is a sample, not a score |
| per-dimension sd | 1.50 | that dimension's `scoring_criteria` prose is too loose |
| classification consistency | 100% | repeats loaded different rubrics, so scores were never comparable |
| spearman(tier, score) | 0.70 | the scorer is not reliably ranking strong above weak |

Percentile coherence is reported as a **diagnostic, not a gate**, because `percentile` is still model-supplied rather than derived from `overall_score`. A low value means the two numbers shown side by side in the UI disagree.

Fixtures are in `evals/fixtures.json`: 12 listings, 4 each at weak/moderate/strong, across 10 subcategories. `tier` is the human judgement discrimination is measured against; `expected_subcategory` must match a key in `data/rubrics/_index.json`.

`smoke_resilience.py` stubs `chat.completions.parse`, so it runs the real LangGraph pipeline end to end for free. Run both after touching `llm_client.py`, any response model, or any agent's mapping code.

Beyond that, manual testing:
1. Start backend: `cd backend && python main.py`
2. Start frontend: `cd frontend && npm run dev`
3. Use the demo presets in the input form (Weak Magnesium, Weak Vitamin C Serum, Moderate Creatine)
4. Verify all 8 SSE events fire and all result sections render

## Related Documents

- [docs/OPERATIONS.md](docs/OPERATIONS.md) — running the stack, account management, troubleshooting, incident recipes
- [docs/LLMOPS.md](docs/LLMOPS.md) — LLM operations strategy; the status table at the top says what is built vs planned
- [docs/LANGGRAPH_GUIDE.md](docs/LANGGRAPH_GUIDE.md) — LangGraph concepts as used here

## Gotchas

- The backend venv is at `backend/venv/` — activate it before running
- `pip install requirements.txt` won't work — use `pip install -r requirements.txt`
- `backend/venv/` in the repo is a **macOS** venv (`_pydantic_core...darwin.so`) with no exec bits — it does not run on Linux. `frontend/node_modules/.bin/*` has the same problem. Build both fresh per machine; do not trust the committed copies (`node node_modules/typescript/bin/tsc` works around the missing exec bit)
- Lost an API key or password? Both are stored hashed and cannot be recovered — reissue or reset
- Locked out of the admin panel? `manage_accounts.py` works without logging in; use it to reset a password or promote an account
- Ports 8000 and 3000 are often already taken on a dev box. `PORT` works for the backend, `PORT=3001 npm run dev` for the frontend, and `BACKEND_URL` in `frontend/.env.local` must then match
- Dev servers started from an agent session die when that session ends. Run them in your own terminal, or detach with `setsid nohup`, if you want them to persist
- `scoring_history.py` uses SQLite at `backend/data/scoring_history.db` — created automatically on first write
- Frontend build requires Node 18+
