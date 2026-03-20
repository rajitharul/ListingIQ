"""
A/B Test Generator Branch Agent
Generates ready-to-deploy A/B test variants from improvement suggestions,
with hypothesis, expected lift, and statistical requirements.
"""
from __future__ import annotations

import json
import logging
import time
from config import OPENAI_MODEL
from models.schemas import BrandInput, ImprovementSuggestion
from agents.llm_client import logged_chat_completion

log = logging.getLogger("sitescore.branch.ab_test")


async def generate_ab_tests(
    brand_input: BrandInput,
    suggestions: list[ImprovementSuggestion],
) -> dict:
    """Generate A/B test variants from improvement suggestions."""
    suggestion_context = "\n".join(
        f'- Target: {s.target_dimension} | Current: {s.current_score} → Projected: {s.projected_score}\n  Original: "{s.original_text}" → Improved: "{s.improved_text}"'
        for s in suggestions
    )

    prompt = f"""You are a conversion rate optimisation specialist who designs A/B tests for marketing copy.

Given the following improvement suggestions, create structured A/B test plans.

BRAND: {brand_input.brand_name}
CATEGORY: {brand_input.product_category}

IMPROVEMENT SUGGESTIONS:
{suggestion_context}

For each suggestion, create a test plan. Return a JSON object:
{{
  "ab_tests": [
    {{
      "test_name": "Descriptive test name",
      "hypothesis": "If we change X then Y because Z",
      "control": "Original tagline",
      "variant": "Improved tagline",
      "target_metric": "What to measure",
      "expected_lift": "e.g., 5-15% improvement in recall",
      "min_sample_size": <int>,
      "recommended_duration_days": <int>,
      "risk_level": "low | medium | high"
    }}
  ],
  "testing_priority": "Which test to run first and why"
}}

Return ONLY valid JSON."""

    response = await logged_chat_completion(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        response_format={"type": "json_object"},
        caller="ab_test.generate",
    )
    return json.loads(response.choices[0].message.content)


async def ab_test_generator_node(state: dict) -> dict:
    """LangGraph node: generates A/B test plans from improvement suggestions."""
    log.info("⚙ ab_test_generator_node ENTER")
    t0 = time.perf_counter()
    brand_input = BrandInput(**state["brand_input"]) if isinstance(state["brand_input"], dict) else state["brand_input"]
    suggestions = state.get("suggestions", [])
    if suggestions and isinstance(suggestions[0], dict):
        suggestions = [ImprovementSuggestion(**s) for s in suggestions]
    result = await generate_ab_tests(brand_input, suggestions)
    log.info("⚙ ab_test_generator_node EXIT  %.1fs  tests=%d", time.perf_counter() - t0, len(result.get("ab_tests", [])))
    return {"ab_test_data": result}
