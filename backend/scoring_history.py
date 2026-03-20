"""
Scoring History — SQLite persistence for tracking scores over time.
Stores evaluation results per brand per session for trend projection.
"""
from __future__ import annotations

import aiosqlite
import json
import logging
from datetime import datetime
from pathlib import Path

log = logging.getLogger("sitescore.scoring_history")

DB_PATH = Path(__file__).parent / "data" / "scoring_history.db"


async def _ensure_table(db: aiosqlite.Connection) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS scoring_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            brand_name TEXT NOT NULL,
            session_id TEXT NOT NULL,
            tagline TEXT NOT NULL,
            overall_score REAL NOT NULL,
            dimension_scores TEXT NOT NULL,
            competitor_scores TEXT NOT NULL,
            depth_level TEXT DEFAULT 'standard',
            created_at TEXT NOT NULL
        )
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_brand_name ON scoring_history(brand_name)
    """)
    await db.commit()


async def record_score(
    brand_name: str,
    session_id: str,
    tagline: str,
    overall_score: float,
    dimension_scores: list[dict],
    competitor_scores: list[dict],
    depth_level: str = "standard",
) -> int:
    """Save an evaluation score to history. Returns the row ID."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await _ensure_table(db)
        cursor = await db.execute(
            """INSERT INTO scoring_history
               (brand_name, session_id, tagline, overall_score,
                dimension_scores, competitor_scores, depth_level, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                brand_name,
                session_id,
                tagline,
                overall_score,
                json.dumps(dimension_scores),
                json.dumps(competitor_scores),
                depth_level,
                datetime.utcnow().isoformat(),
            ),
        )
        await db.commit()
        row_id = cursor.lastrowid
        log.info("Recorded score for %s: %.1f (row %d)", brand_name, overall_score, row_id)
        return row_id


async def get_score_history(brand_name: str, limit: int = 20) -> list[dict]:
    """Retrieve scoring history for a brand, most recent first."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await _ensure_table(db)
        cursor = await db.execute(
            """SELECT brand_name, session_id, tagline, overall_score,
                      dimension_scores, competitor_scores, depth_level, created_at
               FROM scoring_history
               WHERE brand_name = ?
               ORDER BY created_at DESC
               LIMIT ?""",
            (brand_name, limit),
        )
        rows = await cursor.fetchall()
        return [
            {
                "brand_name": r[0],
                "session_id": r[1],
                "tagline": r[2],
                "overall_score": r[3],
                "dimension_scores": json.loads(r[4]),
                "competitor_scores": json.loads(r[5]),
                "depth_level": r[6],
                "created_at": r[7],
            }
            for r in rows
        ]
