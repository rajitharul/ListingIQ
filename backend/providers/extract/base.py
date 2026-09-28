"""
What reading a competitor's page produces.

`ExtractedPage` is deliberately separate from `CompetitorListing`: it records
what a *page* yielded and how confident we are in it, before that is merged with
what discovery already knew. The merge matters — discovery has the price and the
rating, the page has the copy, and neither should overwrite the other's better
information.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# How the fields were obtained, best first.
STRUCTURED = "structured"      # schema.org JSON-LD — exact, free, no model
MODEL = "model"                # read out of page text by the LLM
DISCOVERY_ONLY = "discovery_only"   # the page could not be read at all
FAILED = "failed"              # fetched, but produced nothing usable


# Below this, a description is effectively absent and worth asking the model
# for. Above it, the copy is the seller's own and must be left alone.
PRESENT_CHARS = 40

# Enough copy that scoring the listing against the rubric is fair rather than
# a measurement of what we failed to read.
SCOREABLE_CHARS = 120

# One surviving bullet is far more often an extraction artefact than a listing
# with exactly one selling point.
MIN_SCOREABLE_BULLETS = 2


@dataclass
class ExtractedPage:
    """The result of attempting to read one product page."""

    url: str
    title: str = ""
    description: str = ""
    bullet_points: list[str] = field(default_factory=list)
    brand_name: str = ""
    price: str = ""
    rating: float = 0.0
    review_count: int = 0
    # Cleaned page text, kept so the model pass can fill gaps without refetching.
    body: str = ""
    status: str = DISCOVERY_ONLY
    note: str = ""
    method: str = ""

    @property
    def has_copy(self) -> bool:
        """
        Whether there is enough real copy here to score the listing fairly.

        Two bullets, not one. A page that survived the chrome filter with a
        single item usually did not survive at all — observed live, two Amazon
        listings came through with one bullet each reading "Try disabling your
        extensions.", were marked scoreable, and would have been graded on the
        rubric as though that were the seller's copy. A competitor scored on our
        failure to read them lowers the benchmark mean and flatters the user.
        """
        if len(self.bullet_points) >= MIN_SCOREABLE_BULLETS:
            return True
        return len(self.description.strip()) >= SCOREABLE_CHARS

    def missing_fields(self) -> list[str]:
        """
        Which fields a model pass would still need to find.

        The bar is *absent*, not *short*. A 100-character description published
        in the page's own structured data is the seller's real copy; asking the
        model to fill that gap would invite it to lengthen genuine copy, and the
        expanded version would then be scored as though the competitor had
        written it.
        """
        gaps = []
        if not self.title:
            gaps.append("title")
        if not self.bullet_points:
            gaps.append("bullet_points")
        if len(self.description.strip()) < PRESENT_CHARS:
            gaps.append("description")
        if not self.brand_name:
            gaps.append("brand_name")
        return gaps
