"""
Competitor Analyzer Agent (Agent 4)
Extracts competitive patterns across the fetched competitor listings.

The model proposes what matters — which keywords, which claims count as the
same claim — and attributes each claim to specific competitors by rank. Every
frequency and every structural statistic is then computed in Python from the
listings themselves (see agents/competitor_stats.py).

This matters because those numbers are quoted to customers as evidence
("8/10 top competitors include this"). A model's estimate of a count it could
not verify is a fabricated statistic, however plausible it looks.
"""
from __future__ import annotations

import logging
import time
from models.schemas import (
    CompetitorListing,
    CompetitorScoutResult,
    ScoringRubric,
    CompetitorAnalysis,
    KeywordPattern,
    ClaimPattern,
)
from models.llm_responses import CompetitorAnalysisOut
from agents.competitor_stats import (
    count_keyword,
    structural_patterns,
    tally_by_rank,
)
from agents.llm_client import structured_completion

log = logging.getLogger("listingiq.agent.competitor_analyzer")


async def analyze_competitors(
    scout_result: CompetitorScoutResult,
    rubric: ScoringRubric,
) -> CompetitorAnalysis:
    """
    Extract competitive intelligence patterns from the competitor listings.

    Only listings whose page was actually read are analysed. Counting across
    competitors whose copy we never retrieved measures our extraction failures
    rather than the market: "1 of 10 competitors mention third-party testing"
    reads as a market gap when the truth may be that six of the nine we could
    not read do mention it. It also made the denominators disagree — frequencies
    over ten listings printed beside a benchmark averaged over three.
    """
    analysed = [l for l in scout_result.listings if l.counts_toward_benchmark]
    skipped = len(scout_result.listings) - len(analysed)
    if skipped:
        log.info("analysing %d of %d competitors — %d had no readable copy",
                 len(analysed), len(scout_result.listings), skipped)

    if not analysed:
        return CompetitorAnalysis(
            summary="No competitor pages could be read in full, so no competitive "
                    "patterns could be measured for this run.")

    listings_text = ""
    for i, listing in enumerate(analysed, 1):
        bullets = "\n    ".join(f"• {b}" for b in listing.bullet_points[:5])
        listings_text += f"""
LISTING {i}: {listing.brand_name} (Rank #{listing.rank}, {listing.rating}★, {listing.review_count} reviews, {listing.price})
  Title: {listing.title}
  Bullets:
    {bullets}
  Description: {listing.description[:200]}{'...' if len(listing.description) > 200 else ''}
  Badges: {', '.join(listing.badges) if listing.badges else 'None'}
"""

    dims_text = ", ".join(d.name for d in rubric.dimensions)

    prompt = f"""You are a competitive intelligence analyst. Analyze these {len(analysed)} competitor product listings and extract patterns.

{listings_text}

SCORING DIMENSIONS FOR THIS CATEGORY: {dims_text}

Analyze across ALL the listings above and extract:

1. keyword_patterns: Keywords and phrases that appear in MULTIPLE listings. Write each
   one EXACTLY as it literally appears in the listing text — it will be matched
   verbatim against the listings, so a paraphrase will find nothing. Prefer
   specific multi-word phrases ("third-party tested", "magnesium glycinate")
   over single generic words.

2. claim_patterns: Specific claims that appear across listings. For each, list the
   RANK NUMBERS of every competitor that makes it.

3. trust_signals: Certifications, badges, testing claims and trust markers. For each,
   list the RANK NUMBERS of every competitor showing it.

4. common_title_format: The dominant title pattern in one sentence.

5. differentiation_insights: 3-5 specific things the top listings do that the rest don't.

6. summary: A 3-sentence competitive landscape summary.

Do NOT report counts, frequencies, averages or lengths — those are measured
separately. Attribute by rank number and be accurate about WHICH competitors,
since the counts are derived from your attribution."""

    out = await structured_completion(
        response_model=CompetitorAnalysisOut,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_completion_tokens=4000,
        caller="competitor_analyzer.analyze",
    )

    listings = analysed

    # Keywords: counted exactly by matching the phrase on word boundaries.
    # A proposed keyword that appears in no listing is dropped rather than
    # reported with a frequency of zero.
    keyword_patterns = []
    for kp in out.keyword_patterns:
        freq, position = count_keyword(listings, kp.keyword)
        if freq > 0:
            keyword_patterns.append(
                KeywordPattern(keyword=kp.keyword, frequency=freq, position=position))
    keyword_patterns.sort(key=lambda k: -k.frequency)

    # Claims and trust signals: frequency is the size of the attribution, so it
    # can never exceed the number of competitors actually analysed.
    claim_patterns = []
    for cp in out.claim_patterns:
        freq, brands = tally_by_rank(listings, cp.competitor_ranks)
        if freq > 0:
            claim_patterns.append(ClaimPattern(
                claim=cp.claim, frequency=freq,
                example_brand=brands[0], brands=brands))
    claim_patterns.sort(key=lambda c: -c.frequency)

    trust_signals = []
    for ts in out.trust_signals:
        freq, brands = tally_by_rank(listings, ts.competitor_ranks)
        if freq > 0:
            trust_signals.append({"signal": ts.signal, "frequency": freq, "brands": brands})
    trust_signals.sort(key=lambda t: -t["frequency"])

    # Structural statistics are pure arithmetic over the listing text.
    structural = structural_patterns(listings)
    structural["common_title_format"] = out.common_title_format

    log.info("counted %d keywords, %d claims, %d trust signals over %d listings",
             len(keyword_patterns), len(claim_patterns), len(trust_signals), len(listings))

    return CompetitorAnalysis(
        keyword_patterns=keyword_patterns,
        claim_patterns=claim_patterns,
        trust_signals=trust_signals,
        structural_patterns=structural,
        differentiation_insights=out.differentiation_insights,
        summary=out.summary,
    )


# ── LangGraph node wrapper ────────────────────────────────────
async def competitor_analyzer_node(state: dict) -> dict:
    """LangGraph node: analyzes patterns across competitor listings."""
    log.info("⚙ competitor_analyzer_node ENTER")
    t0 = time.perf_counter()

    scout_result = state["competitor_scout_result"]
    if isinstance(scout_result, dict):
        scout_result = CompetitorScoutResult(**scout_result)

    rubric = state["rubric"]
    if isinstance(rubric, dict):
        rubric = ScoringRubric(**rubric)

    result = await analyze_competitors(scout_result, rubric)
    log.info(
        "⚙ competitor_analyzer_node EXIT  %.1fs  keywords=%d  claims=%d  trust=%d",
        time.perf_counter() - t0,
        len(result.keyword_patterns),
        len(result.claim_patterns),
        len(result.trust_signals),
    )
    return {"competitor_analysis": result}
