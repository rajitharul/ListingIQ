"""
Shared HTTP plumbing for competitor data providers.

Two problems this solves.

**`retryable` had no reader.** `ProviderError(..., retryable=...)` is set in five
places in `rainforest.py` and consumed nowhere: there is no retry loop in the
provider layer at all, so a single 429 from an upstream fails the whole fetch
while `agents/llm_client.py` retries the same class of failure happily. The flag
was documentation. `request_json` makes it behaviour.

**Tests had to patch each provider's module-level `httpx`.** `tests/test_providers.py`
assigns `providers.rainforest.httpx.AsyncClient` and never restores it, so later
sections leak into earlier ones and it passes only because the checks happen to
be ordered compatibly. Every provider builds its client through `make_client`
here, so a test patches one symbol, for every provider, and can restore it.

Each provider supplies its own `classify` callback, because status codes mean
different things per vendor — a 402 is "out of credits" for one and unused by
another. The retry *policy* stays here, in one place, tested once.
"""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Callable

import httpx

from providers.base import ProviderError

log = logging.getLogger("listingiq.providers.http")

# Mirrors the LLM client's shape: bounded attempts, exponential backoff, full
# jitter so concurrent retries do not resynchronise into a thundering herd.
DEFAULT_RETRIES = 2
DEFAULT_BASE_DELAY = 0.5
DEFAULT_MAX_DELAY = 8.0


def make_client(timeout: float = 30.0) -> httpx.AsyncClient:
    """
    The single seam through which every provider gets an HTTP client.

    Tests patch this one symbol to inject `httpx.MockTransport`. Do not
    construct `httpx.AsyncClient` directly in a provider, and reach this
    function through the module (`_http.make_client(...)`) rather than
    `from providers.http import make_client` — a name bound at import time
    cannot be patched, so the stub would be silently ignored and the test
    would hit the live network.
    """
    return httpx.AsyncClient(timeout=timeout)


def _backoff_delay(attempt: int, retry_after: float | None = None) -> float:
    """Exponential backoff with full jitter, capped, honouring Retry-After."""
    if retry_after is not None:
        return min(retry_after, DEFAULT_MAX_DELAY)
    ceiling = min(DEFAULT_BASE_DELAY * (2 ** attempt), DEFAULT_MAX_DELAY)
    return random.uniform(0, ceiling)


def _retry_after(response: httpx.Response) -> float | None:
    raw = response.headers.get("retry-after")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


async def request_json(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    provider: str,
    classify: Callable[[httpx.Response], ProviderError | None],
    json_body: dict | None = None,
    params: dict | None = None,
    headers: dict | None = None,
    retries: int = DEFAULT_RETRIES,
) -> dict:
    """
    Issue a request and return parsed JSON, retrying only retryable failures.

    `classify` inspects the response and returns a `ProviderError` to fail with,
    or None if the response is good. Whether that error is retried is decided by
    its own `retryable` flag — which is the whole point of this function.

    Transport errors (timeout, connection reset) are always retryable; a
    non-JSON body never is, because replaying it will not change the answer.
    """
    last: ProviderError | None = None

    for attempt in range(retries + 1):
        try:
            response = await client.request(
                method, url, json=json_body, params=params, headers=headers
            )
        except httpx.TimeoutException as e:
            last = ProviderError(provider, f"timed out: {e}", retryable=True)
        except httpx.HTTPError as e:
            last = ProviderError(provider, f"connection error: {e}", retryable=True)
        else:
            err = classify(response)
            if err is None:
                try:
                    return response.json()
                except ValueError as e:
                    raise ProviderError(
                        provider, f"non-JSON response: {e}", retryable=False
                    ) from e
            last = err
            if err.retryable and attempt < retries:
                delay = _backoff_delay(attempt, _retry_after(response))
                log.warning("⟳ %s retry %d/%d after %s — sleeping %.1fs",
                            provider, attempt + 1, retries, err.detail, delay)
                await asyncio.sleep(delay)
                continue
            raise err

        # Transport failure path: retry if we have attempts left.
        if attempt < retries:
            delay = _backoff_delay(attempt)
            log.warning("⟳ %s retry %d/%d after %s — sleeping %.1fs",
                        provider, attempt + 1, retries, last.detail, delay)
            await asyncio.sleep(delay)
            continue
        raise last

    # Unreachable: the loop either returns or raises.
    raise last or ProviderError(provider, "request failed", retryable=False)
