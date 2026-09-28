"""
What a discovery provider returns: candidates, not competitors.

The split matters. Discovery answers "who is selling this, and where" — it
produces a URL, a merchant and whatever commercial metadata the search engine
already knows (price, rating, review count, rank). It does *not* produce listing
copy, because a search result has none.

Extraction turns a candidate into a `CompetitorListing` by reading the page.
Keeping the two apart is what lets the system be platform-agnostic: discovery
does not care which site a result is on, and extraction does not care how the
URL was found.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from normalize import registrable_domain
from providers import platforms


@dataclass
class Candidate:
    """One product found by a search, before its page has been read."""

    url: str
    title: str = ""
    merchant: str = ""
    price: str = ""
    rating: float = 0.0
    review_count: int = 0
    # Position within the result set that produced it, 1-based.
    position: int = 0
    # Which channel found it: "shopping" or "web".
    channel: str = ""
    # The engine's own product id, when it has one. Exact cross-merchant match.
    product_id: str = ""

    platform: str = field(default="", init=False)
    domain: str = field(default="", init=False)

    def __post_init__(self) -> None:
        self.domain = registrable_domain(self.url)
        # A shopping result has no address — its link is a search-engine
        # interstitial — so the merchant name is the only platform signal it
        # carries. Falling back to URL detection there would make every priced
        # competitor "generic".
        self.platform = (platforms.detect(self.url) if self.url
                         else platforms.from_merchant(self.merchant))
        if not self.merchant:
            self.merchant = platforms.label_for(self.platform)

    @property
    def has_commercial_signal(self) -> bool:
        """
        Whether the engine gave us price or rating.

        Web results carry neither. That is an absence of knowledge, not a
        rating of zero, and downstream arithmetic has to treat it that way.
        """
        return bool(self.price) or self.rating > 0


class DiscoveryProvider(Protocol):
    """Finds candidate competitor products for a query plan."""

    name: str

    async def discover(self, plan) -> list[Candidate]:
        ...
