"""
Rubric Template Loader
Loads scoring rubrics from JSON files in the rubrics directory.
Falls back to LLM-generated rubric when no pre-built rubric exists.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from models.schemas import ScoringRubric, RubricDimension

log = logging.getLogger("listingiq.rubrics")

RUBRICS_DIR = Path(__file__).parent
_index_cache: dict | None = None


def _load_index() -> dict:
    """Load and cache the rubric index."""
    global _index_cache
    if _index_cache is None:
        index_path = RUBRICS_DIR / "_index.json"
        with open(index_path) as f:
            _index_cache = json.load(f)
    return _index_cache


def get_available_subcategories() -> list[str]:
    """Return all subcategory names that have pre-built rubrics."""
    index = _load_index()
    return list(index["subcategories"].keys())


def get_rubric_index() -> dict:
    """Return the full index including aliases."""
    return _load_index()


def resolve_subcategory(query: str) -> str | None:
    """Resolve a query string to a canonical subcategory name using aliases."""
    index = _load_index()
    # Direct match
    if query in index["subcategories"]:
        return query
    # Alias match (case-insensitive)
    normalized = query.lower().strip()
    aliases = index.get("aliases", {})
    if normalized in aliases:
        return aliases[normalized]
    # Partial match on subcategory names
    for subcat in index["subcategories"]:
        if normalized in subcat.lower():
            return subcat
    return None


def load_rubric(subcategory: str) -> ScoringRubric | None:
    """
    Load a scoring rubric for the given subcategory.
    Returns None if no rubric file exists (caller should generate via LLM).
    """
    index = _load_index()

    # Try direct match first, then alias resolution
    filename = index["subcategories"].get(subcategory)
    if not filename:
        resolved = resolve_subcategory(subcategory)
        if resolved:
            filename = index["subcategories"].get(resolved)
            subcategory = resolved

    if not filename:
        log.warning("No rubric found for subcategory: %s", subcategory)
        return None

    rubric_path = RUBRICS_DIR / filename
    if not rubric_path.exists():
        log.warning("Rubric file missing: %s", rubric_path)
        return None

    with open(rubric_path) as f:
        data = json.load(f)

    dimensions = [RubricDimension(**d) for d in data["dimensions"]]
    log.info("Loaded rubric for '%s' — %d dimensions", subcategory, len(dimensions))

    return ScoringRubric(
        subcategory=subcategory,
        dimensions=dimensions,
        version=data.get("version", "1.0"),
    )


# ── Generic fallback rubric ─────────────────────────────────────

GENERIC_DIMENSIONS = [
    RubricDimension(
        name="Title Clarity",
        weight=0.15,
        description="Is the product title clear, specific, and informative?",
        scoring_criteria="0: Vague/generic. 5: Basic product name. 10: Specific with key attributes (brand, type, size, variant).",
    ),
    RubricDimension(
        name="Keyword Coverage",
        weight=0.15,
        description="Does the listing include category-relevant search terms?",
        scoring_criteria="0: No relevant keywords. 5: Some obvious keywords. 10: Comprehensive keyword coverage matching top competitors.",
    ),
    RubricDimension(
        name="Benefit Specificity",
        weight=0.12,
        description="Are specific benefits and outcomes clearly stated?",
        scoring_criteria="0: No benefits. 5: Generic claims. 10: Specific, measurable outcomes with supporting detail.",
    ),
    RubricDimension(
        name="Trust Signals",
        weight=0.12,
        description="Are certifications, testing, and credibility markers present?",
        scoring_criteria="0: None. 5: 1-2 basic signals. 10: Multiple third-party certifications, testing, and trust markers.",
    ),
    RubricDimension(
        name="Ingredient/Feature Transparency",
        weight=0.12,
        description="Are key ingredients, materials, or features clearly disclosed?",
        scoring_criteria="0: No detail. 5: Basic mention. 10: Full transparency with specifics (types, concentrations, sources).",
    ),
    RubricDimension(
        name="Target Audience Alignment",
        weight=0.10,
        description="Does the listing speak to a specific audience's needs?",
        scoring_criteria="0: Generic. 5: Broad audience. 10: Clearly targets specific use cases and demographics.",
    ),
    RubricDimension(
        name="Structural Quality",
        weight=0.10,
        description="Is the listing well-structured with proper bullets, formatting, and readability?",
        scoring_criteria="0: Wall of text. 5: Basic structure. 10: Scannable bullets, clear hierarchy, optimal length.",
    ),
    RubricDimension(
        name="Competitive Differentiation",
        weight=0.08,
        description="Does the listing clearly differentiate from competitors?",
        scoring_criteria="0: Generic/commodity. 5: Some unique elements. 10: Clear USP that competitors lack.",
    ),
    RubricDimension(
        name="Value Communication",
        weight=0.06,
        description="Is the value proposition (quantity, servings, cost-per-use) communicated?",
        scoring_criteria="0: No value info. 5: Basic quantity. 10: Clear servings, cost-per-serving, comparative value.",
    ),
]


def get_generic_rubric(subcategory: str = "Generic Product") -> ScoringRubric:
    """Return a generic fallback rubric for unrecognized subcategories."""
    return ScoringRubric(
        subcategory=subcategory,
        dimensions=GENERIC_DIMENSIONS,
        version="1.0-generic",
    )
