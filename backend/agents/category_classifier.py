"""
Category Classifier Agent (Agent 2)
Maps the parsed product listing to a vertical > category > subcategory hierarchy
and loads the corresponding scoring rubric.
"""
from __future__ import annotations

import json
import logging
import time
from config import OPENAI_MODEL
from models.schemas import ParsedListing, CategoryClassification, ScoringRubric, RubricDimension
from agents.llm_client import logged_chat_completion

log = logging.getLogger("listingiq.agent.category_classifier")

# Import rubric loader
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from data.rubrics.loader import load_rubric, get_available_subcategories, resolve_subcategory, get_generic_rubric


async def classify_category(parsed: ParsedListing) -> tuple[CategoryClassification, ScoringRubric]:
    """Classify the product and load the appropriate scoring rubric."""

    available = get_available_subcategories()
    available_list = "\n".join(f"- {s}" for s in available)

    prompt = f"""You are a product classification agent for an ecommerce listing optimization system.

PRODUCT TITLE: {parsed.original_title}
BRAND: {parsed.brand_name}
PRODUCT TYPE: {parsed.extracted_entities.product_type}
FORMAT: {parsed.extracted_entities.format_type}
INGREDIENTS: {', '.join(parsed.extracted_entities.ingredients[:15]) or 'Not specified'}
CLAIMS: {', '.join(parsed.extracted_entities.claims[:10]) or 'Not specified'}

AVAILABLE SUBCATEGORIES WITH PRE-BUILT SCORING RUBRICS:
{available_list}

TASK: Classify this product into:
1. vertical — the top-level market vertical (e.g., "Supplements & Nutraceuticals", "Beauty & Cosmetics")
2. category — the mid-level category (e.g., "Minerals", "Skincare", "Sports Nutrition")
3. subcategory — the specific product subcategory. PREFER matching one of the available subcategories above if the product fits. If no available subcategory matches, create an appropriate one.
4. confidence — how confident you are in this classification (0.0 to 1.0)
5. reasoning — brief explanation of why you chose this classification

Return a JSON object:
{{
  "vertical": "...",
  "category": "...",
  "subcategory": "...",
  "confidence": 0.95,
  "reasoning": "..."
}}

Return ONLY valid JSON."""

    response = await logged_chat_completion(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        response_format={"type": "json_object"},
        caller="category_classifier.classify",
    )
    data = json.loads(response.choices[0].message.content)

    classification = CategoryClassification(
        vertical=data.get("vertical", "General"),
        category=data.get("category", "General"),
        subcategory=data.get("subcategory", "General Product"),
        confidence=data.get("confidence", 0.5),
        reasoning=data.get("reasoning", ""),
    )

    # Try to load a pre-built rubric
    rubric = load_rubric(classification.subcategory)

    if rubric is None:
        # Try alias resolution
        resolved = resolve_subcategory(classification.subcategory)
        if resolved:
            rubric = load_rubric(resolved)
            classification.subcategory = resolved

    if rubric is None:
        # No pre-built rubric — generate one via LLM
        log.info("No pre-built rubric for '%s' — generating via LLM", classification.subcategory)
        rubric = await _generate_rubric(parsed, classification)

    return classification, rubric


async def _generate_rubric(
    parsed: ParsedListing,
    classification: CategoryClassification,
) -> ScoringRubric:
    """Generate a scoring rubric via LLM for subcategories without a pre-built template."""

    prompt = f"""You are a product listing evaluation expert. Generate a scoring rubric for evaluating ecommerce product listings in this specific subcategory.

VERTICAL: {classification.vertical}
CATEGORY: {classification.category}
SUBCATEGORY: {classification.subcategory}
PRODUCT TYPE: {parsed.extracted_entities.product_type}

Generate 8-10 scoring dimensions specifically tailored to what matters for listings in this subcategory. For each dimension:
- name: Short, clear name
- weight: Relative importance (all weights should sum to approximately 1.0)
- description: What this dimension measures and why it matters for this product type
- scoring_criteria: How to score 0-10 with specific examples at 0, 5, and 10

Think about what information buyers need to make a purchase decision for this specific product type.

Return a JSON object:
{{
  "dimensions": [
    {{
      "name": "...",
      "weight": 0.12,
      "description": "...",
      "scoring_criteria": "0: ... 5: ... 10: ..."
    }}
  ]
}}

Return ONLY valid JSON."""

    response = await logged_chat_completion(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        response_format={"type": "json_object"},
        caller="category_classifier.generate_rubric",
    )
    data = json.loads(response.choices[0].message.content)

    dims = data.get("dimensions", [])
    if not dims:
        log.warning("LLM generated empty rubric — using generic fallback")
        return get_generic_rubric(classification.subcategory)

    dimensions = [RubricDimension(**d) for d in dims]
    log.info("Generated %d-dimension rubric for '%s'", len(dimensions), classification.subcategory)

    return ScoringRubric(
        subcategory=classification.subcategory,
        dimensions=dimensions,
        version="1.0-generated",
    )


# ── LangGraph node wrapper ────────────────────────────────────
async def category_classifier_node(state: dict) -> dict:
    """LangGraph node: classifies product and loads scoring rubric."""
    log.info("⚙ category_classifier_node ENTER")
    t0 = time.perf_counter()

    parsed = state["parsed_listing"]
    if isinstance(parsed, dict):
        parsed = ParsedListing(**parsed)

    classification, rubric = await classify_category(parsed)
    log.info(
        "⚙ category_classifier_node EXIT  %.1fs  %s > %s > %s (%.0f%% conf, %d dims)",
        time.perf_counter() - t0,
        classification.vertical,
        classification.category,
        classification.subcategory,
        classification.confidence * 100,
        len(rubric.dimensions),
    )
    return {"category": classification, "rubric": rubric}
