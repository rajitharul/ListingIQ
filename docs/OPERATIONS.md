# Operations Runbook

Day-to-day running of ListingIQ: starting it, managing who can use it, and
fixing the things that actually go wrong. Every troubleshooting entry below is a
failure that has really happened on this project, not a hypothetical.

- [Running the stack](#running-the-stack)
- [Managing accounts](#managing-accounts)
- [Competitor data and its costs](#competitor-data-and-its-costs)
- [Where the data lives](#where-the-data-lives)
- [Cost and budget control](#cost-and-budget-control)
- [Troubleshooting](#troubleshooting)
- [Incident recipes](#incident-recipes)
- [Before deploying anywhere public](#before-deploying-anywhere-public)

---

## Running the stack

Two processes. Both need to be up.

```bash
# Backend — FastAPI + LangGraph
cd backend
source venv/bin/activate
python main.py                      # :8000, or PORT=8001 python main.py

# Frontend — Next.js
cd frontend
npm run dev                         # :3000, or PORT=3001 npm run dev
```

`frontend/.env.local` must point `BACKEND_URL` at wherever the backend is
listening. If you move the backend off 8000, change it here too or every request
will 502.

### Ports are frequently already taken

8000 and 3000 are popular. Check before assuming the app is broken:

```bash
ss -ltnp | grep -E ':(3000|3001|8000|8001)'
```

If another project owns the port, either stop it or move ListingIQ:

```bash
PORT=8001 python main.py
PORT=3001 npm run dev
# then set BACKEND_URL=http://localhost:8001 in frontend/.env.local
```

### Keeping servers alive

A dev server started from inside an agent session, CI job or any other
short-lived shell **dies when that shell's session ends**. If a page suddenly
stops loading, check the ports before debugging anything else.

To detach properly:

```bash
mkdir -p .logs
setsid nohup env PORT=8001 ./venv/bin/python main.py > .logs/backend.log 2>&1 < /dev/null &
setsid nohup env PORT=3001 npm run dev              > .logs/frontend.log 2>&1 < /dev/null &
```

Stop them by port rather than by process name — a name pattern like `main.py`
can match the very shell you are typing it in:

```bash
kill $(ss -ltnp | grep -oP ':(3001|8001)\s.*pid=\K[0-9]+')
```

### Health checks

```bash
curl -s localhost:8000/health                 # public, no auth
curl -s localhost:3000/login -o /dev/null -w '%{http_code}\n'
```

`/health` returning 200 only means the process is up. It does **not** check
OpenAI reachability or the database.

---

## Managing accounts

Everything here is also in the admin panel at `/admin`. The CLI exists for
bootstrapping and scripting, and works even when nobody can log in.

```bash
cd backend

# First administrator — before anyone can sign in
python manage_accounts.py create-admin you@example.com

python manage_accounts.py create user@example.com --rpm 20 --daily-tokens 500000
python manage_accounts.py list
python manage_accounts.py set-limits acct_ab12cd34 --daily-tokens 1000000
python manage_accounts.py password acct_ab12cd34      # also revokes their sessions
python manage_accounts.py deactivate acct_ab12cd34
python manage_accounts.py activate acct_ab12cd34

# API keys for scripts and CI. They spend the account's quota.
python manage_accounts.py issue-key acct_ab12cd34 "CI pipeline"
python manage_accounts.py list-keys
```

Passwords are prompted for, never taken as arguments, so they stay out of shell
history and the process list.

Things that are irreversible by design:

- A password or API key is stored **hashed**. Neither can be recovered — reset or
  reissue instead.
- The **last active admin cannot be demoted or disabled.** Promote a second admin
  first. This guard exists so you cannot lock everyone out of the panel.

---

## Where the data lives

| Path | Contents | Losing it means |
|------|----------|-----------------|
| `backend/data/auth.db` | accounts, sessions, API keys, daily usage, competitor + benchmark caches | everyone must be re-created; all logins drop; caches rebuild at provider cost |
| `backend/data/scoring_history.db` | score history per brand | historical trends are gone; the app still runs |
| `backend/.env` | OpenAI key, limits, tracing config | the app cannot start |
| `frontend/.env.local` | `BACKEND_URL` | frontend cannot reach the backend |
| `backend/evals/results/` | raw eval output | re-running costs money; gitignored by default |

Back up `auth.db` before any schema change:

```bash
cp backend/data/auth.db backend/data/auth.db.$(date +%Y%m%d).bak
```

Schema changes run automatically from `ensure_schema` in `store.py` on the next
connection. Migrations are idempotent and preserve data — the pre-accounts
upgrade, for instance, moves old usage rows to `daily_usage_pre_accounts` rather
than dropping them.

---

## Cost and budget control

One pipeline run is roughly **9 GPT-4o calls, ~16k tokens, ~60 seconds**. That is
the unit of spend to think in.

Three limits, all per account, all in `config.py` or per-account overrides:

| Limit | Default | Env |
|-------|---------|-----|
| Requests per minute | 10 | `DEFAULT_RPM_LIMIT` |
| Concurrent runs | 2 | `DEFAULT_MAX_CONCURRENT` |
| Tokens per day | 2,000,000 | `DEFAULT_DAILY_TOKEN_LIMIT` |
| Service-wide tokens per day | 20,000,000 | `GLOBAL_DAILY_TOKEN_LIMIT` |

Budgets are checked **before** a run and recorded **after**, so a single run can
overshoot its cap by its own cost. That is deliberate: the alternative is
refusing work based on a guess. Failed runs are billed too, because the tokens
were spent either way.

Check spend:

```bash
curl -s -b cookies.txt localhost:3000/api/usage        # the signed-in account
python manage_accounts.py list                         # limits for everyone
```

Quotas count **tokens, not dollars**, so no pricing table can go stale. For
dollar figures in logs and on `/api/usage`, set `OPENAI_COST_PER_1M_INPUT` and
`OPENAI_COST_PER_1M_OUTPUT` to your current rates.

---

## Competitor data and its costs

`COMPETITOR_PROVIDER` decides where competitors come from. **Production must run
`web`** — benchmark scores against estimated competitors are not defensible to a
paying customer, and `rainforest` only ever sees one marketplace.

```bash
# backend/.env
COMPETITOR_PROVIDER=web
SERPER_API_KEY=...            # discovery: who is selling this, and where
FIRECRAWL_API_KEY=...         # extraction: reading each competitor's page
COMPETITOR_CACHE_TTL_HOURS=24
```

Both keys travel in request **headers**. The Rainforest key, if you still use
that provider, travels as a URL query parameter and stays out of the logs only
because the `httpx` logger is pinned to WARNING in `main.py` — do not lower that.

Options, in order of preference:

| Value | Behaviour |
|-------|-----------|
| `web` | Open-web discovery across any platform. The default and the product |
| `rainforest` | Amazon only. Kept working, no longer the default |
| `llm` | Model estimates. Development only, and the labelled fallback |

### The cost shape that decides your margin

An uncached analysis in a new subcategory is roughly **3 search queries plus one
page fetch per competitor** — about a cent, against 11 requests for the old
Amazon-only path. On top of that the competitor benchmark is one large LLM call,
and page extraction is a second one *only for pages that published no structured
data*.

Both are cached per subcategory, so **the first analysis in a subcategory pays
and the rest of the day does not**. Cache hit rate is effectively your gross
margin — watch it.

```bash
grep -c "competitor cache HIT" .logs/backend.log
grep -c "serper .* queries"    .logs/backend.log     # uncached discovery
grep -c "firecrawl read"       .logs/backend.log     # uncached extraction
grep -c "structured data covered every page" .logs/backend.log   # free extractions
```

That last line is worth watching on its own: when a subcategory's competitors
publish proper `schema.org` markup, extraction costs no model tokens at all.

**The failure mode to watch for is a collapsed hit rate.** The competitor cache
key includes a fingerprint of the *request* — platform, subcategory, limit,
country — and deliberately **not** the generated query strings, which are built
from model-extracted entities and drift between runs. If that ever changes, hit
rate goes to near zero and the bill goes up while everything still appears to
work. `DISCOVERY_VERSION` in `providers/query.py` is the deliberate lever for
invalidating every entry after a logic change.

### Cache behaviour

| Cache | Key | Invalidated by |
|-------|-----|----------------|
| Competitor listings | platform + subcategory + **request fingerprint** | TTL, or a `DISCOVERY_VERSION` bump |
| Measured benchmarks | platform + subcategory + **rubric fingerprint** + **competitor-set fingerprint** | TTL, any edit to a dimension's `scoring_criteria`, or a different set of competitors |

Editing a rubric automatically invalidates its benchmark. That is deliberate:
comparing new user scores against competitor scores graded by old criteria would
silently corrupt every gap. The competitor-set fingerprint does the same job for
discovery: a benchmark can only ever be served for the exact set it was computed
from.

To force a refresh:

```python
# python, from backend/
import asyncio
from providers import cache, benchmark_cache
asyncio.run(cache.invalidate("amazon", "Magnesium Glycinate"))
asyncio.run(benchmark_cache.invalidate("amazon", "Magnesium Glycinate"))
```

Both match on prefix, so they clear every request and rubric variant for that
subcategory rather than one of them.

### Diagnosing a thin or odd competitor set

The provenance strip in the UI is the first place to look; `provider_note`
carries the same text.

| What you see | What it means |
|---|---|
| Amber *"AI-estimated competitors"* | Discovery failed entirely and the run fell back. `grep "falling back to estimated data" .logs/backend.log` |
| *"N of M pages could not be read"* | Discovery worked, extraction did not. Those competitors are shown but excluded from the benchmark. Usually Firecrawl credits (402) or a bot-hostile storefront |
| *"only N competitor(s) found on X"* | Too few same-platform results to form a cohort, so the headline percentile is measured across the whole category instead. Expected for brand-site sellers, since a search cannot be scoped to "Shopify" |
| One platform dominating the mix | `COMPETITOR_MAX_PER_DOMAIN` caps results per storefront. If the cohort is still lopsided, the category term is probably marketplace-dominated |
| *"N duplicate listing(s) merged"* | The same product was found on two storefronts. Working as intended |

### Provider credit exhaustion

Check both before blaming the pipeline:

```bash
grep "out of credits"        .logs/backend.log
grep "retrying via"          .logs/backend.log   # a platform API failed over
```



Each vendor degrades differently, on purpose:

- **Serper out of credits (402)** — discovery fails, the run falls back to
  estimated competitors and is labelled amber. This is the one that breaks the
  product.
- **Firecrawl out of credits (402)** — discovery still worked, so the run
  completes with real competitors and real prices, marked `discovery_only` and
  excluded from the benchmark. Degraded, not broken, and still labelled as
  observed data.

### Reading provenance

Every result carries `data_source`. `rainforest_api` means observed;
`llm_knowledge` means estimated, and the UI shows an amber banner saying so.
Estimated data is never cached, so an outage cannot leave estimates in place
after it recovers.

If customers report the amber banner, check the log for the reason:

```bash
grep "falling back to estimated data" .logs/backend.log
```

Common causes are an expired key, exhausted credits (HTTP 402) and provider rate
limiting (429).

---

## Troubleshooting

### A page loads nothing, or the browser can't connect

Check the servers are actually running before anything else:

```bash
ss -ltnp | grep -E ':(3000|3001|8000|8001)'
```

Most "the app is broken" reports are a dev server that exited with its parent
shell. Restart per [Keeping servers alive](#keeping-servers-alive).

### `ModuleNotFoundError: No module named 'pydantic'`

You are running system `python3` instead of the venv, or the venv is unusable.
Use `./venv/bin/python`, or `source venv/bin/activate` first.

### The venv or `node_modules` will not run at all

A tree copied between machines carries the wrong platform binaries. Symptoms:
`_pydantic_core...darwin.so` on Linux, `@next/swc-darwin-arm64`, missing execute
bits, `Permission denied`, or `MODULE_NOT_FOUND`.

Both are reproducible from their lockfiles — rebuild rather than repair:

```bash
cd backend  && python3 -m venv venv --clear && ./venv/bin/pip install -r requirements.txt
cd frontend && rm -rf node_modules && npm install
```

Check which platform a venv was built for with `cat backend/venv/pyvenv.cfg`.

### `Address already in use` after stopping the backend

`uvicorn --reload` runs a parent and a child. Killing the parent can leave the
child holding the port:

```bash
for p in $(ss -ltnp | grep ':8001' | grep -oP 'pid=\K[0-9]+'); do kill -9 "$p"; done
```

### Every `/api` call returns 401

- Not signed in — the browser has no session cookie, or it expired
  (`SESSION_TTL_HOURS`, 7 days by default).
- The account was disabled, or its password was changed; both revoke sessions
  immediately.
- An API key predates accounts. `manage_accounts.py list-keys` shows these as
  `ORPHANED`; they are refused rather than given a guessed owner. Reissue.

### 429 responses

Read the `detail` — the three limits give different messages:

| Message mentions | Meaning |
|------------------|---------|
| requests per minute | rate limit; `Retry-After` says how long |
| concurrent runs | too many pipelines in flight for that account |
| token budget | daily budget exhausted; resets 00:00 UTC |

Service-wide exhaustion returns **503**, not 429.

### 502 from the pipeline

An upstream model call failed after exhausting its retries. The detail names the
agent. 502 rather than 500 is deliberate: it means retryable. Check
`LLM_MAX_RETRIES` and `LLM_TIMEOUT_SECONDS`, and whether OpenAI is degraded.

### A run fails part-way and its work is lost

Expected today. `SQLITE_CHECKPOINT_PATH` is configured but unused, so there is no
resume. A dropped connection or backend restart discards a 60-second run.

### Logs are flooded with one warning per LLM call

`structured_completion` filters the known-benign LangSmith serializer warning
about `field_name='parsed'`. The filter is deliberately narrow — a serializer
warning about any *other* field is real and will still surface.

---

## Incident recipes

**Someone must lose access right now**

```bash
python manage_accounts.py deactivate acct_xxxx
```

Sessions die immediately and their API keys stop working on the next request.

**A password or key has leaked**

```bash
python manage_accounts.py password acct_xxxx      # revokes all their sessions
python manage_accounts.py list-keys               # find the key id
# revoke it from /admin, or issue a replacement and revoke the old one
```

**An account is burning the budget**

```bash
python manage_accounts.py set-limits acct_xxxx --daily-tokens 0 --concurrent 0
```

Takes effect on their next request; a run already in flight finishes.

**Everyone is locked out of the admin panel**

The CLI does not require a login:

```bash
python manage_accounts.py list
python manage_accounts.py password acct_of_an_admin
# or promote someone: the panel can do it once you are back in
```

**Scores look wrong after a prompt or rubric change**

Run the eval harness and diff against the previous baseline:

```bash
python evals/run_eval.py --mode scorer --repeats 5
python evals/run_eval.py --analyze evals/results/<earlier-file>.json
```

A dimension in "worst dimensions overall" is telling you which
`scoring_criteria` text to tighten. Vague criteria produce noise; criteria with
anchored, countable examples at 0/3/5/7/10 are effectively deterministic.

---

## Before deploying anywhere public

Known-open items, in the order they would hurt:

1. **`/api/auth/login` has no rate limit.** It is brute-forceable. Needs an
   IP-keyed limiter.
2. **Rate and concurrency limits are per-process.** A multi-instance deploy
   multiplies every limit by the instance count. They need Redis.
3. **SQLite opens a connection per request** and is a local file — it cannot be
   shared across instances. Move to Postgres.
4. **`next@15.1.0` has a published advisory** (CVE-2025-66478).
5. **Provider credits are a hard dependency.** Running out means every run falls
   back to labelled estimates. Monitor the balance and alert before it hits zero.
6. **No container, CI, or readiness probe.** `/health` does not check OpenAI or
   the database.
7. **`AUTH_ENABLED=false` opens every route.** It logs a startup banner, but make
   sure it cannot reach a deployed environment.
