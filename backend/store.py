"""
Shared SQLite store for accounts, sessions, API keys and usage.

All four live in one database because they are one concern: who may call, and
how much. `ensure_schema` is idempotent and also carries forward-migrations, so
an existing auth.db picks up new columns rather than needing a rebuild.
"""
from __future__ import annotations

import logging

import aiosqlite

from config import AUTH_DB_PATH

log = logging.getLogger("listingiq.store")


async def _columns(db: aiosqlite.Connection, table: str) -> set[str]:
    cur = await db.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in await cur.fetchall()}


async def ensure_schema(db: aiosqlite.Connection) -> None:
    # ── Accounts ────────────────────────────────────────────────
    await db.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            account_id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            password_salt TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'member',
            active INTEGER NOT NULL DEFAULT 1,
            rpm_limit INTEGER NOT NULL,
            max_concurrent INTEGER NOT NULL,
            daily_token_limit INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            last_login_at TEXT
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_accounts_email ON accounts(email)")

    # ── Sessions ────────────────────────────────────────────────
    # Opaque random tokens, stored hashed. No JWT: revocation is immediate and
    # there is no signing algorithm to get wrong.
    await db.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_account ON sessions(account_id)")

    # ── API keys ────────────────────────────────────────────────
    await db.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            key_id TEXT PRIMARY KEY,
            key_hash TEXT NOT NULL UNIQUE,
            label TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            rpm_limit INTEGER NOT NULL,
            max_concurrent INTEGER NOT NULL,
            daily_token_limit INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            last_used_at TEXT,
            account_id TEXT
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash)")

    # Forward-migration for databases created before keys belonged to accounts.
    # Such keys are orphans: auth refuses them rather than guessing an owner.
    if "account_id" not in await _columns(db, "api_keys"):
        log.warning("Migrating api_keys: adding account_id. Pre-existing keys "
                    "become orphaned and must be reissued under an account.")
        await db.execute("ALTER TABLE api_keys ADD COLUMN account_id TEXT")

    # ── Usage ───────────────────────────────────────────────────
    # Pre-accounts databases keyed daily_usage by key_id, which is part of the
    # primary key and so cannot be migrated with ALTER TABLE. Those rows belong
    # to keys that now have no owning account, so they cannot be attributed to
    # anyone: set them aside under a new name rather than dropping them, and
    # build the account-keyed table fresh.
    usage_cols = await _columns(db, "daily_usage")
    if usage_cols and "account_id" not in usage_cols:
        log.warning("Migrating daily_usage: old key_id-based rows moved to "
                    "daily_usage_pre_accounts; today's counters restart at zero.")
        await db.execute("DROP TABLE IF EXISTS daily_usage_pre_accounts")
        await db.execute("ALTER TABLE daily_usage RENAME TO daily_usage_pre_accounts")

    # Keyed by account_id, so a customer's web and API usage share one budget.
    await db.execute("""
        CREATE TABLE IF NOT EXISTS daily_usage (
            account_id TEXT NOT NULL,
            day TEXT NOT NULL,
            tokens INTEGER NOT NULL DEFAULT 0,
            prompt_tokens INTEGER NOT NULL DEFAULT 0,
            completion_tokens INTEGER NOT NULL DEFAULT 0,
            runs INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (account_id, day)
        )
    """)
    # ── Competitor cache ────────────────────────────────────────
    # One fetch costs 11 upstream requests, so results are reused across runs
    # of the same subcategory. Only live data is ever cached.
    await db.execute("""
        CREATE TABLE IF NOT EXISTS competitor_cache (
            cache_key TEXT PRIMARY KEY,
            platform TEXT NOT NULL,
            subcategory TEXT NOT NULL,
            payload TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_cache_expires ON competitor_cache(expires_at)")

    # ── Measured competitor benchmarks ──────────────────────────
    # Scoring 10 competitors is a large LLM call whose result depends only on
    # the competitor set and the rubric. The key carries a rubric fingerprint so
    # editing scoring_criteria invalidates it rather than comparing new user
    # scores against competitor scores graded by different rules.
    await db.execute("""
        CREATE TABLE IF NOT EXISTS benchmark_cache (
            cache_key TEXT PRIMARY KEY,
            platform TEXT NOT NULL,
            subcategory TEXT NOT NULL,
            rubric_fingerprint TEXT NOT NULL,
            payload TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_benchmark_sub ON benchmark_cache(platform, subcategory)")

    await db.commit()


async def connect() -> aiosqlite.Connection:
    """Open the auth database with its schema in place."""
    AUTH_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(str(AUTH_DB_PATH))
    await ensure_schema(db)
    return db
