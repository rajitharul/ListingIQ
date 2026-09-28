"""
Competitor provider selection.

`COMPETITOR_PROVIDER` chooses the source. Live results are cached by
subcategory; estimated results never are, so a temporary outage cannot leave
estimated data masquerading as real for the rest of the TTL.

If the live provider fails and `COMPETITOR_ALLOW_FALLBACK` is on, the run
continues with estimated data — but `data_source` and `provider_note` record
exactly that, and the UI labels it. A degraded, honestly-labelled answer is
better than a failed 60-second run; silently passing estimates off as observed
data is not.
"""
from __future__ import annotations

import logging

from config import COMPETITOR_ALLOW_FALLBACK, COMPETITOR_PROVIDER
from models.schemas import (
    CategoryClassification,
    CompetitorScoutResult,
    ExtractedEntities,
)
from providers import cache
from providers.query import build_query_plan
from providers.base import CompetitorProvider, ProviderError
from providers.llm import LLMProvider
from providers.rainforest import RainforestProvider
from providers.web import WebSearchProvider

log = logging.getLogger("listingiq.providers")

_PROVIDERS: dict[str, type] = {
    "web": WebSearchProvider,          # open-web discovery, any platform
    "rainforest": RainforestProvider,  # Amazon only, still supported
    "llm": LLMProvider,                # estimates: development and fallback
}


def get_provider(name: str | None = None) -> CompetitorProvider:
    key = (name or COMPETITOR_PROVIDER).lower()
    if key not in _PROVIDERS:
        raise ValueError(
            f"Unknown COMPETITOR_PROVIDER {key!r}. Options: {', '.join(_PROVIDERS)}")
    return _PROVIDERS[key]()


async def fetch_competitors(
    category: CategoryClassification,
    platform: str,
    brand_name: str = "",
    limit: int = 10,
    *,
    entities: ExtractedEntities | None = None,
) -> CompetitorScoutResult:
    """Fetch competitors via the configured provider, with cache and fallback."""
    provider = get_provider()

    # The cache key is the identity of what was asked for. For a single
    # marketplace that genuinely is (platform, subcategory), so those providers
    # keep the original key and their existing entries stay valid. Web
    # discovery can return a different set for the same pair — a different
    # limit or country — so it adds a fingerprint of the request.
    #
    # The fingerprint deliberately excludes the generated query strings. Those
    # are built from model-extracted entities and drift between runs, so keying
    # on them would make almost every lookup a miss and quietly destroy the
    # cache hit rate the unit economics depend on.
    key = ""
    if isinstance(provider, WebSearchProvider):
        key = build_query_plan(category, entities, platform=platform,
                               brand_name=brand_name, limit=limit).fingerprint()

    cached = await cache.get(platform, category.subcategory, key)
    if cached is not None:
        log.info("competitor cache HIT for %s/%s (%d listings)",
                 platform, category.subcategory, len(cached.listings))
        return cached.model_copy(update={"from_cache": True})

    try:
        result = await _call(provider, category, platform, brand_name, limit, entities)
    except ProviderError as e:
        if provider.name == LLMProvider.name or not COMPETITOR_ALLOW_FALLBACK:
            raise
        log.error("Provider %s failed (%s) — falling back to estimated data",
                  provider.name, e)
        result = await LLMProvider().fetch(category, platform, brand_name, limit)
        result = result.model_copy(update={
            "provider_note": (
                f"{provider.name} unavailable ({e.detail}); these competitors are "
                "AI-estimated, not observed marketplace data"
            )
        })
        return result

    await cache.put(platform, category.subcategory, result, key)
    return result


async def _call(provider, category, platform, brand_name, limit, entities):
    """
    Invoke a provider, passing extracted entities to those that can use them.

    Only the web provider builds search queries from the parsed listing; the
    others take the subcategory alone. Passing the argument conditionally keeps
    the shared protocol narrow instead of widening it for every provider.
    """
    if isinstance(provider, WebSearchProvider):
        return await provider.fetch(category, platform, brand_name, limit,
                                    entities=entities)
    return await provider.fetch(category, platform, brand_name, limit)
