"""
Evaluator Scoring Agent
The core mathematical benchmarking engine -- scores all content across all dimensions.
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
    ContentScore,
    DimensionScore,
    EvaluationResult,
    TrendAnalysisResult,
)
from agents.llm_client import get_openai_client, logged_chat_completion

log = logging.getLogger("sitescore.agent.evaluator")


async def evaluate_all(
    brand_input: BrandInput,
    competitors: list[Competitor],
    dimensions: list[Dimension],
    benchmark: BenchmarkSnippet,
    trend_context: str = "",
) -> EvaluationResult:
    """Score the user's content + all competitors across every dimension."""

    # Build the list of all taglines to evaluate
    entries = [
        {"brand": brand_input.brand_name, "tagline": brand_input.current_tagline, "is_user": True},
    ] + [
        {"brand": c.name, "tagline": c.tagline, "is_user": False}
        for c in competitors
    ]

    dim_list = "\n".join(f"- {d.name}: {d.description}" for d in dimensions)
    tagline_list = "\n".join(
        f'{i+1}. {e["brand"]}: "{e["tagline"]}"' for i, e in enumerate(entries)
    )

    prompt = f"""You are a quantitative marketing evaluation engine. You must produce CONSISTENT, DETERMINISTIC numerical scores.

TASK: Score each tagline below on every dimension using a 0.0-10.0 scale (one decimal place). The benchmark tagline represents a perfect 10.0 on all dimensions.

BENCHMARK (10/10 ceiling):
"{benchmark.ideal_tagline}"

TAGLINES TO EVALUATE:
{tagline_list}

DIMENSIONS:
{dim_list}

SCORING RULES:
1. Scores must use exactly one decimal place (e.g., 7.3, not 7 or 7.31)
2. No tagline should score above 9.5 (the benchmark is 10.0)
3. Be discriminating -- create meaningful spread between competitors
4. Consider the RELATIVE performance: who is strongest in each dimension?
5. Provide specific evidence for each score

{f"MARKET TREND CONTEXT (use as scoring modifier):{chr(10)}{trend_context}{chr(10)}Brands riding positive trends should get a slight boost; those facing headwinds a slight penalty.{chr(10)}" if trend_context else ""}Return a JSON object:
{{
  "scores": [
    {{
      "brand_name": "BrandName",
      "tagline": "the tagline",
      "dimension_scores": [
        {{
          "dimension": "DimName",
          "score": 7.3,
          "explanation": "Specific reason for this score",
          "strengths": ["strength 1"],
          "weaknesses": ["weakness 1"]
        }}
      ],
      "overall_score": 0.0
    }}
  ],
  "insights": ["Key insight 1 about competitive positioning", "Key insight 2", "Key insight 3"]
}}

IMPORTANT: overall_score should be the weighted average across all dimensions. Return ONLY valid JSON."""

    response = await logged_chat_completion(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        response_format={"type": "json_object"},
        caller="evaluator.score",
    )
    data = json.loads(response.choices[0].message.content)

    all_scores: list[ContentScore] = []
    for s in data.get("scores", []):
        dim_scores = [DimensionScore(**ds) for ds in s.get("dimension_scores", [])]
        overall = s.get("overall_score", 0.0)
        if overall == 0.0 and dim_scores:
            # Calculate weighted average
            total_weight = sum(d.weight for d in dimensions)
            weighted_sum = 0.0
            for ds in dim_scores:
                dim_obj = next((d for d in dimensions if d.name == ds.dimension), None)
                w = dim_obj.weight if dim_obj else 1.0
                weighted_sum += ds.score * w
            overall = round(weighted_sum / total_weight, 1) if total_weight else 0.0

        all_scores.append(
            ContentScore(
                brand_name=s["brand_name"],
                tagline=s["tagline"],
                dimension_scores=dim_scores,
                overall_score=overall,
            )
        )

    # Rank them
    all_scores.sort(key=lambda x: x.overall_score, reverse=True)
    for i, cs in enumerate(all_scores):
        cs.rank = i + 1

    # Separate user vs competitors
    user_score = next(
        (s for s in all_scores if s.brand_name == brand_input.brand_name),
        all_scores[0],
    )
    competitor_scores = [s for s in all_scores if s.brand_name != brand_input.brand_name]

    rankings = [
        {"brand": s.brand_name, "score": s.overall_score, "rank": s.rank}
        for s in all_scores
    ]

    return EvaluationResult(
        user_score=user_score,
        competitor_scores=competitor_scores,
        benchmark=benchmark,
        dimensions=dimensions,
        rankings=rankings,
        insights=data.get("insights", []),
    )


# ── LangGraph node wrapper ────────────────────────────────────
async def evaluator_node(state: dict) -> dict:
    """LangGraph node: scores all taglines across every dimension."""
    log.info("⚙ evaluator_node ENTER")
    t0 = time.perf_counter()
    brand_input = BrandInput(**state["brand_input"]) if isinstance(state["brand_input"], dict) else state["brand_input"]
    competitors = state["competitor_result"].competitors if hasattr(state.get("competitor_result"), "competitors") else state["competitor_result"]["competitors"]
    if competitors and isinstance(competitors[0], dict):
        competitors = [Competitor(**c) for c in competitors]
    dimensions = state["dimensions"]
    if dimensions and isinstance(dimensions[0], dict):
        dimensions = [Dimension(**d) for d in dimensions]
    benchmark = state["benchmark"]
    if isinstance(benchmark, dict):
        from models.schemas import DimensionScore as DS
        benchmark = BenchmarkSnippet(**{**benchmark, "dimension_scores": [DS(**ds) if isinstance(ds, dict) else ds for ds in benchmark.get("dimension_scores", [])]})

    # Build trend context if available
    trend_ctx = ""
    trend_data = state.get("trend_data")
    if trend_data:
        td = trend_data if isinstance(trend_data, TrendAnalysisResult) else TrendAnalysisResult(**trend_data)
        lines = [f"Brand '{td.brand_trend.competitor_name}': interest={td.brand_trend.search_interest}, direction={td.brand_trend.trend_direction}, sentiment={td.brand_trend.sentiment_score}"]
        for ct in td.competitor_trends:
            lines.append(f"'{ct.competitor_name}': interest={ct.search_interest}, direction={ct.trend_direction}, sentiment={ct.sentiment_score}")
        trend_ctx = "\n".join(lines)

    evaluation = await evaluate_all(brand_input, competitors, dimensions, benchmark, trend_context=trend_ctx)
    log.info("⚙ evaluator_node EXIT   %.1fs  user_score=%.1f  rank=#%d", time.perf_counter() - t0, evaluation.user_score.overall_score, evaluation.user_score.rank)
    return {"evaluation": evaluation}
