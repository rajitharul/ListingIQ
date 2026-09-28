"""
Input Parser Agent (Agent 1)
Normalizes text, extracts entities (product type, ingredients, certifications,
dosage, claims, format), and detects platform.
"""
from __future__ import annotations

import logging
import time
from providers import platforms
from models.schemas import ListingInput, ParsedListing, ExtractedEntities
from models.llm_responses import ExtractedEntitiesOut
from agents.llm_client import structured_completion

log = logging.getLogger("listingiq.agent.input_parser")


def resolve_platform(listing_input: ListingInput) -> str:
    """
    Turn "auto" into a real platform before anything downstream reads it.

    `/api/extract` resolves it when the user pastes a URL, but a listing
    submitted with the selector left on "auto" carried that string all the way
    into the pipeline — where `canonical("auto")` is `"generic"`, so the
    same-platform cohort matched nothing and the thin-cohort fallback fired on
    every run regardless of what was found. The report even displayed the
    platform as "auto".

    An explicit choice always wins. Otherwise the listing's own URL decides,
    and with no URL there is genuinely nothing to detect.
    """
    chosen = (listing_input.platform or "").strip().lower()
    if chosen and chosen != "auto":
        return chosen
    if listing_input.listing_url:
        return platforms.detect(listing_input.listing_url)
    return "generic"


async def parse_listing(listing_input: ListingInput) -> ParsedListing:
    """Normalize and extract entities from a raw product listing."""

    bullets_text = "\n".join(f"- {b}" for b in listing_input.bullet_points) if listing_input.bullet_points else "(no bullet points)"

    prompt = f"""You are a product listing parsing agent. Analyze this ecommerce product listing and extract structured entities.

PRODUCT TITLE: {listing_input.product_title}

BULLET POINTS:
{bullets_text}

DESCRIPTION:
{listing_input.product_description or "(no description)"}

BRAND: {listing_input.brand_name or "(not specified)"}
PLATFORM: {listing_input.platform}

Extract the following entities from the listing:

1. product_type: The normalized product type (e.g., "Magnesium Glycinate Supplement", "Vitamin C Serum", "Creatine Monohydrate Powder")
2. ingredients: List of ingredients, active compounds, or key components mentioned
3. certifications: List of certifications mentioned (USP, NSF, GMP, organic, vegan, cruelty-free, etc.)
4. dosage_info: Dosage, serving size, concentration, or quantity information
5. target_audience: Target audience if mentioned or implied (e.g., "women 30+", "athletes", "sensitive skin")
6. claims: List of health, benefit, or performance claims made
7. format_type: Product format (capsules, powder, serum, cream, tablets, softgels, gummies, etc.)

Be thorough — extract EVERY ingredient, certification, and claim mentioned anywhere in the listing."""

    out = await structured_completion(
        response_model=ExtractedEntitiesOut,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_completion_tokens=2000,
        caller="input_parser.parse",
    )

    entities = ExtractedEntities(
        product_type=out.product_type,
        ingredients=out.ingredients,
        certifications=out.certifications,
        dosage_info=out.dosage_info,
        target_audience=out.target_audience or listing_input.target_audience,
        claims=out.claims,
        format_type=out.format_type,
    )

    return ParsedListing(
        original_title=listing_input.product_title,
        original_description=listing_input.product_description,
        original_bullets=listing_input.bullet_points,
        brand_name=listing_input.brand_name,
        platform=resolve_platform(listing_input),
        extracted_entities=entities,
    )


# ── LangGraph node wrapper ────────────────────────────────────
async def input_parser_node(state: dict) -> dict:
    """LangGraph node: parses and normalizes the product listing."""
    log.info("⚙ input_parser_node ENTER")
    t0 = time.perf_counter()

    li = state["listing_input"]
    listing_input = ListingInput(**li) if isinstance(li, dict) else li

    result = await parse_listing(listing_input)
    log.info(
        "⚙ input_parser_node EXIT  %.1fs  product_type=%s  entities=%d ingredients, %d certs, %d claims",
        time.perf_counter() - t0,
        result.extracted_entities.product_type,
        len(result.extracted_entities.ingredients),
        len(result.extracted_entities.certifications),
        len(result.extracted_entities.claims),
    )
    return {"parsed_listing": result}
