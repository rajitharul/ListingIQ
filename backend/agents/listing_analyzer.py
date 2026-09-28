"""
Listing Analyzer Agent (Agent 5)
Parses the user's listing against every dimension in the scoring rubric,
extracting what's present, what's missing, and how completely each dimension is covered.
"""
from __future__ import annotations

import logging
import time
from models.schemas import (
    ParsedListing,
    ScoringRubric,
    ListingAnalysis,
    DimensionExtraction,
)
from models.llm_responses import ListingAnalysisOut, clamp
from agents.llm_client import structured_completion

log = logging.getLogger("listingiq.agent.listing_analyzer")


async def analyze_listing(
    parsed: ParsedListing,
    rubric: ScoringRubric,
) -> ListingAnalysis:
    """Analyze the user's listing against every rubric dimension."""

    bullets_text = "\n".join(f"- {b}" for b in parsed.original_bullets) if parsed.original_bullets else "(no bullet points)"
    dims_text = "\n".join(
        f"- {d.name} (weight: {d.weight}): {d.description}"
        for d in rubric.dimensions
    )

    prompt = f"""You are a product listing analysis agent. Examine this product listing against each scoring dimension and extract what the listing says (or doesn't say) for each one.

PRODUCT TITLE: {parsed.original_title}

BULLET POINTS:
{bullets_text}

DESCRIPTION:
{parsed.original_description or "(no description)"}

BRAND: {parsed.brand_name}

SCORING DIMENSIONS TO ANALYZE:
{dims_text}

For EACH dimension, determine:
1. present (bool): Is this dimension addressed AT ALL in the listing?
2. extracted_value: What specific information does the listing provide for this dimension? Be precise.
3. evidence: Direct quote from the listing that addresses this dimension (empty string if not present)
4. completeness (0.0 to 1.0): How completely does the listing cover this dimension?
   - 0.0 = not mentioned at all
   - 0.3 = vaguely or partially mentioned
   - 0.6 = mentioned but lacking detail
   - 0.8 = well covered
   - 1.0 = thoroughly and comprehensively covered

Return one entry per dimension listed above, in the same order.
Be strict and honest. If the listing does NOT mention something, mark it as not present. Do not infer information that isn't explicitly stated."""

    out = await structured_completion(
        response_model=ListingAnalysisOut,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_completion_tokens=4000,
        caller="listing_analyzer.analyze",
    )

    extractions = [
        DimensionExtraction(
            dimension_name=item.dimension_name,
            present=item.present,
            extracted_value=item.extracted_value,
            evidence=item.evidence,
            completeness=clamp(item.completeness, 0.0, 1.0),
        )
        for item in out.dimensions
    ]

    present = [e.dimension_name for e in extractions if e.present]
    missing = [e.dimension_name for e in extractions if not e.present]
    overall = sum(e.completeness for e in extractions) / len(extractions) if extractions else 0.0

    return ListingAnalysis(
        dimensions=extractions,
        overall_completeness=round(overall, 2),
        missing_dimensions=missing,
        present_dimensions=present,
    )


# ── LangGraph node wrapper ────────────────────────────────────
async def listing_analyzer_node(state: dict) -> dict:
    """LangGraph node: analyzes user's listing against rubric dimensions."""
    log.info("⚙ listing_analyzer_node ENTER")
    t0 = time.perf_counter()

    parsed = state["parsed_listing"]
    if isinstance(parsed, dict):
        parsed = ParsedListing(**parsed)

    rubric = state["rubric"]
    if isinstance(rubric, dict):
        rubric = ScoringRubric(**rubric)

    result = await analyze_listing(parsed, rubric)
    log.info(
        "⚙ listing_analyzer_node EXIT  %.1fs  completeness=%.0f%%  present=%d  missing=%d",
        time.perf_counter() - t0,
        result.overall_completeness * 100,
        len(result.present_dimensions),
        len(result.missing_dimensions),
    )
    return {"listing_analysis": result}
