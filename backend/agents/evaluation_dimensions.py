"""
Evaluation Dimension Agent
Dynamically generates scoring dimensions tailored to the brand and product category
using LLM intelligence. Falls back to universal defaults if LLM fails.
"""
import json
import logging
import time
from config import OPENAI_MODEL
from models.schemas import BrandInput, Dimension
from agents.llm_client import logged_chat_completion

log = logging.getLogger("sitescore.agent.dimensions")

# ── Fallback dimensions (used only if LLM call fails) ─────────
FALLBACK_DIMENSIONS: list[Dimension] = [
    Dimension(name="Clarity", description="How immediately understandable is the message?", weight=1.0),
    Dimension(name="Memorability", description="How sticky and recall-friendly is the tagline?", weight=1.0),
    Dimension(name="Emotional Resonance", description="Does the copy evoke a feeling?", weight=1.0),
    Dimension(name="Persuasiveness", description="Does the copy compel action?", weight=1.0),
    Dimension(name="Brand Alignment", description="How well does the tagline reinforce the brand's identity?", weight=1.0),
    Dimension(name="Differentiation", description="Does the copy clearly distinguish this brand from competitors?", weight=1.0),
]


async def generate_dimensions(
    brand_name: str,
    product_category: str,
    target_audience: str = "",
) -> list[Dimension]:
    """Use GPT-4o to generate 5-7 scoring dimensions tailored to this brand + category."""

    prompt = f"""You are a senior marketing measurement scientist who designs evaluation frameworks for brand benchmarking.

TASK: Generate 5 to 7 scoring dimensions specifically tailored to evaluate marketing taglines for the following brand and category. Each dimension should be relevant to how consumers perceive and respond to messaging in this specific market.

BRAND: {brand_name}
CATEGORY: {product_category}
TARGET AUDIENCE: {target_audience or "General consumer"}

REQUIREMENTS:
1. Dimensions must be SPECIFIC to this category — e.g., a chocolate brand needs "Sensory Appeal" or "Indulgence Factor", a tech brand needs "Innovation Signal", a coffee brand needs "Ritual Connection"
2. Include 2-3 universal marketing dimensions (e.g., Clarity, Memorability) alongside category-specific ones
3. Assign a weight between 0.5 and 2.0 to each dimension based on its relative importance for THIS category (weights do NOT need to sum to any particular total)
4. Each description should be 1-2 sentences explaining what the dimension measures and why it matters for this category

Return a JSON object:
{{
  "dimensions": [
    {{
      "name": "DimensionName",
      "description": "What this dimension measures and why it matters for {product_category}",
      "weight": 1.2
    }}
  ]
}}

Return ONLY valid JSON, no markdown."""

    try:
        response = await logged_chat_completion(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            response_format={"type": "json_object"},
            caller="dimensions.generate",
        )
        data = json.loads(response.choices[0].message.content)
        items = data.get("dimensions", [])
        if not items:
            log.warning("LLM returned empty dimensions — using fallback")
            return FALLBACK_DIMENSIONS
        dims = [Dimension(**d) for d in items]
        log.info("Generated %d tailored dimensions for %s/%s", len(dims), brand_name, product_category)
        return dims
    except Exception as e:
        log.error("Dimension generation failed (%s) — using fallback", e)
        return FALLBACK_DIMENSIONS


def get_dimensions(custom_dimensions: list[Dimension] | None = None) -> list[Dimension]:
    """Return fallback dimensions, merging any custom ones. Used by non-graph endpoints."""
    if not custom_dimensions:
        return FALLBACK_DIMENSIONS
    dim_map = {d.name: d for d in FALLBACK_DIMENSIONS}
    for cd in custom_dimensions:
        dim_map[cd.name] = cd
    return list(dim_map.values())


# ── LangGraph node wrapper ────────────────────────────────────
async def dimensions_node(state: dict) -> dict:
    """LangGraph node: generates scoring dimensions tailored to the brand."""
    log.info("⚙ dimensions_node ENTER")
    t0 = time.perf_counter()

    brand_input = state["brand_input"]
    brand_name = brand_input.brand_name if hasattr(brand_input, "brand_name") else brand_input.get("brand_name", "Unknown")
    product_category = brand_input.product_category if hasattr(brand_input, "product_category") else brand_input.get("product_category", "General")
    target_audience = brand_input.target_audience if hasattr(brand_input, "target_audience") else brand_input.get("target_audience", "")

    # Generate tailored dimensions via LLM
    dims = await generate_dimensions(brand_name, product_category, target_audience)

    # Merge with any custom dimensions the user passed
    custom = state.get("custom_dimensions")
    if custom and len(custom) > 0:
        custom_list = [Dimension(**d) if isinstance(d, dict) else d for d in custom]
        dim_map = {d.name: d for d in dims}
        for cd in custom_list:
            dim_map[cd.name] = cd
        dims = list(dim_map.values())

    log.info("⚙ dimensions_node EXIT  %.1fs  %d dimensions", time.perf_counter() - t0, len(dims))
    return {"dimensions": dims}
