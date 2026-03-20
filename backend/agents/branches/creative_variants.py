"""
Creative Variant Generator Branch Agent
Generates alternative benchmark-quality taglines with different creative approaches.
"""
from __future__ import annotations

import json
import logging
import time
from config import OPENAI_MODEL
from models.schemas import BrandInput, BenchmarkSnippet, Dimension
from agents.llm_client import logged_chat_completion

log = logging.getLogger("sitescore.branch.creative_variants")


async def generate_creative_variants(
    brand_input: BrandInput,
    benchmark: BenchmarkSnippet,
    dimensions: list[Dimension],
) -> dict:
    """Generate alternative high-scoring tagline variants with different styles."""
    dim_descriptions = "\n".join(f"- {d.name} (weight {d.weight})" for d in dimensions)

    prompt = f"""You are an award-winning creative director who specialises in generating tagline variations.

Given the benchmark (ideal) tagline, create 4 creative VARIANTS that each take a different creative approach while maintaining high scores. Each variant should represent a distinct strategy.

BRAND: {brand_input.brand_name}
CATEGORY: {brand_input.product_category}
BENCHMARK TAGLINE: "{benchmark.ideal_tagline}"
CURRENT TAGLINE: "{brand_input.current_tagline}"

DIMENSIONS:
{dim_descriptions}

CREATIVE APPROACHES to use (one per variant):
1. Emotional/Storytelling — evoke deep feelings
2. Bold/Provocative — challenge conventions
3. Minimal/Elegant — maximum impact with minimum words
4. Action-Oriented — drive immediate response

Return a JSON object:
{{
  "variants": [
    {{
      "approach": "Emotional/Storytelling",
      "tagline": "...",
      "rationale": "Why this works for {brand_input.brand_name}",
      "estimated_score": <0-10>,
      "key_strength": "Which dimension this variant excels in"
    }}
  ]
}}

Return ONLY valid JSON."""

    response = await logged_chat_completion(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.6,
        response_format={"type": "json_object"},
        caller="creative_variants.generate",
    )
    return json.loads(response.choices[0].message.content)


async def creative_variant_node(state: dict) -> dict:
    """LangGraph node: generates creative tagline variants."""
    log.info("⚙ creative_variant_node ENTER")
    t0 = time.perf_counter()
    brand_input = BrandInput(**state["brand_input"]) if isinstance(state["brand_input"], dict) else state["brand_input"]
    benchmark = state["benchmark"]
    if isinstance(benchmark, dict):
        benchmark = BenchmarkSnippet(**benchmark)
    dimensions = state["dimensions"]
    if dimensions and isinstance(dimensions[0], dict):
        dimensions = [Dimension(**d) for d in dimensions]
    result = await generate_creative_variants(brand_input, benchmark, dimensions)
    log.info("⚙ creative_variant_node EXIT  %.1fs  variants=%d", time.perf_counter() - t0, len(result.get("variants", [])))
    return {"creative_variants_data": result}
