# ListingIQ — Multi-Agent Product Listing Optimization Engine

> **GRACE CodeRemLabs** — AI-powered ecommerce listing intelligence

A **10-stage agentic AI system** that benchmarks an ecommerce product listing against the **real** top 10 competitors in its subcategory, scores it across category-specific weighted dimensions, and generates optimized rewrites.

Competitors are fetched live from a marketplace API and scored on the same rubric, so the benchmark is a measured average of real listings rather than a model's estimate. Every frequency, average and rewrite score the product shows is either computed or explicitly labelled as a projection — see [Measured, Not Estimated](#measured-not-estimated).

Built with **LangGraph** orchestration, **OpenAI GPT-4o**, the **Rainforest** product API, real-time **SSE streaming**, and **LangSmith** observability. Full-stack: Python FastAPI backend + Next.js React frontend.

---

## Table of Contents

- [What It Does](#what-it-does)
- [Why It Matters](#why-it-matters)
- [Demo Stories](#demo-stories)
- [Architecture](#architecture)
- [The Pipeline Stages](#the-pipeline-stages)
- [Measured, Not Estimated](#measured-not-estimated)
- [Category-Specific Scoring Rubrics](#category-specific-scoring-rubrics)
- [Three Rewrite Strategies](#three-rewrite-strategies)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [API Endpoints](#api-endpoints)
- [SSE Streaming Protocol](#sse-streaming-protocol)
- [Observability](#observability)
- [Agentic Memory System](#agentic-memory-system)
- [Quick Start](#quick-start)
- [Demo Walkthrough](#demo-walkthrough)
- [Accounts, Access & Spend Control](#accounts-access--spend-control)
- [Measuring Scoring Quality](#measuring-scoring-quality)
- [Testing](#testing)
- [Known Limitations](#known-limitations)
- [Key Design Decisions](#key-design-decisions)
- [Environment Variables](#environment-variables)
- [Roadmap](#roadmap)

---

## What It Does

1. **Takes a product listing** — paste the copy, or just paste the URL and it reads the page
2. **Classifies the product** into a vertical/category/subcategory and loads a weighted scoring rubric
3. **Finds real competitors across the open web** — a marketplace listing, an eBay item, a brand's own store — and reads each page wherever it lives
4. **Analyzes competitive patterns** — keyword frequency, claim patterns, trust signals, structural data
5. **Scores the listing 0-10** across 9-10 category-specific dimensions with competitor benchmarks and gap analysis
6. **Generates prioritized recommendations** — specific copy to add, competitive evidence, projected score lift
7. **Produces 3 complete rewrite variants** — keyword-optimized, benefit-led, trust-forward — each with projected scores
8. **Learns from feedback** — accepted/rejected suggestions and brand guidelines persist as agentic memory

All of this executes as a **LangGraph StateGraph** pipeline of 10 stages, streamed to the browser in real time over SSE.

It is **not tied to one marketplace.** Competitors are discovered by search rather than through a single storefront's API, so a Shopify seller is benchmarked against the stores they actually compete with — and every competitor carries the platform it was found on.

---

## Why It Matters

| Problem | ListingIQ Solution |
|---------|-------------------|
| **80% of Amazon listings underperform** — sellers write titles and bullets based on gut feeling, not data | AI scores every dimension against the top 10, showing exactly where you're losing |
| **Hiring a listing optimization consultant costs $500-2,000 per ASIN** and takes 1-2 weeks | ListingIQ delivers the same analysis in ~60 seconds for pennies in API cost |
| **Sellers can't see their own blind spots** — they don't know what "good" looks like in their subcategory | Competitive intelligence shows what 9/10 top sellers do that you don't |
| **Generic listing tools give vague advice** like "add more keywords" | ListingIQ gives **exact copy to paste** — e.g. "Add to bullet: 'Chelated magnesium glycinate — absorbed 2x better than oxide with zero digestive discomfort'" |
| **Each product category has different success criteria** — what works for supplements doesn't work for skincare | Category-specific rubrics with weighted dimensions tuned per subcategory |

**Target market:** 2M+ active Amazon sellers, Shopify brands, DTC brands, Amazon agencies managing portfolios of 100-10,000+ ASINs.

---

## Demo Stories

### Story 1: "The Lazy Listing" — Magnesium Supplement

**The Setup:** A new supplement brand "HealthPlus" launches a Magnesium product on Amazon. They write the bare minimum listing because they don't know what matters in the supplements category.

**Their listing:**
- Title: *"Magnesium 500mg 120 Capsules"*
- Bullets: "500mg per capsule", "120 capsules per bottle", "Easy to swallow"
- Description: "Magnesium supplement capsules. Take daily for health support."

**What ListingIQ reveals:**
- **Overall score: 1.3/10** (Percentile: P10 — worse than 90% of competitors)
- Missing form specificity (glycinate vs oxide vs citrate — 9/10 competitors explain this)
- Zero trust signals (no third-party testing, no GMP, no certifications)
- No dosage science (competitors cite "clinically studied 200mg elemental magnesium")
- No bioavailability claims (top sellers all mention chelated form and absorption rates)
- No target audience (competitors mention "women 30+", "athletes", "sleep support")

**The payoff:** ListingIQ generates 3 complete rewrites. The **trust-forward variant** scores 8.5/10 — a **7.2 point jump** — with specific bullets like:
> *"CHELATED MAGNESIUM GLYCINATE — The most bioavailable form, absorbed 2x better than magnesium oxide. Gentle on the stomach with zero digestive discomfort, even at therapeutic doses."*

**Investor takeaway:** This is the difference between page 5 and page 1 on Amazon. A $0.03 API call replaces a $1,500 consultant.

---

### Story 2: "The Generic Serum" — Vitamin C Skincare

**The Setup:** "GlowSkin" is a DTC skincare brand that wrote their Amazon listing like a Shopify product page — vague benefits, no specificity for the Amazon algorithm.

**Their listing:**
- Title: *"Vitamin C Serum for Face Anti Aging 30ml"*
- Bullets: "Anti aging formula", "30ml bottle", "For all skin types"
- Description: "Face serum with vitamin C. Helps with anti aging and skin brightening."

**What ListingIQ reveals:**
- **Different rubric loads** — skincare dimensions include "Active Concentration Transparency", "Clinical Evidence", "Ingredient Synergy", "Texture & Sensorial Description"
- Missing concentration (10%? 15%? 20%? — 8/10 competitors state exact percentage)
- No ingredient form specified (L-Ascorbic Acid vs Sodium Ascorbyl Phosphate — matters for efficacy claims)
- No complementary ingredients mentioned (competitors list Hyaluronic Acid + Vitamin E + Ferulic Acid)
- Zero sensorial language ("lightweight", "fast-absorbing", "non-greasy" — used by 7/10 competitors)
- No packaging/stability claims (dark glass bottle, airless pump — trust signals in skincare)

**The payoff:** The **benefit-led variant** rewrites the title to:
> *"GlowSkin Vitamin C Serum 20% L-Ascorbic Acid with Hyaluronic Acid & Vitamin E — Brightening Anti-Aging Face Serum for Dark Spots, Fine Lines & Uneven Skin Tone — 30ml Glass Dropper"*

**Investor takeaway:** ListingIQ understands that different categories need different criteria. A supplement rubric scores "dosage science" and "third-party testing" — a skincare rubric scores "active concentration" and "sensorial description". This isn't a generic keyword tool.

---

### Story 3: "The Good-Not-Great" — Creatine Powder

**The Setup:** "NutriForce" is a mid-tier supplement brand with a well-written creatine listing. They've done their homework — 5 solid bullets, third-party testing mentioned, clean formula claims. But they're stuck at position #15 in search and can't crack the top 10.

**Their listing:**
- Title: *"Creatine Monohydrate Powder 5000mg - Micronized Unflavored 300g (60 Servings)"*
- 5 detailed bullets covering purity, servings, testing, versatility, clean formula
- Solid description mentioning muscle strength and performance

**What ListingIQ reveals:**
- **Overall score: 5.8/10** (Percentile: P45 — middle of the pack)
- Good on testing and purity (7.5/10) — but that's table stakes, all top 10 have it
- Weak on **outcome specificity** (4.0/10) — doesn't quantify results ("increases lean mass by 5-10%" like top competitors do)
- Weak on **use case guidance** (3.5/10) — no loading phase, no timing advice, no stack suggestions
- Missing **social proof integration** (2.0/10) — no mention of "trusted by 50,000+ athletes" or review highlights
- The title is good but the **keyword order is suboptimal** — "creatine monohydrate" should lead for Amazon SEO

**The payoff:** Quick wins identified — 3 small copy changes that lift the score from 5.8 to 7.4 without a full rewrite. The recommendation engine shows: *"8/10 top competitors include specific performance metrics. Add: 'Clinically proven to increase strength output by 5-15% in the first 4 weeks'"*

**Investor takeaway:** ListingIQ doesn't just help bad listings become average — it helps good listings become great. The value applies across the entire seller spectrum. Even sophisticated brands have blind spots.

---

## Architecture

### 10-Stage Pipeline (Sequential LangGraph StateGraph)

```
                    ┌─────────────────────────┐
                    │   START (Listing Input)  │
                    └────────────┬─────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │   1. Input Parser        │  Extract entities, ingredients, certifications, claims
                    └────────────┬─────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │   2. Category Classifier │  Identify vertical/subcategory, load scoring rubric
                    └────────────┬─────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │   3. Competitor Scout    │  Fetch 10 REAL competitor listings (marketplace API)
                    └────────────┬─────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │   4. Competitor Analyzer │  Keyword patterns, claim frequency, trust signals
                    └────────────┬─────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │   5. Competitor Scorer   │  Score all 10 competitors -> the MEASURED benchmark
                    └────────────┬─────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │   6. Listing Analyzer    │  Per-dimension extraction: present/missing/evidence
                    └────────────┬─────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │   7. Benchmark Scorer    │  Score 0-10 per dimension vs competitor benchmarks
                    └────────────┬─────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │   8. Recommendation      │  Prioritized improvements with specific copy
                    │      Engine              │
                    └────────────┬─────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │   9. Rewrite Generator   │  3 complete listing variants
                    └────────────┬─────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │  10. Rewrite Verifier    │  Re-score each variant — measured, not self-reported
                    └────────────┬─────────────┘
                                 ▼
                            ┌─────────┐
                            │   END   │
                            └─────────┘
```

All stages always run. No conditional branches. Each stage uses GPT-4o with strict structured outputs — except the arithmetic, which is done in Python.

---

### The Pipeline Stages

| # | Stage | File | What It Does | Key Output |
|---|-------|------|-------------|------------|
| 1 | **Input Parser** | `input_parser.py` | Extracts entities, ingredients, certifications, dosage, claims, format type from raw listing text | `ParsedListing` with `ExtractedEntities` |
| 2 | **Category Classifier** | `category_classifier.py` | Classifies into vertical/category/subcategory; loads a pre-built rubric or generates one | `CategoryClassification` + `ScoringRubric` |
| 3 | **Competitor Scout** | `competitor_scout.py` → `providers/` | Finds **real** competitors by web search across any platform, deduplicates them, and reads each product page. Every listing carries the platform it was found on | `CompetitorScoutResult` (listings + `platform_breakdown` + `data_source`) |
| 4 | **Competitor Analyzer** | `competitor_analyzer.py` | Identifies keywords, claims and trust signals and attributes them to specific competitors. **Frequencies and structural stats are counted in Python** | `CompetitorAnalysis` |
| 5 | **Competitor Scorer** | `competitor_scorer.py` | Scores every readable competitor on the same rubric in one call, then aggregates in Python into **two cohorts** — same-platform and whole-category | `CompetitorBenchmarkSet` (per-dimension mean/best/worst/n) |
| 6 | **Listing Analyzer** | `listing_analyzer.py` | Evaluates the user's listing per rubric dimension: present/missing, evidence quotes, completeness | `ListingAnalysis` |
| 7 | **Benchmark Scorer** | `benchmark_scorer.py` | Scores the listing 0-10 per dimension; gaps and both percentiles come from the **measured** benchmark, and the result records which cohort the headline used | `ListingScore` with weighted overall, `percentile_basis` + gap analysis |
| 8 | **Recommendation Engine** | `recommendation_engine.py` | Prioritized recommendations with specific copy and competitive evidence | `RecommendationResult` (quick wins + strategic moves) |
| 9 | **Rewrite Generator** | `rewrite_generator.py` | Creates 3 complete listing variants: keyword-optimized, benefit-led, trust-forward — shaped to the target platform's own format norms | `RewriteResult` (3 variants) |
| 10 | **Rewrite Verifier** | `rewrite_verifier.py` | Re-scores each variant through the same scorer used on competitors, so its score is measured | `RewriteResult` with `measured_score` per variant |

---

## Measured, Not Estimated

The product sells a number, so every number it shows is either **computed from real data** or **explicitly labelled as a projection**. Each row below replaced a model estimate that was previously presented to customers as fact.

| Number | Before | Now |
|--------|--------|-----|
| Competitor listings | Recalled by GPT-4o — plausible brands, invented prices | Found by web search and read from their own pages, with a clickable URL and a platform per competitor |
| Which platform a competitor is on | Assumed to be Amazon — an unrecognised platform was silently searched on Amazon anyway | Detected from the URL; an unknown domain is a brand site, never a marketplace |
| Competitor price and rating | Invented where absent | Taken from search results where published, left **empty** where not — an unread rating is not a rating of zero |
| Copy for a page we could not read | Scored as though it were the seller's listing | Excluded from the benchmark and labelled, so a failed read is not graded as a weak listing |
| Competitor average per dimension | *"What would the average top-10 competitor score?"* — a guess | Every fetched competitor scored on the same rubric, averaged in Python |
| Gap vs competitors | Derived from that guess | Measured average minus your score |
| Percentile | Typed by the model | Counted — how many scored competitors you actually beat |
| *"8/10 competitors mention X"* | Model's impression | Counted by word-boundary phrase matching, with the brands named |
| Avg title length, bullet count, emoji use | Model's estimate | Exact arithmetic over the listing text |
| Rewrite score | The generator grading its own output | Re-scored through the same scorer used on the competitors |

**The rule:** the model proposes and attributes — which keywords matter, which competitors make a claim. Python counts. A model's estimate of a count it could not verify is a fabricated statistic, however plausible, and these numbers are quoted to customers as evidence.

### What measuring revealed

Three findings that only appeared once the numbers were real:

- **The rewrite generator overrates itself by ~4 points.** Claimed 8.5 / 9.0 / 9.2; measured 4.6 / 4.5 / 5.0. The rewrites genuinely improve a listing — 3.1 → 5.0 — but do not beat the competitor mean of 6.5, which "9.2" strongly implied.
- **A "top 10" is often 6 brands.** Marketplaces list sizes and flavours as separate ASINs; one creatine brand held 3 of 10 slots and dragged the average toward itself. Deduplication now happens before paying for product detail.
- **Most competitors have no description.** Only 4 of 10 real listings carried a description block — the rest use A+ image content. Averaging the empty ones made competitors look like they wrote short copy.
- **One number cannot describe competitors from different platforms.** A 200-character keyword-stacked marketplace title and a brand site's 40-character product name are both good listings, by different rules. Pooled into one average, the mean measures whichever house style dominated the search — so the score is reported against two cohorts instead of one.

### Two cohorts, not one average

The headline percentile is measured against competitors on **your own platform**. A second, wider percentile covers every competitor found. Both are shown:

> *62nd percentile among Amazon sellers &middot; 31st across the category*

Both come from a single scoring call — the second cohort is arithmetic over the same scored rows, so it costs nothing extra. When too few competitors are found on your platform to form a cohort, the headline falls back to the wider one **and says so**, rather than quoting a precise-looking percentile computed over two listings.

### Honest fallback

When the live provider is unavailable the run still completes, but the result is labelled `llm_knowledge`, the UI shows an amber *"AI-estimated competitors — not live marketplace data"* banner next to the score, and **the estimated data is never cached** — so an outage cannot leave estimates masquerading as real once it recovers. That guard now covers the *benchmark computed from* those listings too, which previously slipped through.

Degrading is not the same as estimating, and the two are kept apart. If competitor pages cannot be read but the search worked, the result stays labelled as observed data and reports what was thin — search results are still something we saw. Relabelling them "AI-estimated" would be a lie in the opposite direction.

---

## Category-Specific Scoring Rubrics

ListingIQ uses **weighted scoring rubrics** tailored to each product subcategory. Dimensions and their weights differ based on what matters in that specific market.

### Pre-Built Rubrics (10 subcategories)

**Supplements & Nutraceuticals (5):**
| Subcategory | Dimensions | Example Dimensions |
|-------------|------------|-------------------|
| Magnesium Glycinate | 9 | Form Specificity, Bioavailability Claims, Dosage Science, Third-Party Testing |
| Creatine Monohydrate | 9 | Purity Claims, Serving Flexibility, Performance Metrics, Use Case Guidance |
| Probiotic Capsules | 10 | CFU Count & Strain Transparency, Survivability Claims, Condition-Specific Benefits |
| Vitamin D3 + K2 | 10 | Synergy Explanation, Form Specificity, Dosage Precision |
| Collagen Peptides | 10 | Source & Type Transparency, Bioavailability Evidence, Taste & Mixability |

**Skincare & Beauty (5):**
| Subcategory | Dimensions | Example Dimensions |
|-------------|------------|-------------------|
| Vitamin C Serum | 10 | Active Concentration Transparency, Ingredient Form, Clinical Evidence, Sensorial Description |
| Retinol Serum | 10 | Retinol Concentration & Form, Irritation Mitigation, Before/After Expectations |
| Hyaluronic Acid Serum | 10 | Molecular Weight Diversity, Hydration Science, Layering Compatibility |
| Sunscreen SPF 50 | 10 | UV Filter Transparency, Cosmetic Elegance, Reef Safety Claims |
| Niacinamide Serum | 10 | Concentration Disclosure, Multi-Concern Positioning, Compatibility Claims |

**Fallback:** For unrecognized subcategories, the Category Classifier agent generates a custom rubric via LLM using 9 universal dimensions.

---

## Three Rewrite Strategies

Each analysis produces 3 complete listing variants, each optimized for a different buyer psychology:

| Variant | Strategy | Best For |
|---------|----------|----------|
| **Keyword-Optimized** | Front-loads high-volume search terms. Amazon SEO structure: brand + key feature + product type + size. Every bullet contains a search keyword. | Amazon sellers focused on search ranking and discoverability |
| **Benefit-Led** | Leads with strongest outcome claims and aspirational language. Focuses on what the product does for the buyer. Emotional triggers. | Shopify/DTC brands, brand storytelling, social media traffic |
| **Trust-Forward** | Leads with certifications, third-party testing, clinical evidence, and social proof. Builds credibility before benefits. | Supplements and skincare where trust is the primary purchase barrier |

Each variant includes: complete title + 5-6 bullet points + 2-3 paragraph description + projected overall score + list of key changes from original.

---

## Tech Stack

### Backend

| Component | Technology | Version |
|-----------|-----------|---------|
| Runtime | Python | 3.12 |
| Web Framework | FastAPI + Uvicorn | 0.115.6 |
| Agent Orchestration | **LangGraph** (StateGraph) | 1.1.6 |
| LLM | OpenAI GPT-4o via `openai` SDK (async) | 2.31.0 |
| LLM Integration | `langchain-openai` + `langchain-core` | 1.1.12 / 1.2.28 |
| Streaming | Server-Sent Events via `sse-starlette` | 3.0.3 |
| Validation | Pydantic v2 | 2.12.3 |
| Observability | **LangSmith** (auto-tracing via env vars) | 0.7.30 |
| Persistence | SQLite via `aiosqlite` | 0.22.1 |

### Frontend

| Component | Technology | Version |
|-----------|-----------|---------|
| Framework | Next.js (App Router) | 15.1.0 |
| UI Library | React | 19.0.0 |
| Styling | Tailwind CSS | 4.0.0 |
| Charts | Recharts (Radar chart) | 2.15.0 |
| Streaming | Native `ReadableStream` SSE client | -- |
| Icons | Lucide React | 0.468.0 |
| Type System | TypeScript | 5.7.2 |

---

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
│   ├── agents/
│   │   ├── llm_client.py             # structured_completion(): retries, timeout, usage
│   │   ├── graph_state.py            # ListingIQState TypedDict
│   │   ├── orchestrator.py           # LangGraph StateGraph build + compile
│   │   ├── input_parser.py           # Agent 1: entity extraction
│   │   ├── category_classifier.py    # Agent 2: subcategory + rubric loading
│   │   ├── competitor_scout.py       # Agent 3: 10 real competitor listings via providers/
│   │   ├── competitor_analyzer.py    # Agent 4: keyword/claim/trust patterns
│   │   ├── listing_analyzer.py       # Agent 5: per-dimension evaluation
│   │   ├── benchmark_scorer.py       # Agent 6: weighted scoring + gaps
│   │   ├── recommendation_engine.py  # Agent 7: quick wins + strategic moves
│   │   ├── rewrite_generator.py      # Agent 8: 3 rewrite variants
│   │   └── feedback_memory.py        # Brand memory + feedback store (not yet wired in)
│   ├── data/
│   │   ├── auth.db                   # Accounts, sessions, keys, daily usage
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

---

## API Endpoints

All `/api` routes require an authenticated caller — either a session cookie from
logging in, or an `X-API-Key` header for programmatic clients. `/health` is public.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check — `{"engine": "listingiq"}` (no auth) |
| `POST` | `/api/auth/login` | Exchange email + password for a session |
| `POST` | `/api/auth/logout` | End the current session |
| `GET` | `/api/auth/me` | Current caller, role, limits and usage |
| `GET` | `/api/admin/accounts` | List accounts with limits and usage *(admin)* |
| `POST` | `/api/admin/accounts` | Create an account *(admin)* |
| `PATCH` | `/api/admin/accounts/{account_id}` | Change limits, role or active state *(admin)* |
| `POST` | `/api/admin/accounts/{account_id}/password` | Set a password, revoking sessions *(admin)* |
| `GET` | `/api/admin/keys` | List API keys and their owners *(admin)* |
| `POST` | `/api/admin/keys` | Issue a key under an account *(admin)* |
| `DELETE` | `/api/admin/keys/{key_id}` | Revoke a key *(admin)* |
| `GET` | `/api/usage` | Calling account's token spend and quota for today |
| `POST` | `/api/extract` | Read a product page into a listing, so it need not be retyped |
| `POST` | `/api/pipeline` | Run the full pipeline (JSON response) |
| `POST` | `/api/pipeline/stream` | Run pipeline with **SSE streaming** (real-time node progress) |
| `GET` | `/api/rubrics` | List available pre-built scoring rubrics |
| `POST` | `/api/feedback` | Submit human feedback to memory |
| `GET` | `/api/memory/{brand_name}` | Retrieve cached guidelines |
| `POST` | `/api/memory/guideline` | Add a brand guideline |
| `GET` | `/api/feedback/log` | View feedback audit log |
| `GET` | `/api/history/{brand_name}` | Scoring history for a brand |

### Example Request

```bash
curl -X POST http://localhost:8000/api/pipeline/stream \
  -H "Content-Type: application/json" \
  -d '{
    "listing_input": {
      "product_title": "Magnesium 500mg 120 Capsules",
      "product_description": "Magnesium supplement capsules. Take daily for health support.",
      "bullet_points": ["500mg per capsule", "120 capsules per bottle", "Easy to swallow"],
      "brand_name": "HealthPlus",
      "platform": "amazon",
      "target_audience": ""
    },
    "session_id": "demo_1"
  }'
```

---

## SSE Streaming Protocol

The `/api/pipeline/stream` endpoint emits events as each agent completes:

```
event: node_complete
data: {"node": "input_parser", "duration_ms": 2221}

event: node_complete
data: {"node": "category_classifier", "duration_ms": 1779}

event: node_complete
data: {"node": "competitor_scout", "duration_ms": 12905}

event: node_complete
data: {"node": "competitor_analyzer", "duration_ms": 4300}

event: node_complete
data: {"node": "listing_analyzer", "duration_ms": 5848}

event: node_complete
data: {"node": "benchmark_scorer", "duration_ms": 9438}

event: node_complete
data: {"node": "recommendation_engine", "duration_ms": 11806}

event: node_complete
data: {"node": "rewrite_generator", "duration_ms": 14534}

event: result
data: { full FullPipelineResponse JSON }
```

The frontend `LoadingOverlay` shows live progress — each agent lights up with a checkmark as it completes (~60s total).

---

## Observability

### Structured Terminal Logging

```
21:28:46 │ INFO  │ listingiq.agent.input_parser        │ ⚙ input_parser_node EXIT  2.2s  product_type=Magnesium Supplement
21:28:48 │ INFO  │ listingiq.rubrics                   │ Loaded rubric for 'Magnesium Glycinate' — 9 dimensions
21:29:01 │ INFO  │ listingiq.agent.competitor_scout     │ ⚙ competitor_scout_node EXIT  12.9s  10 listings found
21:29:05 │ INFO  │ listingiq.agent.competitor_analyzer  │ ⚙ competitor_analyzer_node EXIT  4.3s  keywords=3 claims=2
21:29:20 │ INFO  │ listingiq.agent.benchmark_scorer     │ ⚙ benchmark_scorer_node EXIT  9.4s  overall=1.3  percentile=10
21:29:47 │ INFO  │ listingiq.api                        │ ◀ SSE pipeline DONE   62.8s  nodes=8
```

### LangSmith Integration

Set 3 env vars for full production observability — zero code changes:

```env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=lsv2_pt_your_key_here
LANGCHAIN_PROJECT=listingiq
```

Captures: full node waterfall, every LLM call with prompts/completions/tokens/costs, state transitions, and errors.

---

## Agentic Memory System

| Source | How It's Created | Confidence |
|--------|-----------------|------------|
| `brand_guideline` | User manually adds (e.g. *"Never use the word cheap"*) | 1.0 |
| `human_feedback` | User rejects a suggestion with a reason | 0.9 |
| `learned_preference` | User accepts a suggestion (auto-captured) | 0.8 |

> **Status: not wired in.** The API endpoints, models and store exist, and the
> graph state declares a `memory_context` field — but no agent reads it, so
> entries are never injected into prompts and have no effect on output. Storage
> is also a module-level dict that resets on restart, and the frontend passes an
> empty list. Treat this as a designed-but-unimplemented feature.
>
> To finish it: read `memory_context` in `recommendation_engine` and
> `rewrite_generator`, populate it in the graph before those nodes run, and move
> the store into the SQLite database alongside accounts.

---

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- An OpenAI API key with GPT-4o access

### 1. Backend

Create the first administrator — the whole app is behind a login:

```bash
python manage_accounts.py create-admin you@example.com   # prompts for a password
```

Every other account is created from the admin panel once you are signed in.


```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # macOS/Linux
pip install -r requirements.txt
```

Create `backend/.env`:
```env
OPENAI_API_KEY=sk-proj-your-key-here
OPENAI_MODEL=gpt-4o
CORS_ORIGINS=http://localhost:3000
```

Start the server:
```bash
python3 main.py
```

Backend runs at **http://localhost:8000**.

### 2. Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local    # set BACKEND_URL if the backend is not on :8000
npm run dev
```

Frontend runs at **http://localhost:3000**. Sign in with the admin account you just created.

No credential ever reaches the browser: logging in sets an **httpOnly** session cookie, and the Next proxy in `src/app/api/[...path]/route.ts` forwards that session to the backend on every call.

> **Ports.** 8000 and 3000 are commonly taken. Use `PORT=8001 python main.py` and `PORT=3001 npm run dev`, and set `BACKEND_URL` in `frontend/.env.local` to match.

### 3. Use It

1. Open http://localhost:3000 and sign in
2. Select a demo preset ("Weak Magnesium", "Weak Vitamin C Serum", or "Moderate Creatine")
3. Click **Analyze Listing**
4. Watch all 10 stages execute in real time via SSE streaming
5. Explore: scores, competitors, analysis, recommendations, rewrites
6. Copy optimized copy to clipboard with one click

---

## Demo Walkthrough

### Recommended Demo Flow (for investors)

**Step 1 — Show the problem (30 seconds)**
> Select the "Weak Magnesium" preset. Point out: this is a real listing you'd see from a new seller — bare minimum title, 3 generic bullets, no description.

**Step 2 — Run the pipeline (60 seconds)**
> Click "Analyze Listing". The loading overlay shows 8 AI agents working in sequence. Each agent has a specific role — parsing, classifying, scouting competitors, analyzing patterns, scoring, recommending, rewriting.

**Step 3 — Show the score (15 seconds)**
> Score appears: **1.3/10, Percentile P10**. This listing is worse than 90% of its competitors. The system auto-detected "Magnesium Glycinate" subcategory and loaded a 9-dimension weighted rubric.

**Step 4 — Show competitive intelligence (30 seconds)**
> Scroll to competitor cards — 10 real competitor listings with brands, prices, ratings, badges. Then the analysis panel: "9/10 competitors mention chelated form", "7/10 cite bioavailability", "6/10 include third-party testing badges".

**Step 5 — Show the gap (30 seconds)**
> Score matrix: per-dimension scores with competitor averages and gaps. Radar chart: their listing (tiny polygon) vs competitor average (large polygon). Visual and quantitative proof of where they're losing.

**Step 6 — Show the fix (30 seconds)**
> Recommendations panel: Quick Wins tab shows 2-3 changes with specific copy. "Add to bullet: 'Chelated magnesium glycinate — absorbed 2x better than oxide'". Each recommendation shows current score, projected score, and competitive evidence.

**Step 7 — Show the rewrites (30 seconds)**
> Rewrite panel: 3 complete variants. Trust-Forward variant scores **8.5/10** (from 1.3). Show the title transformation, new bullet points, full description. Click "Copy" to grab it.

**Step 8 — Show it works for another category (60 seconds)**
> Run the "Weak Vitamin C Serum" preset. Different category, different rubric (skincare dimensions), different competitors, different recommendations. Same engine. Proves category adaptability.

**Total demo time: ~4-5 minutes**

---

## Accounts, Access & Spend Control

The whole application is behind a login. An **account** owns its limits; credentials are just ways to prove you are that account.

### Roles

| Role | Can |
|------|-----|
| `member` | Sign in, analyse listings, spend their own budget |
| `admin` | All of the above, plus the `/admin` panel: create accounts, set limits, promote, disable, reset passwords, issue API keys |

### Admin panel

At `/admin`, visible in the header for admins only:

- **Create accounts** — email, password, role, and all three limits
- **Edit limits inline** — a Save button appears on any row you change
- **Promote / demote, disable / enable, set passwords**
- **Live usage** — tokens used today against each account's budget, with a run count

### Limits

Set per account and applied to everything that account does, browser or API:

| Limit | Default | Guards against |
|-------|---------|----------------|
| Requests per minute | 10 | looping an endpoint |
| Concurrent runs | 2 | many parallel 60-second pipelines |
| Tokens per day | 2,000,000 | sustained spend |
| Service-wide tokens per day | 20,000,000 | one account draining the provider account |

Quotas are counted in **tokens, not dollars**, so there is no pricing table to go stale. Set `OPENAI_COST_PER_1M_INPUT` / `OPENAI_COST_PER_1M_OUTPUT` to also see runs costed in your logs and on `/api/usage`.

### API keys

For scripts and CI. Issued **under an account** from the admin panel or the CLI, and they spend that account's budget — so web and programmatic usage share one ledger rather than two.

```bash
curl -H "X-API-Key: liq_live_..." http://localhost:8000/api/usage
```

Disabling an account stops its sessions *and* its keys on the next request.

### How credentials are stored

- **Passwords** — `hashlib.scrypt`, memory-hard, per-password salt, constant-time verification. Minimum 10 characters.
- **Sessions** — opaque random tokens kept as SHA-256 hashes, not JWTs, so revocation is immediate and there is no signing algorithm to misconfigure. Seven-day default lifetime.
- **API keys** — SHA-256 hashes. Shown once at creation and never recoverable.

Login returns the same message for a wrong password, an unknown email and a disabled account, so it cannot be used to find out which email addresses exist. The last active admin cannot be demoted or disabled.

---

## Measuring Scoring Quality

The product's core claim is a number, so that number is tested. `backend/evals/` runs a fixed set of 12 listings (4 each at weak / moderate / strong, across 10 subcategories) repeatedly and gates on four properties:

- **Stability** — the same listing must score the same on repeat runs (sd ≤ 0.75 overall, ≤ 1.50 per dimension)
- **Discrimination** — rank correlation between human quality tier and mean score must be ≥ 0.70
- **Classification consistency** — repeats must load the same rubric, or the scores were never comparable
- **Percentile coherence** — reported as a diagnostic, since `percentile` is model-supplied rather than derived

```bash
cd backend && python evals/run_eval.py --mode scorer --repeats 5
```

This is the only suite that calls the real model; it prints a cost estimate and waits for confirmation. See CLAUDE.md for the two modes and what each gate means when it fails.

### Measured results

12 listings × 5 repeats, scorer mode — 60 observations, ~157k tokens, 208 seconds:

| Gate | Result | |
|------|--------|--|
| Overall score stability | worst sd **0.29** (limit 0.75) | PASS |
| Classification consistency | **100%** on all 12 | PASS |
| Tier discrimination | spearman **0.859** (limit 0.70) | PASS |
| Per-dimension stability | 2 dimensions over sd 1.50 | FAIL |
| Percentile coherence | spearman **0.957** | diagnostic |

Five of twelve listings scored *identically* across all five runs. Scoring is far more repeatable than expected.

**What the harness found, and what fixing it proved.** `Certifications` appeared in four rubrics with two different criteria styles — a natural experiment:

| Criteria style | mean sd |
|----------------|---------|
| `"0: None. 5: Some. 10: Comprehensive."` | 1.10 |
| `"0: None. 3: 1 cert. 5: 2-3 certs. 7: … 10: …"` | 0.00 |

Rewriting the three vague ones in the anchored style dropped `Certifications` from **0.66 → 0.27** mean sd and from 2 listings over the gate to **0**. Three JSON lines, no code. **Vague scoring criteria are the main source of score noise; anchored, countable criteria are effectively deterministic.**

### Known limitations

- **`Shelf Stability` still fails** (sd 2.74). It already *has* anchored criteria and is being over-scored anyway — "no refrigeration needed" is a documented 5 and scores 7–9. Anchoring harder will not fix this one.
- **Tier bands overlap.** Strong listings span 5.1–8.3 and moderates 3.3–6.0, so rank correlation passes while you still cannot say "a score above X means a good listing". The gate is not sensitive to this.
- **These figures are a floor.** Scorer mode reuses one competitor set per listing, so it measures the scorer alone. End-to-end variance including competitor-scout churn needs `--mode full`.

## Testing

Eighteen suites, all offline. None call OpenAI, none touch your database — each uses a
temporary one.

```bash
cd backend
python tests/check_schemas.py       # response models -> valid strict JSON schema (auto-discovered)
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

The eval harness (`evals/run_eval.py`) is separate and **does** call the real
model — a stubbed model would only measure the stub. It prints a cost estimate
and waits for confirmation.

Frontend type checking:

```bash
cd frontend && npx tsc --noEmit
```

---

## Known Limitations

Honest state of things, so nobody is surprised in production. Operational
procedures for all of these live in [docs/OPERATIONS.md](docs/OPERATIONS.md).

| Area | Status |
|------|--------|
| **Competitor descriptions** | Many real marketplace listings have no description block — their copy lives in A+ content, which is images and not text-extractable. Description-related dimensions therefore compare against a small sample. Reported in `provider_note` rather than hidden. |
| **Pages we cannot read** | Some storefronts defeat extraction. Those competitors are still shown, labelled, and **excluded from the benchmark** — but a run where many pages fail produces a thinner cohort than the competitor count suggests. Watch the `n` on each dimension. |
| **Prices on non-marketplace competitors** | Price and rating come from Google Shopping, whose links are search-engine interstitials rather than merchant URLs. They are matched onto real product pages by title, so a competitor whose title does not match cleanly is shown without a price. Shown as blank, never invented. |
| **Amazon needs its own reader** | Amazon publishes no structured product markup and returns mostly navigation, so it is read through the Rainforest product API. Without a Rainforest key it falls back to generic extraction, which produces noticeably worse bullets on Amazon specifically. |
| **Cross-platform duplicates** | The same product on two storefronts is matched by title-token overlap, which is a heuristic. It deliberately under-collapses: a missed duplicate slightly overstates the set, while a wrong merge would delete a real competitor. The count is reported in `provider_note`. |
| **Structural targets on a mixed cohort** | `avg_bullet_count` and similar are computed across every competitor, so a cohort that is half brand-site pages reports structural norms that mix two house styles. The rewrite generator is given the target platform's own format profile, which is the number that should dominate — but the mixed average is still in the prompt. |
| **Shopify / brand-site cohorts** | "Shopify" is not one domain, so a search cannot be scoped to it the way it can to a marketplace. A seller on their own store will often fall back to the whole-category cohort — correctly labelled, but a weaker comparison. |
| **Rewrite quality** | Measured rewrite scores land well below the generator's own projection (~+4 points of optimism, consistently). The rewrites improve a listing materially but do not yet beat the competitor mean. |
| **Scoring evals after prompt edits** | The competitive-context denominators in the scorer prompt changed from a hardcoded `/10` to the real cohort size. `evals/run_eval.py --mode scorer` has not been re-run since (it calls the paid model), so scoring stability across that change is unverified. |
| **Agentic memory** | Endpoints and models exist; no agent reads them. See the note in that section. |
| **Login rate limiting** | `/api/auth/login` is not rate limited and is brute-forceable. Needs an IP-keyed limiter before anything is internet-facing. |
| **Password self-service** | Only an admin can set a password; there is no change-your-own-password flow and no reset email. |
| **Rate & concurrency limits** | Held in process memory, so they are per-instance. A multi-instance deploy multiplies them by instance count until they move to Redis. |
| **Storage** | SQLite, opening a connection per request. Fine for a single instance; needs Postgres to scale out. |
| **Checkpointing** | `SQLITE_CHECKPOINT_PATH` is configured but unused — a dropped connection loses a 60-second run rather than resuming it. |
| **Score bands** | Strong and moderate listings overlap (5.1–8.3 vs 3.3–6.0), so a score cannot yet be read as an absolute quality grade. |
| **Dependencies** | `next@15.1.0` has a published advisory (CVE-2025-66478) and should be upgraded. |

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **LangGraph StateGraph** | Declarative agent orchestration with built-in state management, streaming, and LangSmith tracing |
| **Category-specific rubrics** | Supplements and skincare have fundamentally different success criteria — generic scoring is useless |
| **10 competitors (not 3)** | Statistically meaningful benchmarks require a larger sample; 10 covers the full first page of Amazon search |
| **3 rewrite variants** | Different channels need different approaches — Amazon SEO vs DTC storytelling vs trust-building |
| **Live competitor data, with honest fallback** | Benchmarking against invented competitors is not defensible to a paying customer. When the provider is down the run still completes, but the data is labelled AI-estimated and never cached |
| **The model never does arithmetic** | It proposes and attributes; Python counts. A model's estimate of a count it could not verify is a fabricated statistic, and these numbers are quoted to customers as evidence |
| **Rewrites are re-scored, not self-reported** | The generator overrated its own output by ~4 points when measured. Selling that number would not have survived a customer re-running their own rewrite |
| **Sequential pipeline** | Reliable execution without LangGraph fan-in complexity; ~60s total is acceptable for the value delivered |
| **SSE over WebSockets** | Simpler protocol for unidirectional streaming; no handshake overhead |
| **GPT-4o for all agents** | Best quality; no cost optimization — performance is the priority at this stage |
| **Specific copy in recommendations** | "Add more keywords" is useless advice; "Add this exact bullet" is actionable and demonstrates AI value |
| **Eval gates on discrimination, not just stability** | A perfectly repeatable scorer that cannot rank a strong listing above a weak one is still broken, so the two are measured independently |
| **Quotas in tokens, not dollars** | No hardcoded pricing table to go stale; set the cost env vars for dollar reporting on top |
| **Limits belong to accounts, not credentials** | A customer's browser session and their API keys draw on one budget, so there is one place to change limits and one usage ledger |
| **Opaque session tokens, not JWTs** | Revocation is immediate, there is no signing algorithm to misconfigure, and the token carries no readable claims |
| **`hashlib.scrypt` for passwords** | Memory-hard and in the standard library — no new dependency and no hand-rolled crypto |

---

## Environment Variables

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `OPENAI_API_KEY` | -- | **Yes** | OpenAI API key with GPT-4o access |
| `AUTH_ENABLED` | `true` | No | Set `false` to open every route — local dev only |
| `HOST` | `0.0.0.0` | No | Dev server bind address |
| `PORT` | `8000` | No | Dev server port; deployment platforms usually inject this |
| `SESSION_TTL_HOURS` | `168` | No | How long a browser login stays valid (7 days) |
| `AUTH_DB_PATH` | `data/auth.db` | No | Accounts, sessions, keys and usage |
| `DEFAULT_RPM_LIMIT` | `10` | No | Requests per minute for a new account |
| `DEFAULT_MAX_CONCURRENT` | `2` | No | Concurrent pipeline runs per account |
| `DEFAULT_DAILY_TOKEN_LIMIT` | `2000000` | No | Tokens per account per UTC day |
| `GLOBAL_DAILY_TOKEN_LIMIT` | `20000000` | No | Service-wide daily token circuit breaker |
| `OPENAI_COST_PER_1M_INPUT` | `0` | No | For cost reporting only; quotas are in tokens |
| `OPENAI_COST_PER_1M_OUTPUT` | `0` | No | For cost reporting only; quotas are in tokens |
| `COMPETITOR_PROVIDER` | `web` | **Production: `web`** | `web` = open-web discovery on any platform; `rainforest` = Amazon only; `llm` = estimates, development only |
| `SERPER_API_KEY` | -- | With `web` | Discovery — finds who is selling the product, and where. Sent as a header |
| `FIRECRAWL_API_KEY` | -- | With `web` | Extraction — reads each competitor's page, and the user's own URL. Sent as a header |
| `SERPER_COUNTRY` | `us` | No | Search country (`gl`) |
| `SERPER_LANGUAGE` | `en` | No | Search language (`hl`) |
| `SERPER_RESULTS_PER_QUERY` | `20` | No | Results requested per query before filtering and dedupe |
| `SERPER_BASE_URL` | `https://google.serper.dev` | No | Discovery endpoint; override for a proxy or mock |
| `SERPER_TIMEOUT_SECONDS` | `20` | No | Per-request timeout for discovery |
| `FIRECRAWL_BASE_URL` | `https://api.firecrawl.dev/v2` | No | Extraction endpoint; override for a proxy or mock |
| `FIRECRAWL_MAX_CONCURRENCY` | `5` | No | Parallel page fetches |
| `FIRECRAWL_TIMEOUT_SECONDS` | `30` | No | Per-page timeout |
| `EXTRACT_DEADLINE_SECONDS` | `60` | No | Whole-stage deadline; unread pages are marked, the run continues |
| `MIN_EXTRACTED_CHARS` | `200` | No | Below this, page text is chrome rather than listing copy and is not scored |
| `COMPETITOR_MAX_PER_DOMAIN` | `4` | No | Cap per storefront, so one site cannot fill the competitive set |
| `BENCHMARK_MIN_COHORT` | `4` | No | Below this the same-platform cohort is too small to be the headline |
| `RAINFOREST_API_KEY` | -- | With `rainforest` | Amazon-only provider key. Travels in the **URL**, so keep the httpx logger at WARNING |
| `COMPETITOR_CACHE_TTL_HOURS` | `24` | No | How long a fetched competitor set and its benchmark are reused; `0` disables |
| `COMPETITOR_ALLOW_FALLBACK` | `true` | No | Continue with clearly-labelled estimates when the live provider fails |
| `RAINFOREST_BASE_URL` | `https://api.rainforestapi.com/request` | No | Provider endpoint; override for a proxy or mock |
| `RAINFOREST_MAX_CONCURRENCY` | `5` | No | Parallel product lookups per fetch |
| `RAINFOREST_TIMEOUT_SECONDS` | `45` | No | Per-request timeout for the provider |
| `LLM_TIMEOUT_SECONDS` | `90` | No | Wall-clock budget per LLM call |
| `LLM_MAX_RETRIES` | `2` | No | Retries after the first attempt |
| `LLM_RETRY_BASE_DELAY` | `1.0` | No | Base seconds for exponential backoff |
| `LLM_RETRY_MAX_DELAY` | `20.0` | No | Cap on a single backoff sleep, in seconds |
| `SQLITE_CHECKPOINT_PATH` | `data/checkpoints.db` | No | Configured but **not currently used** — see Known Limitations |
| `OPENAI_MODEL` | `gpt-4o` | No | Model for every stage |
| `CORS_ORIGINS` | `http://localhost:3000` | No | Allowed frontend origins |
| `LANGCHAIN_TRACING_V2` | `false` | No | Enable LangSmith tracing |
| `LANGCHAIN_API_KEY` | -- | No | LangSmith API key |
| `LANGCHAIN_PROJECT` | `default` | No | LangSmith project name |

---

## Roadmap

| Phase | Feature | Status |
|-------|---------|--------|
| v1.0 | 8-agent pipeline, 10 rubrics, SSE streaming, 3 rewrite variants | Done |
| v1.2 | Live competitor data (Rainforest), measured benchmark, counted statistics, verified rewrite scores | Done |
| v1.1 | API-key auth, per-key rate/concurrency/token quotas, spend circuit breaker | Done |
| v1.1 | Eval harness — score stability, tier discrimination, classification drift gates | Done |
| v1.1 | User accounts, login sessions, roles, and an admin panel for limits | Done |
| v1.2 | Login rate limiting, self-service password change, Postgres, Docker + CI | Planned |
| v1.1 | Real competitor data via Rainforest API / Amazon SP-API | Planned |
| v1.2 | Batch mode — analyze 100+ ASINs in a portfolio | Planned |
| v1.3 | Historical tracking — score trends over time with re-analysis | Planned |
| v1.4 | A/B test generator — create structured split-test plans | Planned |
| v2.0 | Multi-marketplace (Amazon US/UK/DE, Shopify, Daraz, Noon) | Planned |

---

## Documentation

| Document | Covers |
|----------|--------|
| [README.md](README.md) | This file — what it does, how to run it, the API |
| [CLAUDE.md](CLAUDE.md) | Codebase orientation for contributors: architecture, conventions, common tasks |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | Running it, managing accounts, troubleshooting, incident recipes |
| [docs/LLMOPS.md](docs/LLMOPS.md) | LLM operations strategy, with a delivery-status table at the top |
| [docs/LANGGRAPH_GUIDE.md](docs/LANGGRAPH_GUIDE.md) | How LangGraph works and how this project uses it |

---

## License

Internal project — GRACE CodeRemLabs.
