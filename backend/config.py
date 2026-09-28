import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

# Host/port for the dev server. Configurable because deployment platforms
# inject $PORT, and because 8000 is a commonly occupied port locally.
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# ── LLM resilience ───────────────────────────────────────────────
# Per-request wall-clock budget for a single OpenAI call, in seconds.
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "90"))
# Retries AFTER the first attempt, so 2 means up to 3 total attempts.
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))
# Base delay for exponential backoff between retries, in seconds.
LLM_RETRY_BASE_DELAY = float(os.getenv("LLM_RETRY_BASE_DELAY", "1.0"))
# Ceiling on a single backoff sleep, in seconds.
LLM_RETRY_MAX_DELAY = float(os.getenv("LLM_RETRY_MAX_DELAY", "20.0"))

# ── Authentication & quotas ──────────────────────────────────────
# Disabling auth leaves every /api route open. Intended for local development
# only; main.py logs a startup warning whenever it is off.
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "true").lower() not in ("false", "0", "no")
AUTH_DB_PATH = Path(os.getenv(
    "AUTH_DB_PATH",
    str(Path(__file__).parent / "data" / "auth.db"),
))

# How long a browser login stays valid before requiring a fresh sign-in.
SESSION_TTL_HOURS = int(os.getenv("SESSION_TTL_HOURS", "168"))  # 7 days

# Defaults applied to a newly created account; per-account values override them.
DEFAULT_RPM_LIMIT = int(os.getenv("DEFAULT_RPM_LIMIT", "10"))
DEFAULT_MAX_CONCURRENT = int(os.getenv("DEFAULT_MAX_CONCURRENT", "2"))
DEFAULT_DAILY_TOKEN_LIMIT = int(os.getenv("DEFAULT_DAILY_TOKEN_LIMIT", "2000000"))

# Service-wide circuit breaker across all keys, in tokens per UTC day.
GLOBAL_DAILY_TOKEN_LIMIT = int(os.getenv("GLOBAL_DAILY_TOKEN_LIMIT", "20000000"))

# Optional, for cost reporting only — quotas are enforced in tokens, which need
# no pricing table. Set these to your current per-1M-token rates to have runs
# logged in dollars as well.
OPENAI_COST_PER_1M_INPUT = float(os.getenv("OPENAI_COST_PER_1M_INPUT", "0"))
OPENAI_COST_PER_1M_OUTPUT = float(os.getenv("OPENAI_COST_PER_1M_OUTPUT", "0"))

# ── Competitor data ──────────────────────────────────────────────
# "rainforest" = real marketplace data; "llm" = model estimates (dev only).
# Selling benchmark scores against estimated competitors is not defensible,
# so production must run on a live provider.
COMPETITOR_PROVIDER = os.getenv("COMPETITOR_PROVIDER", "llm")

# Continue with clearly-labelled estimated data when the live provider fails,
# rather than failing the run outright. The result records that it happened.
COMPETITOR_ALLOW_FALLBACK = os.getenv(
    "COMPETITOR_ALLOW_FALLBACK", "true").lower() not in ("false", "0", "no")

# One live fetch costs 11 upstream requests (1 search + 10 product lookups), so
# results are reused across runs of the same subcategory. 0 disables caching.
COMPETITOR_CACHE_TTL_HOURS = int(os.getenv("COMPETITOR_CACHE_TTL_HOURS", "24"))

# ── Web discovery (Serper) ───────────────────────────────────────
# Cross-merchant product search. /shopping returns merchant-attributed results
# with price and rating; /search finds the direct-to-consumer stores that
# shopping feeds under-represent.
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
SERPER_BASE_URL = os.getenv("SERPER_BASE_URL", "https://google.serper.dev")
SERPER_COUNTRY = os.getenv("SERPER_COUNTRY", "us")
SERPER_LANGUAGE = os.getenv("SERPER_LANGUAGE", "en")
SERPER_TIMEOUT_SECONDS = float(os.getenv("SERPER_TIMEOUT_SECONDS", "20"))
# Ask for more than we need: sponsored, own-brand and duplicate results are
# filtered out afterwards, and a thin result set cannot be topped up later.
SERPER_RESULTS_PER_QUERY = int(os.getenv("SERPER_RESULTS_PER_QUERY", "20"))

# ── Page extraction (Firecrawl) ──────────────────────────────────
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "")
FIRECRAWL_BASE_URL = os.getenv("FIRECRAWL_BASE_URL", "https://api.firecrawl.dev/v2")
FIRECRAWL_TIMEOUT_SECONDS = float(os.getenv("FIRECRAWL_TIMEOUT_SECONDS", "30"))
FIRECRAWL_MAX_CONCURRENCY = int(os.getenv("FIRECRAWL_MAX_CONCURRENCY", "5"))

# A whole-stage deadline. The Rainforest path has a per-request timeout and no
# total bound, so a slow tail can hang a run well past the ~60s the pipeline
# advertises. Extraction keeps whatever returned in time and marks the rest.
EXTRACT_DEADLINE_SECONDS = float(os.getenv("EXTRACT_DEADLINE_SECONDS", "60"))

# Below this many characters, extracted body copy is navigation chrome or a
# consent interstitial rather than listing copy. Scoring it would drag the
# benchmark down and flatter the user's percentile.
MIN_EXTRACTED_CHARS = int(os.getenv("MIN_EXTRACTED_CHARS", "200"))

# No more than this many competitors from any one storefront, so a single
# marketplace cannot fill the cohort.
COMPETITOR_MAX_PER_DOMAIN = int(os.getenv("COMPETITOR_MAX_PER_DOMAIN", "4"))

# A same-platform cohort smaller than this is not a benchmark — percentiles
# over two competitors are noise with a decimal point. Below it the headline
# falls back to the whole-category cohort and says so.
BENCHMARK_MIN_COHORT = int(os.getenv("BENCHMARK_MIN_COHORT", "4"))

RAINFOREST_API_KEY = os.getenv("RAINFOREST_API_KEY", "")
RAINFOREST_BASE_URL = os.getenv("RAINFOREST_BASE_URL", "https://api.rainforestapi.com/request")
RAINFOREST_TIMEOUT_SECONDS = float(os.getenv("RAINFOREST_TIMEOUT_SECONDS", "45"))
RAINFOREST_MAX_CONCURRENCY = int(os.getenv("RAINFOREST_MAX_CONCURRENCY", "5"))

# LangGraph SQLite checkpoint persistence
SQLITE_CHECKPOINT_PATH = os.getenv(
    "SQLITE_CHECKPOINT_PATH",
    str(Path(__file__).parent / "data" / "checkpoints.db"),
)
