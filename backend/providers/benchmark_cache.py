"""
Cache for measured competitor benchmarks.

Scoring 10 competitors costs a large LLM call, but the result depends only on
the competitor set and the rubric — never on the user's listing. So it is cached
per subcategory and reused across every analysis in that subcategory.

The key includes a fingerprint of the rubric. Editing a dimension's
`scoring_criteria` changes what the scores mean, so it must invalidate the
benchmark rather than silently compare new user scores against old competitor
scores graded by different rules.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone

from config import COMPETITOR_CACHE_TTL_HOURS
from models.schemas import (
    CompetitorBenchmarkSet,
    CompetitorScoutResult,
    ScoringRubric,
)
from store import connect

log = logging.getLogger("listingiq.providers.benchmark_cache")


def rubric_fingerprint(rubric: ScoringRubric) -> str:
    """Stable hash of everything that changes what a score means."""
    payload = json.dumps(
        [[d.name, d.weight, d.scoring_criteria] for d in rubric.dimensions],
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def competitor_set_fingerprint(scout: CompetitorScoutResult) -> str:
    """
    Identity of the exact listings that were scored.

    Without this the key was platform + subcategory + rubric, which was right
    while one marketplace search always returned the same top ten. Web discovery
    can return a different set for the same subcategory, and serving a benchmark
    computed from one set as though it described another is a silent corruption
    of every gap in the report.
    """
    ids = sorted((l.url or l.title).strip().lower() for l in scout.listings)
    return hashlib.sha256(json.dumps(ids).encode()).hexdigest()[:16]


def _key(platform: str, subcategory: str, rubric: ScoringRubric, set_fp: str = "") -> str:
    base = (f"{platform.lower().strip()}::{subcategory.lower().strip()}"
            f"::{rubric_fingerprint(rubric)}")
    return f"{base}::{set_fp}" if set_fp else base


async def get(
    platform: str, subcategory: str, rubric: ScoringRubric, set_fp: str = ""
) -> CompetitorBenchmarkSet | None:
    if COMPETITOR_CACHE_TTL_HOURS <= 0:
        return None

    key = _key(platform, subcategory, rubric, set_fp)
    db = await connect()
    try:
        cur = await db.execute(
            "SELECT payload, expires_at FROM benchmark_cache WHERE cache_key = ?", (key,))
        row = await cur.fetchone()
        if row is None:
            return None
        if datetime.fromisoformat(row[1]) <= datetime.now(timezone.utc):
            await db.execute("DELETE FROM benchmark_cache WHERE cache_key = ?", (key,))
            await db.commit()
            return None
    finally:
        await db.close()

    try:
        return CompetitorBenchmarkSet(**json.loads(row[0]))
    except Exception as e:
        log.warning("Discarding unreadable benchmark cache entry for %s: %s", key, e)
        return None


async def put(
    platform: str, subcategory: str, rubric: ScoringRubric,
    cohorts: CompetitorBenchmarkSet, set_fp: str = "",
) -> None:
    """
    Cache both cohorts as one payload.

    They are computed together from a single scoring call, so caching them
    together is what stops a half-populated pair — a same-platform cohort
    served next to a stale category one would be worse than no cache at all.
    """
    widest = cohorts.all_competitors
    if COMPETITOR_CACHE_TTL_HOURS <= 0 or not widest.competitors:
        return

    # The same guard `cache.put` applies to listings. Without it the
    # "estimated data is never cached" invariant leaked: listings from a
    # fallback were correctly refused, but a benchmark *computed from those
    # listings* was cached happily and then served for the rest of the TTL as
    # though it were measured against real competitors.
    if not widest.is_live_data:
        log.debug("Refusing to cache a benchmark built from estimated competitors")
        return

    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=COMPETITOR_CACHE_TTL_HOURS)
    db = await connect()
    try:
        await db.execute(
            """INSERT INTO benchmark_cache (cache_key, platform, subcategory,
                                            rubric_fingerprint, payload,
                                            fetched_at, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(cache_key) DO UPDATE SET
                 payload    = excluded.payload,
                 fetched_at = excluded.fetched_at,
                 expires_at = excluded.expires_at""",
            (_key(platform, subcategory, rubric, set_fp), platform, subcategory,
             rubric_fingerprint(rubric), cohorts.model_dump_json(),
             now.isoformat(), expires.isoformat()),
        )
        await db.commit()
    finally:
        await db.close()
    log.info("Cached benchmark for %s/%s (%d competitors, mean %.2f) until %s",
             platform, subcategory, len(widest.competitors), widest.overall_mean,
             expires.isoformat(timespec="minutes"))


async def invalidate(platform: str, subcategory: str) -> int:
    """Drop every benchmark for a subcategory, whatever the rubric version."""
    db = await connect()
    try:
        cur = await db.execute(
            "DELETE FROM benchmark_cache WHERE platform = ? AND subcategory = ?",
            (platform.lower().strip(), subcategory.lower().strip()))
        await db.commit()
        return cur.rowcount
    finally:
        await db.close()
