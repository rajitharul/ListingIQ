#!/usr/bin/env python3
"""
Account administration from the command line.

Everything here is also in the admin panel, except `create-admin` — which
exists to bootstrap the very first administrator, before anyone can log in.

    python manage_accounts.py create-admin admin@example.com
    python manage_accounts.py create user@example.com --rpm 20
    python manage_accounts.py list
    python manage_accounts.py set-limits acct_ab12cd34 --daily-tokens 500000
    python manage_accounts.py password acct_ab12cd34
    python manage_accounts.py deactivate acct_ab12cd34
    python manage_accounts.py issue-key acct_ab12cd34 "CI pipeline"

Passwords are prompted for, never passed as arguments, so they stay out of
shell history and the process list.
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import sys

import accounts
import auth
from config import DEFAULT_DAILY_TOKEN_LIMIT, DEFAULT_MAX_CONCURRENT, DEFAULT_RPM_LIMIT


def _prompt_password(confirm: bool = True) -> str:
    pw = getpass.getpass("  Password: ")
    if confirm and pw != getpass.getpass("  Confirm password: "):
        sys.exit("  Passwords do not match.")
    return pw


def _limit_kwargs(args) -> dict:
    return {k: v for k, v in {
        "rpm_limit": args.rpm,
        "max_concurrent": args.concurrent,
        "daily_token_limit": args.daily_tokens,
    }.items() if v is not None}


async def cmd_create(args) -> int:
    role = "admin" if args.admin else "member"
    if role == "admin" and await accounts.count_active_admins() > 0 and not args.force:
        print("  An admin already exists. Create further admins from the admin panel,")
        print("  or pass --force if you are sure.")
        return 1
    try:
        a = await accounts.create_account(
            email=args.email, password=_prompt_password(),
            role=role, **_limit_kwargs(args))
    except accounts.AccountError as e:
        sys.exit(f"  {e}")
    print()
    print(f"  Created {a.role} account")
    print(f"    account_id  {a.account_id}")
    print(f"    email       {a.email}")
    print(f"    limits      {a.rpm_limit}/min · {a.max_concurrent} concurrent · "
          f"{a.daily_token_limit:,} tokens/day")
    print()
    return 0


async def cmd_list(args) -> int:
    rows = await accounts.list_accounts()
    if not rows:
        print('  No accounts yet. Create the first admin with:')
        print('    python manage_accounts.py create-admin you@example.com')
        return 0
    print(f"  {'account_id':<18} {'email':<30} {'role':<8} {'state':<9} "
          f"{'rpm':>5} {'conc':>5} {'tokens/day':>12}  last login")
    for a in rows:
        print(f"  {a.account_id:<18} {a.email[:30]:<30} {a.role:<8} "
              f"{'active' if a.active else 'disabled':<9} "
              f"{a.rpm_limit:>5} {a.max_concurrent:>5} "
              f"{a.daily_token_limit:>12,}  {a.last_login_at or 'never'}")
    return 0


async def cmd_set_limits(args) -> int:
    kwargs = _limit_kwargs(args)
    if not kwargs:
        sys.exit("  Nothing to change. Pass at least one of --rpm/--concurrent/--daily-tokens.")
    try:
        a = await accounts.update_account(args.account_id, **kwargs)
    except accounts.AccountError as e:
        sys.exit(f"  {e}")
    print(f"  {a.email}: {a.rpm_limit}/min · {a.max_concurrent} concurrent · "
          f"{a.daily_token_limit:,} tokens/day")
    return 0


async def cmd_password(args) -> int:
    try:
        await accounts.set_password(args.account_id, _prompt_password())
    except accounts.AccountError as e:
        sys.exit(f"  {e}")
    print("  Password updated. All existing sessions for this account were revoked.")
    return 0


async def cmd_set_active(args, active: bool) -> int:
    try:
        a = await accounts.update_account(args.account_id, active=active)
    except accounts.AccountError as e:
        sys.exit(f"  {e}")
    print(f"  {a.email} is now {'active' if a.active else 'disabled'}.")
    return 0


async def cmd_issue_key(args) -> int:
    try:
        key_id, raw = await auth.create_key(args.account_id, args.label)
    except ValueError as e:
        sys.exit(f"  {e}")
    print()
    print(f"  key_id   {key_id}")
    print(f"  API key  {raw}")
    print()
    print("  Store it now — only its hash is saved. It spends the account's quota.")
    print()
    return 0


async def cmd_list_keys(args) -> int:
    rows = await auth.list_keys(args.account_id)
    if not rows:
        print("  No API keys issued.")
        return 0
    print(f"  {'key_id':<18} {'label':<24} {'owner':<30} {'state':<9} last used")
    for k in rows:
        print(f"  {k['key_id']:<18} {k['label'][:24]:<24} "
              f"{(k['email'] or 'ORPHANED'):<30} "
              f"{'active' if k['active'] else 'revoked':<9} {k['last_used_at'] or 'never'}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    def limits(sp):
        sp.add_argument("--rpm", type=int, default=None,
                        help=f"requests per minute (default {DEFAULT_RPM_LIMIT})")
        sp.add_argument("--concurrent", type=int, default=None,
                        help=f"concurrent runs (default {DEFAULT_MAX_CONCURRENT})")
        sp.add_argument("--daily-tokens", type=int, default=None,
                        help=f"tokens per day (default {DEFAULT_DAILY_TOKEN_LIMIT:,})")

    a = sub.add_parser("create-admin", help="bootstrap the first administrator")
    a.add_argument("email"); limits(a)
    a.add_argument("--force", action="store_true", help="create even if an admin exists")
    a.set_defaults(func=cmd_create, admin=True)

    c = sub.add_parser("create", help="create a member account")
    c.add_argument("email"); limits(c)
    c.set_defaults(func=cmd_create, admin=False, force=False)

    sub.add_parser("list", help="list accounts").set_defaults(func=cmd_list)

    s = sub.add_parser("set-limits", help="change an account's limits")
    s.add_argument("account_id"); limits(s)
    s.set_defaults(func=cmd_set_limits)

    w = sub.add_parser("password", help="set an account's password")
    w.add_argument("account_id"); w.set_defaults(func=cmd_password)

    d = sub.add_parser("deactivate", help="disable an account and end its sessions")
    d.add_argument("account_id")
    d.set_defaults(func=lambda args: cmd_set_active(args, False))

    e = sub.add_parser("activate", help="re-enable an account")
    e.add_argument("account_id")
    e.set_defaults(func=lambda args: cmd_set_active(args, True))

    k = sub.add_parser("issue-key", help="issue an API key under an account")
    k.add_argument("account_id"); k.add_argument("label")
    k.set_defaults(func=cmd_issue_key)

    lk = sub.add_parser("list-keys", help="list API keys")
    lk.add_argument("--account-id", default=None)
    lk.set_defaults(func=cmd_list_keys)

    args = p.parse_args()
    return asyncio.run(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
