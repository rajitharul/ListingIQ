"""
Content Improvement (Chat) Agent
Provides surgical, dimension-targeted recommendations to boost specific scores.
"""
import json
import logging
import time
from config import OPENAI_MODEL
from models.schemas import (
    BrandInput,
    EvaluationResult,
    ImprovementSuggestion,
    MemoryEntry,
)
from agents.llm_client import get_openai_client, logged_chat_completion

log = logging.getLogger("sitescore.agent.improvement")


async def suggest_improvements(
    brand_input: BrandInput,
    evaluation: EvaluationResult,
    target_dimension: str | None = None,
    memory_context: list[MemoryEntry] | None = None,
) -> list[ImprovementSuggestion]:
    """Generate targeted improvement suggestions for the weakest dimensions."""

    user_scores = evaluation.user_score.dimension_scores
    if target_dimension:
        weak_dims = [ds for ds in user_scores if ds.dimension == target_dimension]
    else:
        # Auto-select the 3 weakest dimensions
        sorted_scores = sorted(user_scores, key=lambda x: x.score)
        weak_dims = sorted_scores[:3]

    memory_guidelines = ""
    if memory_context:
        memory_guidelines = (
            "\n\nBRAND GUIDELINES FROM MEMORY (must respect these):\n"
            + "\n".join(
                f"- {m.guideline} (source: {m.source}, confidence: {m.confidence})"
                for m in memory_context
            )
        )

    competitor_context = "\n".join(
        f'- {cs.brand_name} ({cs.overall_score}/10): "{cs.tagline}"'
        for cs in evaluation.competitor_scores
    )

    dims_to_improve = "\n".join(
        f"- {ds.dimension}: current score {ds.score}/10 -- Weaknesses: {', '.join(ds.weaknesses) or 'None noted'}"
        for ds in weak_dims
    )

    prompt = f"""You are an elite marketing copy surgeon. Your task is to make PRECISE, SURGICAL edits to a tagline to improve specific dimensional scores.

CURRENT TAGLINE: "{brand_input.current_tagline}"
BRAND: {brand_input.brand_name} ({brand_input.product_category})
TARGET AUDIENCE: {brand_input.target_audience or "General consumer"}

COMPETITOR CONTEXT:
{competitor_context}

BENCHMARK (perfect tagline): "{evaluation.benchmark.ideal_tagline}"

DIMENSIONS TO IMPROVE:
{dims_to_improve}
{memory_guidelines}

RULES:
1. Make the MINIMUM changes needed to boost each dimension
2. Show exactly what words/phrases to remove and add
3. Quantify the projected score improvement
4. Flag any trade-offs (improving one dimension that might hurt another)
5. Each suggestion should be independently applicable

Return a JSON object:
{{
  "suggestions": [
    {{
      "target_dimension": "DimensionName",
      "current_score": 6.1,
      "projected_score": 8.2,
      "original_text": "original tagline",
      "improved_text": "improved tagline",
      "changes_made": ["Replaced 'X' with 'Y' to increase Z", "Added alliteration for memorability"],
      "trade_offs": ["May slightly reduce Clarity score by 0.2 due to added complexity"]
    }}
  ]
}}

Return ONLY valid JSON."""

    response = await logged_chat_completion(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
        response_format={"type": "json_object"},
        caller="improvement.suggest",
    )
    data = json.loads(response.choices[0].message.content)
    return [ImprovementSuggestion(**s) for s in data.get("suggestions", [])]


# ── LangGraph node wrapper ────────────────────────────────────
async def improvement_node(state: dict) -> dict:
    """LangGraph node: generates targeted improvement suggestions."""
    log.info("⚙ improvement_node ENTER")
    t0 = time.perf_counter()
    brand_input = BrandInput(**state["brand_input"]) if isinstance(state["brand_input"], dict) else state["brand_input"]
    evaluation = state["evaluation"]
    memory_context = state.get("memory_context", [])
    suggestions = await suggest_improvements(
        brand_input, evaluation, memory_context=memory_context
    )
    log.info("⚙ improvement_node EXIT  %.1fs  suggestions=%d", time.perf_counter() - t0, len(suggestions))
    return {"suggestions": suggestions}
