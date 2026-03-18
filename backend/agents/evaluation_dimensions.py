"""
Evaluation Dimension Agent
Establishes the scoring dimensions used for benchmarking.
"""
from models.schemas import Dimension

DEFAULT_DIMENSIONS: list[Dimension] = [
    Dimension(
        name="Clarity",
        description="How immediately understandable is the message? Can a first-time reader grasp the core proposition in under 3 seconds?",
        weight=1.0,
    ),
    Dimension(
        name="Memorability",
        description="How sticky and recall-friendly is the tagline? Does it use rhythm, alliteration, or a unique hook that lodges in memory?",
        weight=1.0,
    ),
    Dimension(
        name="Emotional Resonance",
        description="Does the copy evoke a feeling -- joy, nostalgia, aspiration, comfort? How strong is the emotional pull?",
        weight=1.0,
    ),
    Dimension(
        name="Persuasiveness",
        description="Does the copy compel action? Does it create desire, urgency, or a clear reason to choose this product over alternatives?",
        weight=1.0,
    ),
    Dimension(
        name="Brand Alignment",
        description="How well does the tagline reinforce the brand's identity, values, and market positioning?",
        weight=1.0,
    ),
    Dimension(
        name="Differentiation",
        description="Does the copy clearly distinguish this brand from competitors? Does it own a unique space in the consumer's mind?",
        weight=1.0,
    ),
]


def get_dimensions(custom_dimensions: list[Dimension] | None = None) -> list[Dimension]:
    """Return the active set of dimensions, merging any custom ones."""
    if not custom_dimensions:
        return DEFAULT_DIMENSIONS

    # Merge: custom dimensions override defaults by name
    dim_map = {d.name: d for d in DEFAULT_DIMENSIONS}
    for cd in custom_dimensions:
        dim_map[cd.name] = cd
    return list(dim_map.values())


# ── LangGraph node wrapper ────────────────────────────────────
async def dimensions_node(state: dict) -> dict:
    """LangGraph node: resolves scoring dimensions."""
    import logging
    _log = logging.getLogger("sitescore.agent.dimensions")
    _log.info("⚙ dimensions_node ENTER")
    custom = state.get("custom_dimensions")
    if custom and len(custom) > 0:
        custom = [Dimension(**d) if isinstance(d, dict) else d for d in custom]
    else:
        custom = None
    dims = get_dimensions(custom)
    _log.info("⚙ dimensions_node EXIT  %d dimensions", len(dims))
    return {"dimensions": dims}
