"""
Brand Voice Profiler Branch Agent
Analyses competitor taglines to profile their brand voice, tone, and messaging strategy.
Feeds into benchmark and evaluator with deeper competitive understanding.
"""
from __future__ import annotations

import json
import logging
import time
from config import OPENAI_MODEL
from models.schemas import BrandInput, CompetitorAnalysisResult
from agents.llm_client import logged_chat_completion

log = logging.getLogger("sitescore.branch.brand_voice")


async def profile_brand_voices(
    brand_input: BrandInput,
    competitor_result: CompetitorAnalysisResult,
) -> dict:
    """Profile brand voice characteristics for the user brand and competitors."""
    comp_context = "\n".join(
        f'- {c.name}: "{c.tagline}" — {c.description}' for c in competitor_result.competitors
    )

    prompt = f"""You are a brand strategist specialising in voice and tone analysis.

Analyse the brand voice of the following brand and its competitors. For each, identify the voice archetype, tone, key linguistic patterns, and messaging strategy.

BRAND: {brand_input.brand_name}
TAGLINE: "{brand_input.current_tagline}"
CATEGORY: {brand_input.product_category}

COMPETITORS:
{comp_context}

Return a JSON object:
{{
  "brand_profile": {{
    "voice_archetype": "e.g., Friendly Guide, Bold Challenger, Trusted Authority",
    "tone": "e.g., warm, playful, authoritative, urgent",
    "linguistic_patterns": ["pattern 1", "pattern 2"],
    "messaging_strategy": "1-2 sentence summary"
  }},
  "competitor_profiles": [
    {{
      "name": "CompetitorName",
      "voice_archetype": "...",
      "tone": "...",
      "linguistic_patterns": ["..."],
      "messaging_strategy": "..."
    }}
  ],
  "voice_gap": "Key differentiation opportunity in brand voice"
}}

Return ONLY valid JSON."""

    response = await logged_chat_completion(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        response_format={"type": "json_object"},
        caller="brand_voice.profile",
    )
    return json.loads(response.choices[0].message.content)


async def brand_voice_profiler_node(state: dict) -> dict:
    """LangGraph node: profiles brand voice for user and competitors."""
    log.info("⚙ brand_voice_profiler_node ENTER")
    t0 = time.perf_counter()
    brand_input = BrandInput(**state["brand_input"]) if isinstance(state["brand_input"], dict) else state["brand_input"]
    competitor_result = state["competitor_result"]
    if isinstance(competitor_result, dict):
        competitor_result = CompetitorAnalysisResult(**competitor_result)
    result = await profile_brand_voices(brand_input, competitor_result)
    log.info("⚙ brand_voice_profiler_node EXIT  %.1fs", time.perf_counter() - t0)
    return {"brand_voice_data": result}
