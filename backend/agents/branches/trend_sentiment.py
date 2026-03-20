"""
Trend & Sentiment Branch Agent
Gathers real-time market signals using Google Trends (pytrends) and NewsAPI,
then synthesises them into a TrendAnalysisResult that feeds downstream agents.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from functools import partial

from config import OPENAI_MODEL, NEWSAPI_KEY
from models.schemas import (
    BrandInput,
    CompetitorAnalysisResult,
    CompetitorTrend,
    TrendAnalysisResult,
)
from agents.llm_client import logged_chat_completion

log = logging.getLogger("sitescore.agent.trend_sentiment")

# ── Google Trends helper ──────────────────────────────────────
def _fetch_google_trends(keywords: list[str]) -> dict[str, float]:
    """Fetch relative interest scores from Google Trends (blocking I/O)."""
    try:
        from pytrends.request import TrendReq

        pytrends = TrendReq(hl="en-US", tz=360, timeout=(10, 25))
        # Limit to 5 keywords (API max)
        kws = keywords[:5]
        pytrends.build_payload(kws, timeframe="today 3-m")
        df = pytrends.interest_over_time()
        if df.empty:
            return {kw: 0.0 for kw in kws}
        # Return average interest per keyword over the period
        result = {}
        for kw in kws:
            if kw in df.columns:
                result[kw] = round(float(df[kw].mean()), 1)
            else:
                result[kw] = 0.0
        return result
    except Exception as e:
        log.warning("Google Trends fetch failed: %s — returning zeros", e)
        return {kw: 0.0 for kw in keywords[:5]}


# ── NewsAPI helper ────────────────────────────────────────────
def _fetch_news_headlines(query: str, max_articles: int = 5) -> list[str]:
    """Fetch recent headlines about a brand from NewsAPI (blocking I/O)."""
    if not NEWSAPI_KEY:
        log.info("No NEWSAPI_KEY set — skipping news fetch for '%s'", query)
        return []
    try:
        from newsapi import NewsApiClient

        newsapi = NewsApiClient(api_key=NEWSAPI_KEY)
        resp = newsapi.get_everything(
            q=query,
            language="en",
            sort_by="publishedAt",
            page_size=max_articles,
        )
        return [a["title"] for a in resp.get("articles", []) if a.get("title")]
    except Exception as e:
        log.warning("NewsAPI fetch failed for '%s': %s", query, e)
        return []


# ── Core analysis function ────────────────────────────────────
async def analyze_trends(
    brand_input: BrandInput,
    competitor_result: CompetitorAnalysisResult,
) -> TrendAnalysisResult:
    """Gather trend + sentiment data for the brand and its competitors, then synthesise."""

    brand_name = brand_input.brand_name
    comp_names = [c.name for c in competitor_result.competitors]
    all_names = [brand_name] + comp_names

    loop = asyncio.get_running_loop()

    # Run blocking I/O in threads concurrently
    trends_future = loop.run_in_executor(None, partial(_fetch_google_trends, all_names))
    news_futures = {
        name: loop.run_in_executor(None, partial(_fetch_news_headlines, name))
        for name in all_names
    }

    trends_scores = await trends_future
    news_by_brand: dict[str, list[str]] = {}
    for name, fut in news_futures.items():
        news_by_brand[name] = await fut

    # Use LLM to synthesise trend data + headlines into sentiment + insights
    news_context = ""
    for name in all_names:
        headlines = news_by_brand.get(name, [])
        hl_str = "\n    ".join(headlines[:5]) if headlines else "(no recent headlines)"
        interest = trends_scores.get(name, 0.0)
        news_context += f"\n  {name} (Google Trends interest: {interest}):\n    {hl_str}\n"

    prompt = f"""You are a market intelligence analyst. Analyse the following trend and news data for a brand and its competitors, then provide a structured assessment.

BRAND: {brand_name}
CATEGORY: {brand_input.product_category}
COMPETITORS: {', '.join(comp_names)}

TREND & NEWS DATA:{news_context}

Return a JSON object:
{{
  "brand_trend": {{
    "competitor_name": "{brand_name}",
    "search_interest": <0-100 float>,
    "trend_direction": "rising | declining | stable",
    "sentiment_score": <-1.0 to 1.0>,
    "recent_headlines": [<top 3 most relevant headlines>]
  }},
  "competitor_trends": [
    {{
      "competitor_name": "<name>",
      "search_interest": <0-100>,
      "trend_direction": "rising | declining | stable",
      "sentiment_score": <-1.0 to 1.0>,
      "recent_headlines": [<top 3>]
    }}
  ],
  "market_momentum": "1-2 sentence summary of overall market direction",
  "opportunities": ["opportunity 1", "opportunity 2"],
  "threats": ["threat 1", "threat 2"]
}}

Use the Google Trends interest scores provided. For sentiment, analyse the headline tone. Return ONLY valid JSON."""

    response = await logged_chat_completion(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        response_format={"type": "json_object"},
        caller="trend_sentiment.analyze",
    )
    data = json.loads(response.choices[0].message.content)

    brand_trend = CompetitorTrend(**data.get("brand_trend", {"competitor_name": brand_name}))
    comp_trends = [CompetitorTrend(**ct) for ct in data.get("competitor_trends", [])]

    return TrendAnalysisResult(
        brand_trend=brand_trend,
        competitor_trends=comp_trends,
        market_momentum=data.get("market_momentum", ""),
        opportunities=data.get("opportunities", []),
        threats=data.get("threats", []),
    )


# ── LangGraph node wrapper ────────────────────────────────────
async def trend_sentiment_node(state: dict) -> dict:
    """LangGraph node: gathers trend & sentiment data for brand + competitors."""
    log.info("⚙ trend_sentiment_node ENTER")
    t0 = time.perf_counter()

    brand_input = (
        BrandInput(**state["brand_input"])
        if isinstance(state["brand_input"], dict)
        else state["brand_input"]
    )
    competitor_result = state["competitor_result"]
    if isinstance(competitor_result, dict):
        competitor_result = CompetitorAnalysisResult(**competitor_result)

    result = await analyze_trends(brand_input, competitor_result)
    log.info(
        "⚙ trend_sentiment_node EXIT  %.1fs  brand_interest=%.0f  competitors=%d",
        time.perf_counter() - t0,
        result.brand_trend.search_interest,
        len(result.competitor_trends),
    )
    return {"trend_data": result}
