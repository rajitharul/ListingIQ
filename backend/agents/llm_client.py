"""
Shared AsyncOpenAI client and the resilient structured-completion helper.

Every agent calls `structured_completion()` rather than the OpenAI SDK directly.
That gives the whole pipeline, in one place:

  * strict structured outputs — the model is handed a JSON Schema derived from a
    Pydantic model and the API guarantees conformance, so agents never parse
    JSON by hand or defend against missing keys
  * bounded retries with exponential backoff and jitter on transient failures,
    honouring Retry-After when the API sends it
  * a per-call wall-clock timeout, so a hung request cannot hang a pipeline run
  * an output-token ceiling, so no single agent can run away with the budget
  * token accounting per run, collected via a contextvar

A call that exhausts its retries raises `LLMCallError`, which carries the agent
name, the attempt count, and the underlying cause.
"""
from __future__ import annotations

import asyncio
import contextvars
import logging
import random
import time
import warnings
from dataclasses import dataclass, field
from typing import TypeVar

from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    ContentFilterFinishReasonError,
    InternalServerError,
    LengthFinishReasonError,
    RateLimitError,
)
from pydantic import BaseModel, ValidationError
from langsmith.wrappers import wrap_openai

from config import (
    LLM_MAX_RETRIES,
    LLM_RETRY_BASE_DELAY,
    LLM_RETRY_MAX_DELAY,
    LLM_TIMEOUT_SECONDS,
    OPENAI_API_KEY,
    OPENAI_MODEL,
)

log = logging.getLogger("listingiq.llm")

# LangSmith's wrap_openai traces chat.completions.parse by serialising the
# ParsedChatCompletion it returns. The base ChatCompletion types `parsed` as
# None, so every structured call emits a serializer warning — one per LLM call,
# which buries real log lines. The filter is deliberately scoped to that exact
# field: a serializer warning about any other field still surfaces.
warnings.filterwarnings(
    "ignore",
    message=r"Pydantic serializer warnings[\s\S]*field_name='parsed'",
    category=UserWarning,
    module="pydantic.main",
)

T = TypeVar("T", bound=BaseModel)

# Transient failures worth retrying. Everything else (auth, bad request,
# content filter, refusal) is a bug or a policy stop, not bad luck.
_RETRYABLE = (
    APITimeoutError,
    APIConnectionError,
    RateLimitError,
    InternalServerError,
    ValidationError,
)


class LLMCallError(RuntimeError):
    """An LLM call that failed after exhausting its retries."""

    def __init__(self, caller: str, attempts: int, cause: Exception):
        self.caller = caller
        self.attempts = attempts
        self.cause = cause
        super().__init__(
            f"{caller} failed after {attempts} attempt(s): "
            f"{type(cause).__name__}: {cause}"
        )


# ── Usage accounting ─────────────────────────────────────────────

@dataclass
class CallUsage:
    """Token usage for a single LLM call."""
    caller: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    duration_s: float
    attempts: int


@dataclass
class RunUsage:
    """Accumulated usage for one pipeline run."""
    calls: list[CallUsage] = field(default_factory=list)

    @property
    def prompt_tokens(self) -> int:
        return sum(c.prompt_tokens for c in self.calls)

    @property
    def completion_tokens(self) -> int:
        return sum(c.completion_tokens for c in self.calls)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


# Per-task usage ledger. Each pipeline run starts one; agents append to it
# without needing to thread a tracker through every function signature.
_usage: contextvars.ContextVar[RunUsage | None] = contextvars.ContextVar(
    "listingiq_usage", default=None
)


def start_usage_tracking() -> RunUsage:
    """Begin a fresh usage ledger for the current task. Returns the ledger."""
    ledger = RunUsage()
    _usage.set(ledger)
    return ledger


def get_usage() -> RunUsage | None:
    """Return the current task's usage ledger, if one was started."""
    return _usage.get()


# ── Client ───────────────────────────────────────────────────────

_client: AsyncOpenAI | None = None


def get_openai_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        # wrap_openai instruments the client so every call appears as an LLM
        # span in LangSmith (prompts, completions, token usage) nested under
        # the LangGraph node that made it. No-op when tracing is disabled.
        # It patches chat.completions.parse as well as .create, so structured
        # completions are traced too.
        _client = wrap_openai(AsyncOpenAI(api_key=OPENAI_API_KEY))
        log.info("AsyncOpenAI client initialised")
    return _client


def _retry_after_seconds(exc: Exception) -> float | None:
    """Extract a Retry-After hint from a rate-limit response, if present."""
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    raw = headers.get("retry-after")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _backoff_delay(attempt: int, exc: Exception) -> float:
    """Exponential backoff with full jitter, capped, honouring Retry-After."""
    hinted = _retry_after_seconds(exc)
    if hinted is not None:
        return min(hinted, LLM_RETRY_MAX_DELAY)
    ceiling = min(LLM_RETRY_BASE_DELAY * (2 ** attempt), LLM_RETRY_MAX_DELAY)
    return random.uniform(0, ceiling)


async def structured_completion(
    *,
    response_model: type[T],
    messages: list[dict],
    caller: str,
    temperature: float,
    max_completion_tokens: int,
    model: str = OPENAI_MODEL,
) -> T:
    """
    Call the model and return a validated `response_model` instance.

    Raises LLMCallError if every attempt fails. Never returns a partially
    populated model: strict structured outputs guarantee schema conformance,
    so callers can read every field without defensive `.get()` handling.
    """
    client = get_openai_client()
    prompt_preview = messages[-1]["content"][:80].replace("\n", " ") if messages else "<empty>"
    total_attempts = LLM_MAX_RETRIES + 1
    started = time.perf_counter()
    last_exc: Exception | None = None

    for attempt in range(total_attempts):
        suffix = "" if attempt == 0 else f"  (retry {attempt}/{LLM_MAX_RETRIES})"
        log.info('  ↗ LLM call  [%s]  model=%s  prompt="%s…"%s', caller, model, prompt_preview, suffix)
        call_started = time.perf_counter()

        try:
            completion = await client.chat.completions.parse(
                model=model,
                messages=messages,
                response_format=response_model,
                temperature=temperature,
                max_completion_tokens=max_completion_tokens,
                timeout=LLM_TIMEOUT_SECONDS,
            )
        except LengthFinishReasonError as exc:
            # Truncated output. Retrying with the same ceiling reproduces it,
            # so fail loudly and let the operator raise max_completion_tokens.
            log.error(
                "  ✗ LLM truncated [%s] — output hit the %d-token ceiling",
                caller, max_completion_tokens,
            )
            raise LLMCallError(caller, attempt + 1, exc) from exc
        except ContentFilterFinishReasonError as exc:
            log.error("  ✗ LLM content-filtered [%s]", caller)
            raise LLMCallError(caller, attempt + 1, exc) from exc
        except _RETRYABLE as exc:
            last_exc = exc
            if attempt == total_attempts - 1:
                break
            delay = _backoff_delay(attempt, exc)
            log.warning(
                "  ⟳ LLM retry [%s] after %s: %s — sleeping %.1fs",
                caller, type(exc).__name__, exc, delay,
            )
            await asyncio.sleep(delay)
            continue

        message = completion.choices[0].message
        if message.refusal:
            exc = RuntimeError(f"model refused: {message.refusal}")
            log.error("  ✗ LLM refusal [%s]: %s", caller, message.refusal)
            raise LLMCallError(caller, attempt + 1, exc) from exc

        parsed = message.parsed
        if parsed is None:
            # Should be unreachable under strict structured outputs, but a
            # None here would otherwise surface as an AttributeError upstream.
            last_exc = RuntimeError("model returned no parsed content")
            if attempt == total_attempts - 1:
                break
            await asyncio.sleep(_backoff_delay(attempt, last_exc))
            continue

        elapsed = time.perf_counter() - call_started
        usage = completion.usage
        tokens_in = usage.prompt_tokens if usage else 0
        tokens_out = usage.completion_tokens if usage else 0

        ledger = _usage.get()
        if ledger is not None:
            ledger.calls.append(CallUsage(
                caller=caller,
                model=model,
                prompt_tokens=tokens_in,
                completion_tokens=tokens_out,
                duration_s=elapsed,
                attempts=attempt + 1,
            ))

        log.info(
            "  ↙ LLM done [%s]  %.1fs  tokens_in=%s  tokens_out=%s  attempts=%d",
            caller, elapsed, tokens_in, tokens_out, attempt + 1,
        )
        return parsed

    total_elapsed = time.perf_counter() - started
    log.error(
        "  ✗ LLM exhausted [%s] after %d attempts in %.1fs: %s",
        caller, total_attempts, total_elapsed, last_exc,
    )
    raise LLMCallError(caller, total_attempts, last_exc or RuntimeError("unknown failure"))
