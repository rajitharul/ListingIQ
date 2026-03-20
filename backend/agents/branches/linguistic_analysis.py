"""
Linguistic Analysis Branch Agent
Deep linguistic and structural analysis of taglines — phonetics, rhythm,
rhetorical devices, readability, and memorability mechanics.
"""
from __future__ import annotations

import json
import logging
import time
from config import OPENAI_MODEL
from models.schemas import BrandInput, BenchmarkSnippet
from agents.llm_client import logged_chat_completion

log = logging.getLogger("sitescore.branch.linguistic")


async def analyze_linguistics(
    brand_input: BrandInput,
    benchmark: BenchmarkSnippet,
) -> dict:
    """Perform deep linguistic analysis on user and benchmark taglines."""

    prompt = f"""You are a computational linguist specialising in marketing copy analysis.

Perform a deep linguistic analysis comparing the current tagline against the benchmark.

CURRENT: "{brand_input.current_tagline}"
BENCHMARK: "{benchmark.ideal_tagline}"
BRAND: {brand_input.brand_name}

Analyse:
1. Phonetic qualities (alliteration, assonance, consonance, rhyme)
2. Rhythm and meter (syllable count, stress patterns)
3. Rhetorical devices (metaphor, parallelism, antithesis, etc.)
4. Readability (Flesch score estimate, grade level)
5. Memorability mechanics (hook, repetition, surprise element)

Return a JSON object:
{{
  "current_analysis": {{
    "syllable_count": <int>,
    "word_count": <int>,
    "phonetic_devices": ["device: example"],
    "rhetorical_devices": ["device: explanation"],
    "readability_grade": "e.g., Grade 4",
    "memorability_score": <0-10>,
    "strengths": ["..."],
    "weaknesses": ["..."]
  }},
  "benchmark_analysis": {{
    "syllable_count": <int>,
    "word_count": <int>,
    "phonetic_devices": ["..."],
    "rhetorical_devices": ["..."],
    "readability_grade": "...",
    "memorability_score": <0-10>
  }},
  "linguistic_recommendations": ["recommendation 1", "recommendation 2"]
}}

Return ONLY valid JSON."""

    response = await logged_chat_completion(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        response_format={"type": "json_object"},
        caller="linguistic.analyze",
    )
    return json.loads(response.choices[0].message.content)


async def linguistic_analysis_node(state: dict) -> dict:
    """LangGraph node: deep linguistic analysis of taglines."""
    log.info("⚙ linguistic_analysis_node ENTER")
    t0 = time.perf_counter()
    brand_input = BrandInput(**state["brand_input"]) if isinstance(state["brand_input"], dict) else state["brand_input"]
    benchmark = state["benchmark"]
    if isinstance(benchmark, dict):
        benchmark = BenchmarkSnippet(**benchmark)
    result = await analyze_linguistics(brand_input, benchmark)
    log.info("⚙ linguistic_analysis_node EXIT  %.1fs", time.perf_counter() - t0)
    return {"linguistic_data": result}
