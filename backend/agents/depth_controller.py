"""
Depth Controller Meta-Agent
Analyses the brand input and determines the optimal pipeline depth and which
branch agents should activate. Runs BEFORE the main LangGraph pipeline.
"""
from __future__ import annotations

import json
import logging
from config import OPENAI_MODEL
from models.schemas import BrandInput, DepthConfig
from agents.llm_client import logged_chat_completion

log = logging.getLogger("sitescore.agent.depth_controller")


async def determine_depth(brand_input: BrandInput) -> DepthConfig:
    """Use GPT-4o to decide the optimal analysis depth for this brand."""

    prompt = f"""You are a pipeline orchestration agent for a marketing benchmarking system. Analyse the following brand input and decide what depth of analysis is appropriate.

BRAND: {brand_input.brand_name}
CATEGORY: {brand_input.product_category}
TAGLINE: "{brand_input.current_tagline}"
TARGET AUDIENCE: {brand_input.target_audience or "General consumer"}
DESCRIPTION: {brand_input.current_description or "(none)"}

DEPTH LEVELS:
- "quick": Basic analysis. Skip trend/sentiment data. Good for well-known brands with simple taglines in established categories.
- "standard": Full analysis including market trends and sentiment. Recommended for most brands.
- "deep": Maximum depth — trends, sentiment, and extended analysis. Best for new/niche brands, complex categories, or highly competitive markets.

DECIDE:
1. What depth_level is appropriate?
2. Should the trend & sentiment branch run? (enable_trends)

Return a JSON object:
{{
  "depth_level": "quick | standard | deep",
  "enable_trends": true | false,
  "reasoning": "Brief explanation of why this depth was chosen"
}}

Return ONLY valid JSON."""

    try:
        response = await logged_chat_completion(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            response_format={"type": "json_object"},
            caller="depth_controller.determine",
        )
        data = json.loads(response.choices[0].message.content)
        depth_level = data.get("depth_level", "standard")
        if depth_level not in ("quick", "standard", "deep"):
            depth_level = "standard"
        enable_trends = data.get("enable_trends", True)
        reasoning = data.get("reasoning", "")
        log.info(
            "Depth controller: level=%s, trends=%s — %s",
            depth_level,
            enable_trends,
            reasoning,
        )
        return DepthConfig(enable_trends=enable_trends, depth_level=depth_level, reasoning=reasoning)
    except Exception as e:
        log.error("Depth controller failed (%s) — defaulting to standard", e)
        return DepthConfig(enable_trends=True, depth_level="standard", reasoning=f"Fallback: {e}")
