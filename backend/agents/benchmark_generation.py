"""
Benchmark Content Generation Agent
Generates the theoretical "perfect 10/10" tagline to serve as the mathematical ceiling.
"""
import json
import logging
import time
from config import OPENAI_MODEL
from models.schemas import (
    BrandInput,
    Competitor,
    Dimension,
    BenchmarkSnippet,
    DimensionScore,
    TrendAnalysisResult,
)
from agents.llm_client import get_openai_client, logged_chat_completion

log = logging.getLogger("sitescore.agent.benchmark")


async def generate_benchmark(
    brand_input: BrandInput,
    competitors: list[Competitor],
    dimensions: list[Dimension],
    trend_context: str = "",
) -> BenchmarkSnippet:
    """Generate the ideal 10/10 benchmark tagline and description."""

    dim_descriptions = "\n".join(f"- {d.name}: {d.description}" for d in dimensions)
    comp_context = "\n".join(f'- {c.name}: "{c.tagline}"' for c in competitors)

    trend_section = ""
    if trend_context:
        trend_section = f"\n\nMARKET TREND INTELLIGENCE:\n{trend_context}\nUse these trends to inform what a PERFECT tagline would emphasise right now.\n"

    prompt = f"""You are the world's foremost marketing copywriter and linguistic analyst.

TASK: Create the theoretically PERFECT tagline and product description for the following brand that would score 10/10 on EVERY dimension below. This is the mathematical ceiling -- the north star benchmark.

BRAND: {brand_input.brand_name}
CATEGORY: {brand_input.product_category}
TARGET AUDIENCE: {brand_input.target_audience or "General consumer"}
CURRENT TAGLINE: "{brand_input.current_tagline}"

COMPETITOR TAGLINES (must clearly beat all of them):
{comp_context}

SCORING DIMENSIONS (must score 10/10 on each):
{dim_descriptions}
{trend_section}

Return a JSON object with:
{{
  "ideal_tagline": "...",
  "ideal_description": "2-3 sentence ideal product description",
  "rationale": "Brief explanation of why this achieves perfection across all dimensions",
  "dimension_scores": [
    {{"dimension": "DimName", "score": 10.0, "explanation": "Why this scores 10", "strengths": ["..."], "weaknesses": []}}
  ]
}}

Return ONLY valid JSON."""

    response = await logged_chat_completion(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        response_format={"type": "json_object"},
        caller="benchmark.generate",
    )
    data = json.loads(response.choices[0].message.content)

    dim_scores = [DimensionScore(**ds) for ds in data.get("dimension_scores", [])]
    # Ensure all dimensions are represented
    scored_dims = {ds.dimension for ds in dim_scores}
    for d in dimensions:
        if d.name not in scored_dims:
            dim_scores.append(
                DimensionScore(
                    dimension=d.name,
                    score=10.0,
                    explanation="Benchmark ceiling",
                    strengths=["Theoretical maximum"],
                    weaknesses=[],
                )
            )

    return BenchmarkSnippet(
        ideal_tagline=data.get("ideal_tagline", ""),
        ideal_description=data.get("ideal_description", ""),
        rationale=data.get("rationale", ""),
        dimension_scores=dim_scores,
    )


# ── LangGraph node wrapper ────────────────────────────────────
async def benchmark_node(state: dict) -> dict:
    """LangGraph node: generates the ideal 10/10 benchmark tagline."""
    log.info("⚙ benchmark_node ENTER")
    t0 = time.perf_counter()
    brand_input = BrandInput(**state["brand_input"]) if isinstance(state["brand_input"], dict) else state["brand_input"]
    competitors = state["competitor_result"].competitors if hasattr(state.get("competitor_result"), "competitors") else state["competitor_result"]["competitors"]
    if competitors and isinstance(competitors[0], dict):
        competitors = [Competitor(**c) for c in competitors]
    dimensions = state["dimensions"]
    if dimensions and isinstance(dimensions[0], dict):
        dimensions = [Dimension(**d) for d in dimensions]

    # Build trend context if available
    trend_ctx = ""
    trend_data = state.get("trend_data")
    if trend_data:
        td = trend_data if isinstance(trend_data, TrendAnalysisResult) else TrendAnalysisResult(**trend_data)
        trend_ctx = f"Market momentum: {td.market_momentum}\nOpportunities: {', '.join(td.opportunities)}\nThreats: {', '.join(td.threats)}"

    benchmark = await generate_benchmark(brand_input, competitors, dimensions, trend_context=trend_ctx)
    log.info("⚙ benchmark_node EXIT   %.1fs  tagline=\"%s\"", time.perf_counter() - t0, benchmark.ideal_tagline[:60])
    return {"benchmark": benchmark}
