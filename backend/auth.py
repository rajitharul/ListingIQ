"""
Caller resolution: who is making this request, and under whose quota.

Two credentials reach the same place. A browser sends a session (cookie or
bearer token) established by logging in; a script sends an API key. Both resolve
to a `Caller` carrying the owning account's limits, so a customer's web and
programmatic usage draw from one budget rather than two.

API keys belong to accounts. A key with no owner — one issued before accounts
existed — is refused rather than assigned a guessed owner.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status

from accounts import Account, get_account
from accounts import resolve_session
from config import AUTH_ENABLED, DEFAULT_DAILY_TOKEN_LIMIT, DEFAULT_MAX_CONCURRENT, DEFAULT_RPM_LIMIT
from store import connect

log = logging.getLogger("listingiq.auth")

KEY_PREFIX = "liq_live_"
SESSION_COOKIE = "liq_session"
API_KEY_HEADER = "X-API-Key"


@dataclass(frozen=True)
class Caller:
    """An authenticated caller and the quota it spends against."""
    account_id: str
    email: str
    role: str
    via: str                 # "session" | "api_key" | "auth-disabled"
    rpm_limit: int
    max_concurrent: int
    daily_token_limit: int

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def label(self) -> str:
        return f"{self.email} ({self.via})"


# Identity used when AUTH_ENABLED is false, so quota code has something to key
# on rather than branching on whether auth ran.
ANONYMOUS = Caller(
    account_id="anonymous", email="anonymous@local", role="admin",
    via="auth-disabled", rpm_limit=DEFAULT_RPM_LIMIT,
    max_concurrent=DEFAULT_MAX_CONCURRENT,
    daily_token_limit=DEFAULT_DAILY_TOKEN_LIMIT,
)


def _caller_from_account(account: Account, via: str) -> Caller:
    return Caller(
        account_id=account.account_id, email=account.email, role=account.role,
        via=via, rpm_limit=account.rpm_limit,
        max_concurrent=account.max_concurrent,
        daily_token_limit=account.daily_token_limit,
    )


# ── API keys ─────────────────────────────────────────────────────

def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def generate_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(32)


async def create_key(account_id: str, label: str) -> tuple[str, str]:
    """
    Issue an API key under an account. Returns (key_id, raw_key).

    The key inherits the account's limits, so there is one place to change them.
    """
    account = await get_account(account_id)
    if account is None:
        raise ValueError(f"No such account: {account_id}")

    raw = generate_key()
    key_id = "key_" + secrets.token_hex(6)
    db = await connect()
    try:
        await db.execute(
            """INSERT INTO api_keys (key_id, key_hash, label, active, rpm_limit,
                                     max_concurrent, daily_token_limit,
                                     created_at, account_id)
               VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?)""",
            (key_id, hash_key(raw), label, account.rpm_limit,
             account.max_concurrent, account.daily_token_limit,
             datetime.now(timezone.utc).isoformat(), account_id),
        )
        await db.commit()
    finally:
        await db.close()
    return key_id, raw


async def revoke_key(key_id: str) -> bool:
    db = await connect()
    try:
        cur = await db.execute(
            "UPDATE api_keys SET active = 0 WHERE key_id = ?", (key_id,))
        await db.commit()
        return cur.rowcount > 0
    finally:
        await db.close()


async def list_keys(account_id: str | None = None) -> list[dict]:
    db = await connect()
    try:
        sql = ("SELECT k.key_id, k.label, k.active, k.created_at, k.last_used_at, "
               "k.account_id, a.email FROM api_keys k "
               "LEFT JOIN accounts a ON a.account_id = k.account_id")
        params: tuple = ()
        if account_id:
            sql += " WHERE k.account_id = ?"
            params = (account_id,)
        sql += " ORDER BY k.created_at DESC"
        cur = await db.execute(sql, params)
        rows = await cur.fetchall()
    finally:
        await db.close()
    cols = ["key_id", "label", "active", "created_at", "last_used_at",
            "account_id", "email"]
    return [dict(zip(cols, r)) for r in rows]


async def _caller_from_key(raw_key: str) -> Caller | None:
    db = await connect()
    try:
        cur = await db.execute(
            "SELECT key_id, account_id FROM api_keys WHERE key_hash = ? AND active = 1",
            (hash_key(raw_key),))
        row = await cur.fetchone()
        if row is None:
            return None
        key_id, account_id = row
        await db.execute(
            "UPDATE api_keys SET last_used_at = ? WHERE key_id = ?",
            (datetime.now(timezone.utc).isoformat(), key_id))
        await db.commit()
    finally:
        await db.close()

    if not account_id:
        log.warning("API key %s has no owning account — refusing", key_id)
        return None

    account = await get_account(account_id)
    if account is None or not account.active:
        log.warning("API key %s belongs to a missing or disabled account", key_id)
        return None
    return _caller_from_account(account, "api_key")


# ── Request credentials ──────────────────────────────────────────

def session_token_from(request: Request) -> str | None:
    """Session token from the cookie, or an Authorization: Bearer header."""
    cookie = request.cookies.get(SESSION_COOKIE)
    if cookie:
        return cookie
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None
    return None


async def resolve_caller(request: Request) -> Caller | None:
    """Resolve a caller from whichever credential is present, or None."""
    token = session_token_from(request)
    if token:
        account = await resolve_session(token)
        if account:
            return _caller_from_account(account, "session")

    raw_key = request.headers.get(API_KEY_HEADER)
    if raw_key:
        return await _caller_from_key(raw_key)
    return None


async def require_caller(request: Request) -> Caller:
    """FastAPI dependency: any authenticated caller, or 401."""
    if not AUTH_ENABLED:
        return ANONYMOUS

    caller = await resolve_caller(request)
    if caller is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Log in, or send a valid X-API-Key header.",
        )
    return caller


async def require_admin(request: Request) -> Caller:
    """FastAPI dependency: an authenticated admin, or 401/403."""
    caller = await require_caller(request)
    if not caller.is_admin:
        log.warning("Non-admin %s attempted an admin action", caller.email)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required.",
        )
    return caller


CallerDep = Depends(require_caller)
AdminDep = Depends(require_admin)
