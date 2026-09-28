"""
Competitor result cache.

A subcategory's top 10 does not change minute to minute, but fetching it costs
11 upstream API requests (1 search + 10 product lookups). Without caching, every
pipeline run pays that in full — which is the difference between viable and
unviable unit economics.

Cached by (platform, subcategory) with a TTL. Entries are stored as JSON in the
same SQLite database as accounts so there is one thing to back up.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from config import COMPETITOR_CACHE_TTL_HOURS
from models.schemas import CompetitorScoutResult
from store import connect

log = logging.getLogger("listingiq.providers.cache")


def _key(platform: str, subcategory: str, spec: str = "") -> str:
    """
    Cache identity.

    `spec` is the discovery fingerprint: what was asked for, from
    `providers.query.QueryPlan.fingerprint`. A multi-platform result set is no
    longer identified by platform and subcategory alone, because the same pair
    can now be searched with a different limit or country and produce a
    different set. Defaulted to "" so the single-marketplace providers, whose
    result genuinely is determined by the pair, keep their existing keys.
    """
    return _legacy_key(platform, subcategory) + (f"::{spec}" if spec else "")


def _legacy_key(platform: str, subcategory: str) -> str:
    return f"{platform.lower().strip()}::{subcategory.lower().strip()}"


async def get(platform: str, subcategory: str, spec: str = "") -> CompetitorScoutResult | None:
    """Return a cached result if one exists and has not expired."""
    if COMPETITOR_CACHE_TTL_HOURS <= 0:
        return None

    db = await connect()
    try:
        cur = await db.execute(
            "SELECT payload, expires_at FROM competitor_cache WHERE cache_key = ?",
            (_key(platform, subcategory, spec),),
        )
        row = await cur.fetchone()
        if row is None:
            return None
        if datetime.fromisoformat(row[1]) <= datetime.now(timezone.utc):
            await db.execute(
                "DELETE FROM competitor_cache WHERE cache_key = ?",
                (_key(platform, subcategory, spec),),
            )
            await db.commit()
            return None
    finally:
        await db.close()

    try:
        return CompetitorScoutResult(**json.loads(row[0]))
    except Exception as e:
        # A cached payload that no longer matches the schema is not worth
        # failing a run over; treat it as a miss and refetch.
        log.warning("Discarding unreadable cache entry for %s/%s: %s",
                    platform, subcategory, e)
        return None


async def put(platform: str, subcategory: str, result: CompetitorScoutResult,
              spec: str = "") -> None:
    """Cache a result. Estimated data is never cached — only live fetches."""
    if COMPETITOR_CACHE_TTL_HOURS <= 0 or not result.listings:
        return
    if not result.is_live_data:
        return

    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=COMPETITOR_CACHE_TTL_HOURS)
    db = await connect()
    try:
        await db.execute(
            """INSERT INTO competitor_cache (cache_key, platform, subcategory,
                                             payload, fetched_at, expires_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(cache_key) DO UPDATE SET
                 payload    = excluded.payload,
                 fetched_at = excluded.fetched_at,
                 expires_at = excluded.expires_at""",
            (_key(platform, subcategory, spec), platform, subcategory, result.model_dump_json(),
             now.isoformat(), expires.isoformat()),
        )
        await db.commit()
    finally:
        await db.close()
    log.info("Cached %d competitors for %s/%s until %s",
             len(result.listings), platform, subcategory, expires.isoformat(timespec="minutes"))


async def invalidate(platform: str, subcategory: str) -> bool:
    """
    Drop every cached result for a platform and subcategory.

    Matches on the prefix rather than one exact key, because a subcategory can
    now hold several entries under different discovery fingerprints (a
    different limit or country). Invalidating one of them and leaving the rest
    would be worse than not invalidating at all.
    """
    db = await connect()
    try:
        cur = await db.execute(
            "DELETE FROM competitor_cache WHERE cache_key = ? OR cache_key LIKE ?",
            (_legacy_key(platform, subcategory),
             _legacy_key(platform, subcategory) + "::%"),
        )
        await db.commit()
        return cur.rowcount > 0
    finally:
        await db.close()


async def stats() -> list[dict]:
    """Cache contents, for the admin view and for debugging cost."""
    db = await connect()
    try:
        cur = await db.execute(
            """SELECT platform, subcategory, fetched_at, expires_at,
                      json_array_length(json_extract(payload, '$.listings')) AS n
               FROM competitor_cache ORDER BY fetched_at DESC"""
        )
        rows = await cur.fetchall()
    finally:
        await db.close()
    now = datetime.now(timezone.utc)
    return [
        {
            "platform": r[0], "subcategory": r[1],
            "fetched_at": r[2], "expires_at": r[3], "listings": r[4],
            "expired": datetime.fromisoformat(r[3]) <= now,
        }
        for r in rows
    ]
