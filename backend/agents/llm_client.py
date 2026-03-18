"""
Shared AsyncOpenAI client singleton.
All agents import from here instead of creating their own instances.
Also provides a logged wrapper so every LLM call is visible in the terminal.
"""
import logging
import time
from openai import AsyncOpenAI
from config import OPENAI_API_KEY

log = logging.getLogger("sitescore.llm")

# Single reusable client — connection pooling, no repeated instantiation
_client: AsyncOpenAI | None = None


def get_openai_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        log.info("AsyncOpenAI client initialised")
    return _client


async def logged_chat_completion(*, model: str, messages: list, caller: str = "unknown", **kwargs):
    """Wrapper around chat.completions.create that logs timing and token usage."""
    client = get_openai_client()
    prompt_preview = messages[-1]["content"][:80].replace("\n", " ") if messages else "<empty>"
    log.info("  ↗ LLM call  [%s]  model=%s  prompt=\"%s…\"", caller, model, prompt_preview)
    t0 = time.perf_counter()
    response = await client.chat.completions.create(model=model, messages=messages, **kwargs)
    elapsed = time.perf_counter() - t0
    usage = response.usage
    tokens_in = usage.prompt_tokens if usage else "?"
    tokens_out = usage.completion_tokens if usage else "?"
    log.info("  ↙ LLM done [%s]  %.1fs  tokens_in=%s  tokens_out=%s", caller, elapsed, tokens_in, tokens_out)
    return response
