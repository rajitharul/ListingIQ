"""
Implementation Roadmap Branch Agent
Creates a step-by-step implementation plan from improvement suggestions,
with timeline, resources, and risk mitigation strategies.
"""
from __future__ import annotations

import json
import logging
import time
from config import OPENAI_MODEL
from models.schemas import BrandInput, ImprovementSuggestion
from agents.llm_client import logged_chat_completion

log = logging.getLogger("sitescore.branch.roadmap")


async def generate_roadmap(
    brand_input: BrandInput,
    suggestions: list[ImprovementSuggestion],
) -> dict:
    """Create an implementation roadmap from improvement suggestions."""
    suggestion_context = "\n".join(
        f'- {s.target_dimension}: "{s.improved_text}" (projected {s.projected_score}/10)\n  Changes: {", ".join(s.changes_made)}\n  Trade-offs: {", ".join(s.trade_offs) or "None"}'
        for s in suggestions
    )

    prompt = f"""You are a marketing operations strategist who creates implementation roadmaps.

Given the following tagline improvements, create a phased implementation roadmap.

BRAND: {brand_input.brand_name}
CATEGORY: {brand_input.product_category}

APPROVED IMPROVEMENTS:
{suggestion_context}

Return a JSON object:
{{
  "phases": [
    {{
      "phase": 1,
      "name": "Phase name",
      "duration": "e.g., Week 1-2",
      "actions": ["action 1", "action 2"],
      "deliverables": ["deliverable 1"],
      "success_criteria": "How to measure success"
    }}
  ],
  "rollback_plan": "What to do if the changes don't perform",
  "total_timeline": "e.g., 4-6 weeks",
  "key_risks": ["risk 1", "risk 2"],
  "stakeholders": ["who needs to approve/review"]
}}

Return ONLY valid JSON."""

    response = await logged_chat_completion(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        response_format={"type": "json_object"},
        caller="roadmap.generate",
    )
    return json.loads(response.choices[0].message.content)


async def implementation_roadmap_node(state: dict) -> dict:
    """LangGraph node: creates implementation roadmap."""
    log.info("⚙ implementation_roadmap_node ENTER")
    t0 = time.perf_counter()
    brand_input = BrandInput(**state["brand_input"]) if isinstance(state["brand_input"], dict) else state["brand_input"]
    suggestions = state.get("suggestions", [])
    if suggestions and isinstance(suggestions[0], dict):
        suggestions = [ImprovementSuggestion(**s) for s in suggestions]
    result = await generate_roadmap(brand_input, suggestions)
    log.info("⚙ implementation_roadmap_node EXIT  %.1fs", time.perf_counter() - t0)
    return {"roadmap_data": result}
