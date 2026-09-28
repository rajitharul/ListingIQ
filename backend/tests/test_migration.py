"""
Upgrade path from a pre-accounts database.

The other suites always start from an empty database, so they never exercise
migration — which is exactly where the last bug was. This builds a database with
the ORIGINAL pre-accounts schema, runs the current ensure_schema over it, and
checks the result is usable.
"""
import asyncio, os, pathlib, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_tmp = tempfile.TemporaryDirectory()
DB = pathlib.Path(_tmp.name) / "auth.db"
os.environ["AUTH_DB_PATH"] = str(DB)
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

import aiosqlite

results = []
def check(label, passed, detail=""):
    results.append(passed)
    print(f"  {'ok  ' if passed else 'FAIL'} {label}{'  ' + str(detail) if detail else ''}")


# The schema exactly as it shipped before accounts existed.
OLD_SCHEMA = """
CREATE TABLE api_keys (
    key_id TEXT PRIMARY KEY, key_hash TEXT NOT NULL UNIQUE, label TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1, rpm_limit INTEGER NOT NULL,
    max_concurrent INTEGER NOT NULL, daily_token_limit INTEGER NOT NULL,
    created_at TEXT NOT NULL, last_used_at TEXT
);
CREATE TABLE daily_usage (
    key_id TEXT NOT NULL, day TEXT NOT NULL, tokens INTEGER NOT NULL DEFAULT 0,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0, runs INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (key_id, day)
);
"""


async def main():
    DB.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(DB)) as db:
        await db.executescript(OLD_SCHEMA)
        await db.execute(
            "INSERT INTO api_keys (key_id, key_hash, label, active, rpm_limit, "
            "max_concurrent, daily_token_limit, created_at) "
            "VALUES ('key_old', 'deadbeef', 'Legacy', 1, 10, 2, 2000000, '2026-01-01')")
        await db.execute(
            "INSERT INTO daily_usage (key_id, day, tokens, runs) "
            "VALUES ('key_old', '2026-01-01', 5000, 3)")
        await db.commit()

    import store, accounts, quota, auth

    db = await store.connect()          # runs ensure_schema, i.e. the migration
    try:
        cols = await store._columns(db, "daily_usage")
        check("daily_usage is re-keyed on account_id", "account_id" in cols, sorted(cols))
        check("old key_id column is gone from daily_usage", "key_id" not in cols)

        cur = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='daily_usage_pre_accounts'")
        check("old usage rows preserved, not dropped", await cur.fetchone() is not None)
        cur = await db.execute("SELECT tokens FROM daily_usage_pre_accounts WHERE key_id='key_old'")
        row = await cur.fetchone()
        check("preserved rows still readable", row and row[0] == 5000, row)

        check("api_keys gained account_id", "account_id" in await store._columns(db, "api_keys"))
        cur = await db.execute("SELECT account_id FROM api_keys WHERE key_id='key_old'")
        check("legacy key is left orphaned, not misattributed",
              (await cur.fetchone())[0] is None)
    finally:
        await db.close()

    # The migrated database must actually work.
    acct = await accounts.create_account("post@migration.com", "supersecret123")
    check("accounts work after migration", acct.account_id.startswith("acct_"))

    usage = await quota.get_usage_today(acct.account_id)
    check("usage reads cleanly after migration", usage["tokens"] == 0, usage)
    await quota.record_usage(acct.account_id, 100, 50)
    usage = await quota.get_usage_today(acct.account_id)
    check("usage writes after migration", usage["tokens"] == 150 and usage["runs"] == 1, usage)

    # The orphaned legacy key must be refused rather than granted a guessed owner.
    from fastapi import Request
    caller = await auth._caller_from_key("whatever-does-not-match")
    check("unknown key rejected", caller is None)

    # Migration is idempotent.
    db = await store.connect()
    await db.close()
    usage = await quota.get_usage_today(acct.account_id)
    check("re-running the migration preserves data", usage["tokens"] == 150, usage)

    print()
    print(f"{sum(results)}/{len(results)} checks passed")
    print("MIGRATION PASS" if all(results) else "MIGRATION FAIL")
    return 0 if all(results) else 1


sys.exit(asyncio.run(main()))
