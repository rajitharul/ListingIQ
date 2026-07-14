"""
Input Parser Agent (Agent 1)
Normalizes text, extracts entities (product type, ingredients, certifications,
dosage, claims, format), and detects platform.
"""
from __future__ import annotations

import json
import logging
import time
from config import OPENAI_MODEL
from models.schemas import ListingInput, ParsedListing, ExtractedEntities
from agents.llm_client import logged_chat_completion

log = logging.getLogger("listingiq.agent.input_parser")


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

Return a JSON object:
{{
  "product_type": "...",
  "ingredients": ["..."],
  "certifications": ["..."],
  "dosage_info": "...",
  "target_audience": "...",
  "claims": ["..."],
  "format_type": "..."
}}

Be thorough — extract EVERY ingredient, certification, and claim mentioned anywhere in the listing.
Return ONLY valid JSON."""

    response = await logged_chat_completion(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        response_format={"type": "json_object"},
        caller="input_parser.parse",
    )
    data = json.loads(response.choices[0].message.content)

    entities = ExtractedEntities(
        product_type=data.get("product_type", ""),
        ingredients=data.get("ingredients", []),
        certifications=data.get("certifications", []),
        dosage_info=data.get("dosage_info", ""),
        target_audience=data.get("target_audience", listing_input.target_audience),
        claims=data.get("claims", []),
        format_type=data.get("format_type", ""),
    )

    return ParsedListing(
        original_title=listing_input.product_title,
        original_description=listing_input.product_description,
        original_bullets=listing_input.bullet_points,
        brand_name=listing_input.brand_name,
        platform=listing_input.platform,
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
