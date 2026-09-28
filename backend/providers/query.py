"""
Turning a classified product into the searches that find its competitors.

The old provider used one string: `category.subcategory`. That is enough for a
marketplace search box, which already knows it is searching products, and far
too little for the open web, where "Magnesium Glycinate" returns encyclopaedia
entries and clinical papers before it returns anything anyone is selling.

**This is deliberately not an LLM call.** The model has already proposed: the
input parser produced `ExtractedEntities` and the classifier produced the
subcategory. Composing those into a query string is assembly, not judgement, and
the project's rule is that Python does the mechanical part. A planner call would
also make the queries non-deterministic, which matters more than it sounds —
see `fingerprint` below.

The plan is also the competitor cache's identity, so it lives here rather than
being assembled inline at the call site.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field

from models.schemas import CategoryClassification, ExtractedEntities
from providers import platforms

# Bumped when the planning rules or the merge rules change, so every cached
# result from the old logic is invalidated without a manual purge.
DISCOVERY_VERSION = 1

# Shopping search recall degrades badly on long queries — it is matching against
# merchant product titles, not documents.
_MAX_QUERY_TOKENS = 7

_STRENGTH_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*(mg|mcg|g|iu|ml|%)\b", re.I)


@dataclass(frozen=True)
class QueryPlan:
    """Everything a discovery provider needs, and the cache's identity."""

    subcategory: str
    platform: str = ""
    limit: int = 10
    country: str = "us"
    language: str = "en"
    brand_name: str = ""
    # Cross-merchant product search.
    shopping: tuple[str, ...] = ()
    # Open-web search, including the platform-scoped query.
    web: tuple[str, ...] = ()

    @property
    def all_queries(self) -> tuple[str, ...]:
        return self.shopping + self.web

    def fingerprint(self) -> str:
        """
        Identity of what was *asked for*, not of the strings we generated.

        The query strings are derived from `ExtractedEntities`, which an LLM
        regenerates on every run — "capsules" one time, "veggie capsules" the
        next. Hashing the generated strings would give almost every run a fresh
        cache key, hit rate would collapse to nothing, and the caching that the
        unit economics depend on would quietly stop working while still
        appearing to function. So the fingerprint covers the stable inputs only.
        """
        payload = json.dumps({
            "subcategory": self.subcategory.strip().lower(),
            "platform": platforms.canonical(self.platform),
            "limit": self.limit,
            "country": self.country,
            "v": DISCOVERY_VERSION,
        }, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _tokens(*parts: str) -> list[str]:
    seen: list[str] = []
    for part in parts:
        for tok in (part or "").split():
            low = tok.lower()
            if low not in {t.lower() for t in seen}:
                seen.append(tok)
    return seen


def _strength(dosage: str) -> str:
    """'400 mg per serving' -> '400mg'. Empty when there is no clear figure."""
    m = _STRENGTH_RE.search(dosage or "")
    return f"{m.group(1)}{m.group(2).lower()}" if m else ""


def build_query_plan(
    category: CategoryClassification,
    entities: ExtractedEntities | None = None,
    *,
    platform: str = "",
    brand_name: str = "",
    limit: int = 10,
    country: str = "us",
    language: str = "en",
) -> QueryPlan:
    """Compose the searches for one product. Pure; no I/O."""
    subcategory = (category.subcategory or category.category or "").strip()
    e = entities or ExtractedEntities()

    # The most specific qualifier available, in order of how much it narrows.
    qualifier = (e.format_type or "").strip() or _strength(e.dosage_info)
    primary = " ".join(_tokens(subcategory, qualifier)[:_MAX_QUERY_TOKENS]).strip()
    if not primary:
        primary = subcategory or category.vertical

    shopping: list[str] = [primary]

    web: list[str] = []
    # Always at least one open-web query. Shopping search structurally
    # under-returns direct-to-consumer stores — it indexes merchant feeds — so
    # without this leg the "whole category" cohort is just more marketplaces
    # and earns nothing the same-platform cohort did not already say.
    web.append(" ".join(_tokens("best", subcategory, qualifier)[:_MAX_QUERY_TOKENS]))

    # A query scoped to the user's own platform, so the same-platform cohort is
    # reliably populated rather than left to whatever Shopping happened to
    # surface. `site:` is a web-search operator; Shopping does not honour it.
    domain = platforms.domain_for(platform)
    if domain:
        web.append(f"{primary} site:{domain}")

    # A certification is a strong commercial-intent signal when present.
    cert = next((c for c in (e.certifications or []) if c.strip()), "")
    if cert:
        web.append(" ".join(_tokens(subcategory, cert)[:_MAX_QUERY_TOKENS]))

    # Brand exclusion is a post-filter, never query syntax: a `-brand` term
    # silently drops legitimate competitors that merely mention the brand.
    return QueryPlan(
        subcategory=subcategory,
        platform=platform,
        limit=limit,
        country=country,
        language=language,
        brand_name=brand_name,
        shopping=tuple(q for q in shopping if q.strip()),
        web=tuple(dict.fromkeys(q for q in web if q.strip())),
    )
