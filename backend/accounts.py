"""
Accounts, passwords and login sessions.

Passwords use hashlib.scrypt — a memory-hard KDF in the standard library, so
there is no new dependency and no hand-rolled crypto. Each password gets its own
random salt; verification is constant-time.

Sessions are opaque random tokens stored as SHA-256 hashes, following the same
pattern as API keys. Deliberately not JWTs: revocation is immediate, there is no
signing algorithm to misconfigure, and the token carries no readable claims.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from config import (
    DEFAULT_DAILY_TOKEN_LIMIT,
    DEFAULT_MAX_CONCURRENT,
    DEFAULT_RPM_LIMIT,
    SESSION_TTL_HOURS,
)
from store import connect

log = logging.getLogger("listingiq.accounts")

ROLES = ("admin", "member")

# scrypt cost parameters. n is the memory/CPU cost; 2**14 keeps a single hash
# around a few tens of milliseconds, which is the right order for a login.
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P, _DKLEN = 2 ** 14, 8, 1, 64

MIN_PASSWORD_LENGTH = 10


class AccountError(ValueError):
    """A rejected account operation, safe to surface to the caller."""


@dataclass(frozen=True)
class Account:
    account_id: str
    email: str
    role: str
    active: bool
    rpm_limit: int
    max_concurrent: int
    daily_token_limit: int
    created_at: str
    last_login_at: str | None

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


_COLS = ("account_id, email, role, active, rpm_limit, max_concurrent, "
         "daily_token_limit, created_at, last_login_at")


def _row_to_account(row) -> Account:
    return Account(
        account_id=row[0], email=row[1], role=row[2], active=bool(row[3]),
        rpm_limit=row[4], max_concurrent=row[5], daily_token_limit=row[6],
        created_at=row[7], last_login_at=row[8],
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Passwords ────────────────────────────────────────────────────

def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    """Return (hash_hex, salt_hex) for a password."""
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt,
        n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_DKLEN,
    )
    return digest.hex(), salt.hex()


def verify_password(password: str, hash_hex: str, salt_hex: str) -> bool:
    candidate, _ = hash_password(password, bytes.fromhex(salt_hex))
    return hmac.compare_digest(candidate, hash_hex)


def validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AccountError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")


def normalise_email(email: str) -> str:
    email = email.strip().lower()
    if "@" not in email or len(email) < 3:
        raise AccountError("A valid email address is required.")
    return email


# ── Account CRUD ─────────────────────────────────────────────────

async def create_account(
    email: str,
    password: str,
    role: str = "member",
    rpm_limit: int = DEFAULT_RPM_LIMIT,
    max_concurrent: int = DEFAULT_MAX_CONCURRENT,
    daily_token_limit: int = DEFAULT_DAILY_TOKEN_LIMIT,
) -> Account:
    email = normalise_email(email)
    validate_password(password)
    if role not in ROLES:
        raise AccountError(f"Role must be one of: {', '.join(ROLES)}")

    pw_hash, salt = hash_password(password)
    account_id = "acct_" + secrets.token_hex(6)
    db = await connect()
    try:
        cur = await db.execute("SELECT 1 FROM accounts WHERE email = ?", (email,))
        if await cur.fetchone():
            raise AccountError(f"An account already exists for {email}.")
        await db.execute(
            """INSERT INTO accounts (account_id, email, password_hash, password_salt,
                                     role, active, rpm_limit, max_concurrent,
                                     daily_token_limit, created_at)
               VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?)""",
            (account_id, email, pw_hash, salt, role, rpm_limit,
             max_concurrent, daily_token_limit, _now()),
        )
        await db.commit()
    finally:
        await db.close()
    log.info("Created %s account %s (%s)", role, account_id, email)
    return await get_account(account_id)


async def get_account(account_id: str) -> Account | None:
    db = await connect()
    try:
        cur = await db.execute(
            f"SELECT {_COLS} FROM accounts WHERE account_id = ?", (account_id,))
        row = await cur.fetchone()
    finally:
        await db.close()
    return _row_to_account(row) if row else None


async def list_accounts() -> list[Account]:
    db = await connect()
    try:
        cur = await db.execute(f"SELECT {_COLS} FROM accounts ORDER BY created_at")
        rows = await cur.fetchall()
    finally:
        await db.close()
    return [_row_to_account(r) for r in rows]


async def count_active_admins(exclude: str | None = None) -> int:
    db = await connect()
    try:
        sql = "SELECT COUNT(*) FROM accounts WHERE role = 'admin' AND active = 1"
        params: tuple = ()
        if exclude:
            sql += " AND account_id != ?"
            params = (exclude,)
        cur = await db.execute(sql, params)
        return (await cur.fetchone())[0]
    finally:
        await db.close()


async def update_account(account_id: str, **fields) -> Account:
    """Update limits, role or active flag. Unknown fields are rejected."""
    allowed = {"role", "active", "rpm_limit", "max_concurrent", "daily_token_limit"}
    updates = {k: v for k, v in fields.items() if v is not None and k in allowed}
    unknown = set(fields) - allowed
    if unknown:
        raise AccountError(f"Cannot update: {', '.join(sorted(unknown))}")

    account = await get_account(account_id)
    if account is None:
        raise AccountError("No such account.")

    if updates.get("role") and updates["role"] not in ROLES:
        raise AccountError(f"Role must be one of: {', '.join(ROLES)}")

    # Never allow the last active admin to be demoted or disabled — that would
    # lock everyone out of the admin panel with no way back except the CLI.
    losing_admin = (
        account.is_admin and account.active
        and (updates.get("role") not in (None, "admin") or updates.get("active") is False)
    )
    if losing_admin and await count_active_admins(exclude=account_id) == 0:
        raise AccountError(
            "This is the last active admin. Promote another account first.")

    for k in ("rpm_limit", "max_concurrent", "daily_token_limit"):
        if k in updates and int(updates[k]) < 0:
            raise AccountError(f"{k} cannot be negative.")

    if not updates:
        return account

    sets = ", ".join(f"{k} = ?" for k in updates)
    values = [int(v) if isinstance(v, bool) else v for v in updates.values()]
    db = await connect()
    try:
        await db.execute(
            f"UPDATE accounts SET {sets} WHERE account_id = ?", (*values, account_id))
        await db.commit()
    finally:
        await db.close()

    if updates.get("active") is False:
        await revoke_all_sessions(account_id)
    log.info("Updated account %s: %s", account_id, updates)
    return await get_account(account_id)


async def set_password(account_id: str, password: str) -> None:
    validate_password(password)
    pw_hash, salt = hash_password(password)
    db = await connect()
    try:
        cur = await db.execute(
            "UPDATE accounts SET password_hash = ?, password_salt = ? WHERE account_id = ?",
            (pw_hash, salt, account_id))
        await db.commit()
        if cur.rowcount == 0:
            raise AccountError("No such account.")
    finally:
        await db.close()
    # A password change invalidates existing sessions everywhere.
    await revoke_all_sessions(account_id)
    log.info("Password changed for %s; all sessions revoked", account_id)


# ── Login & sessions ─────────────────────────────────────────────

def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def authenticate(email: str, password: str) -> Account | None:
    """Verify credentials. Returns None for unknown, wrong or disabled accounts."""
    try:
        email = normalise_email(email)
    except AccountError:
        return None

    db = await connect()
    try:
        cur = await db.execute(
            f"SELECT {_COLS}, password_hash, password_salt FROM accounts WHERE email = ?",
            (email,))
        row = await cur.fetchone()
    finally:
        await db.close()

    if row is None:
        # Hash anyway so a missing account and a wrong password take the same
        # time, which stops the endpoint confirming which emails exist.
        hash_password(password)
        return None

    account = _row_to_account(row)
    if not verify_password(password, row[9], row[10]):
        return None
    if not account.active:
        log.warning("Login attempt on disabled account %s", account.email)
        return None
    return account


async def start_session(account_id: str) -> tuple[str, str]:
    """Create a session. Returns (raw_token, expires_at_iso)."""
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS)
    db = await connect()
    try:
        await db.execute(
            "INSERT INTO sessions (token_hash, account_id, created_at, expires_at) "
            "VALUES (?, ?, ?, ?)",
            (_hash_token(token), account_id, _now(), expires.isoformat()))
        await db.execute(
            "UPDATE accounts SET last_login_at = ? WHERE account_id = ?",
            (_now(), account_id))
        await db.commit()
    finally:
        await db.close()
    return token, expires.isoformat()


async def resolve_session(token: str) -> Account | None:
    """Return the account for a session token, or None if invalid or expired."""
    db = await connect()
    try:
        cur = await db.execute(
            "SELECT account_id, expires_at FROM sessions WHERE token_hash = ?",
            (_hash_token(token),))
        row = await cur.fetchone()
        if row is None:
            return None
        if datetime.fromisoformat(row[1]) <= datetime.now(timezone.utc):
            await db.execute(
                "DELETE FROM sessions WHERE token_hash = ?", (_hash_token(token),))
            await db.commit()
            return None
        account_id = row[0]
    finally:
        await db.close()

    account = await get_account(account_id)
    return account if account and account.active else None


async def end_session(token: str) -> None:
    db = await connect()
    try:
        await db.execute(
            "DELETE FROM sessions WHERE token_hash = ?", (_hash_token(token),))
        await db.commit()
    finally:
        await db.close()


async def revoke_all_sessions(account_id: str) -> int:
    db = await connect()
    try:
        cur = await db.execute(
            "DELETE FROM sessions WHERE account_id = ?", (account_id,))
        await db.commit()
        return cur.rowcount
    finally:
        await db.close()
