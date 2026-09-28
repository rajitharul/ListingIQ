"""
Per-account quotas: request rate, concurrent runs, and daily token spend.

Limits belong to the account, not the credential, so a customer's browser
session and their API keys draw down one shared budget.

Three limits guard three different failure modes:

  * requests/minute — someone loops the endpoint
  * concurrent runs — someone fires many pipelines at once (each costs ~60s
    and thousands of tokens, so concurrency is the expensive dimension)
  * daily tokens    — sustained spend, per key and across the whole service

The first two are per-process and reset on restart, which is fine for windows
measured in seconds. The daily budget is persisted in SQLite so a restart does
not hand everyone a fresh allowance. Neither the rate nor the concurrency limit
is shared across instances: a multi-instance deploy needs Redis, and until then
the effective limit is (per-key limit x instance count).

Budgets are checked before a run starts and recorded after it finishes, so a
single run can overshoot the cap by its own cost. That is deliberate — the
alternative is refusing work on an estimate.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import HTTPException, status

from auth import Caller
from store import connect
from config import (
    GLOBAL_DAILY_TOKEN_LIMIT,
    OPENAI_COST_PER_1M_INPUT,
    OPENAI_COST_PER_1M_OUTPUT,
)

log = logging.getLogger("listingiq.quota")

# account_id -> timestamps of recent requests (sliding 60s window)
_requests: dict[str, deque[float]] = defaultdict(deque)
# account_id -> pipeline runs currently in flight
_active: dict[str, int] = defaultdict(int)


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def estimate_cost(prompt_tokens: int, completion_tokens: int) -> float | None:
    """
    Dollar cost of a run, or None when per-token prices are not configured.

    Prices are env-configured rather than hardcoded so they cannot silently
    drift out of date against the provider's actual pricing.
    """
    if OPENAI_COST_PER_1M_INPUT <= 0 and OPENAI_COST_PER_1M_OUTPUT <= 0:
        return None
    return (
        prompt_tokens / 1_000_000 * OPENAI_COST_PER_1M_INPUT
        + completion_tokens / 1_000_000 * OPENAI_COST_PER_1M_OUTPUT
    )


def _check_rate(caller: Caller) -> None:
    """Sliding 60-second window on request count."""
    now = time.monotonic()
    window = _requests[caller.account_id]
    while window and now - window[0] >= 60.0:
        window.popleft()

    if len(window) >= caller.rpm_limit:
        retry_after = max(1, int(60.0 - (now - window[0])) + 1)
        log.warning("Rate limit hit by %s (%d/min)", caller.label, caller.rpm_limit)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: {caller.rpm_limit} requests per minute.",
            headers={"Retry-After": str(retry_after)},
        )
    window.append(now)


async def _check_budget(caller: Caller) -> None:
    """Reject if this key, or the service as a whole, is out of tokens today."""
    day = _today()
    db = await connect()
    try:
        cur = await db.execute(
            "SELECT tokens FROM daily_usage WHERE account_id = ? AND day = ?",
            (caller.account_id, day),
        )
        row = await cur.fetchone()
        used = row[0] if row else 0

        cur = await db.execute(
            "SELECT COALESCE(SUM(tokens), 0) FROM daily_usage WHERE day = ?", (day,)
        )
        global_used = (await cur.fetchone())[0]
    finally:
        await db.close()

    if used >= caller.daily_token_limit:
        log.warning(
            "Daily budget exhausted for %s: %d/%d tokens",
            caller.label, used, caller.daily_token_limit,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Daily token budget exhausted "
                f"({used:,}/{caller.daily_token_limit:,}). Resets at 00:00 UTC."
            ),
        )

    if global_used >= GLOBAL_DAILY_TOKEN_LIMIT:
        # Service-wide circuit breaker: one runaway customer must not be able
        # to drain the provider account for everyone else.
        log.error(
            "GLOBAL daily token limit tripped: %d/%d — refusing all pipeline runs",
            global_used, GLOBAL_DAILY_TOKEN_LIMIT,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service token budget reached for today. Please retry tomorrow.",
        )


async def record_usage(account_id: str, prompt_tokens: int, completion_tokens: int) -> None:
    """Add a finished run's tokens to today's ledger, billed to the account."""
    total = prompt_tokens + completion_tokens
    if total <= 0:
        return
    db = await connect()
    try:
        await db.execute(
            """INSERT INTO daily_usage
                 (account_id, day, tokens, prompt_tokens, completion_tokens, runs)
               VALUES (?, ?, ?, ?, ?, 1)
               ON CONFLICT(account_id, day) DO UPDATE SET
                 tokens            = tokens + excluded.tokens,
                 prompt_tokens     = prompt_tokens + excluded.prompt_tokens,
                 completion_tokens = completion_tokens + excluded.completion_tokens,
                 runs              = runs + 1""",
            (account_id, _today(), total, prompt_tokens, completion_tokens),
        )
        await db.commit()
    finally:
        await db.close()


async def get_usage_today(account_id: str) -> dict:
    db = await connect()
    try:
        cur = await db.execute(
            """SELECT tokens, prompt_tokens, completion_tokens, runs
               FROM daily_usage WHERE account_id = ? AND day = ?""",
            (account_id, _today()),
        )
        row = await cur.fetchone()
    finally:
        await db.close()
    row = row or (0, 0, 0, 0)
    return {
        "day": _today(),
        "tokens": row[0],
        "prompt_tokens": row[1],
        "completion_tokens": row[2],
        "runs": row[3],
    }


async def acquire_slot(caller: Caller) -> None:
    """
    Admit one pipeline run, or raise 429/503.

    Must be awaited in the endpoint body, before any streaming response is
    constructed: an HTTPException raised inside an SSE generator cannot become
    an HTTP error response, because the response has already started. Every
    successful acquire must be paired with `release_slot` in a finally.
    """
    _check_rate(caller)
    await _check_budget(caller)

    if _active[caller.account_id] >= caller.max_concurrent:
        log.warning(
            "Concurrency limit hit by %s (%d running)",
            caller.label, caller.max_concurrent,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Too many concurrent runs: limit is {caller.max_concurrent}. "
                "Wait for a run to finish."
            ),
            headers={"Retry-After": "30"},
        )
    _active[caller.account_id] += 1


def release_slot(caller: Caller) -> None:
    """Release a slot taken by `acquire_slot`. Safe to call once per acquire."""
    _active[caller.account_id] -= 1
    if _active[caller.account_id] <= 0:
        del _active[caller.account_id]


@asynccontextmanager
async def pipeline_slot(caller: Caller):
    """acquire/release as a context manager, for non-streaming callers."""
    await acquire_slot(caller)
    try:
        yield
    finally:
        release_slot(caller)


def check_rate_only(caller: Caller) -> None:
    """Rate limit for the cheap, non-pipeline endpoints."""
    _check_rate(caller)


def reset_for_tests() -> None:
    """Clear the in-process windows. Used by the offline quota tests."""
    _requests.clear()
    _active.clear()
