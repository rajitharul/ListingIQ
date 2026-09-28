"""
Competitor data providers.

The product's central claim is that a listing is benchmarked against its real
top 10 competitors. Which provider served that data therefore matters as much as
the data itself, so every result carries honest provenance: what fetched it, when,
and whether it is live marketplace data or a model's estimate.

Never present estimated data as observed. `CompetitorScoutResult.data_source` is
the contract the UI reads to label it.
"""
from __future__ import annotations

from typing import Protocol

from models.schemas import CategoryClassification, CompetitorScoutResult


class ProviderError(RuntimeError):
    """A competitor provider failed to return usable data."""

    def __init__(self, provider: str, detail: str, *, retryable: bool = True):
        self.provider = provider
        self.detail = detail
        self.retryable = retryable
        super().__init__(f"{provider}: {detail}")


class CompetitorProvider(Protocol):
    """Fetches the top competitor listings for a subcategory."""

    name: str

    async def fetch(
        self,
        category: CategoryClassification,
        platform: str,
        brand_name: str = "",
        limit: int = 10,
    ) -> CompetitorScoutResult:
        ...
