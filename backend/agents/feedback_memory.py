"""
Feedback & Memory Agent
Manages persistent agentic memory — stores feedback, guidelines, and learned preferences.
In production this would use a vector DB or Cosmos DB. For demo, uses in-memory store.
"""
import time
from models.schemas import FeedbackEntry, MemoryEntry

# -- In-memory stores (would be a database in production) --
_feedback_log: list[dict] = []
_memory_store: dict[str, list[MemoryEntry]] = {}  # keyed by brand_name


def record_feedback(entry: FeedbackEntry) -> dict:
    """Record human feedback into the memory system."""
    record = {
        "timestamp": time.time(),
        "session_id": entry.session_id,
        "brand_name": entry.brand_name,
        "feedback_type": entry.feedback_type,
        "original_content": entry.original_content,
        "suggested_content": entry.suggested_content,
        "user_comment": entry.user_comment,
        "dimension": entry.dimension,
    }
    _feedback_log.append(record)

    # Extract guideline from feedback
    if entry.feedback_type == "rejected" and entry.user_comment:
        _add_memory(
            entry.brand_name,
            MemoryEntry(
                brand_name=entry.brand_name,
                guideline=f"User rejected: '{entry.suggested_content}'. Reason: {entry.user_comment}",
                source="human_feedback",
                confidence=0.9,
            ),
        )
    elif entry.feedback_type == "guideline":
        _add_memory(
            entry.brand_name,
            MemoryEntry(
                brand_name=entry.brand_name,
                guideline=entry.user_comment,
                source="brand_guideline",
                confidence=1.0,
            ),
        )
    elif entry.feedback_type == "accepted":
        _add_memory(
            entry.brand_name,
            MemoryEntry(
                brand_name=entry.brand_name,
                guideline=f"User approved suggestion for {entry.dimension}: '{entry.suggested_content}'",
                source="learned_preference",
                confidence=0.8,
            ),
        )

    return {"status": "recorded", "total_feedback": len(_feedback_log)}


def get_memory_context(brand_name: str) -> list[MemoryEntry]:
    """Retrieve all cached guidelines and learned preferences for a brand."""
    return _memory_store.get(brand_name.lower(), [])


def add_guideline(brand_name: str, guideline: str) -> MemoryEntry:
    """Directly add a brand guideline to memory."""
    entry = MemoryEntry(
        brand_name=brand_name,
        guideline=guideline,
        source="brand_guideline",
        confidence=1.0,
    )
    _add_memory(brand_name, entry)
    return entry


def get_feedback_log(brand_name: str | None = None) -> list[dict]:
    """Retrieve the feedback log, optionally filtered by brand."""
    if brand_name:
        return [
            f for f in _feedback_log if f["brand_name"].lower() == brand_name.lower()
        ]
    return _feedback_log


def _add_memory(brand_name: str, entry: MemoryEntry) -> None:
    key = brand_name.lower()
    if key not in _memory_store:
        _memory_store[key] = []
    _memory_store[key].append(entry)
