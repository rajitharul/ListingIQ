"""
Offline tests for accounts, login sessions, roles and admin routes.

Drives the real FastAPI app over ASGI against a temporary database. No model
calls, no touching the developer's own auth.db.
"""
import asyncio, os, pathlib, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_tmp = tempfile.TemporaryDirectory()
os.environ["AUTH_DB_PATH"] = str(pathlib.Path(_tmp.name) / "auth.db")
os.environ["AUTH_ENABLED"] = "true"
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-a-real-key")

import httpx
import accounts
import auth

results = []
def check(label, passed, detail=""):
    results.append(passed)
    print(f"  {'ok  ' if passed else 'FAIL'} {label}{'  ' + str(detail) if detail else ''}")


async def main():
    from main import app
    t = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=t, base_url="http://t") as c:
        # ── Passwords ────────────────────────────────────────────
        h, salt = accounts.hash_password("supersecret123")
        check("password verifies", accounts.verify_password("supersecret123", h, salt))
        check("wrong password rejected", not accounts.verify_password("nope", h, salt))
        h2, salt2 = accounts.hash_password("supersecret123")
        check("same password, different salt -> different hash", h != h2 and salt != salt2)

        admin = await accounts.create_account("admin@x.com", "supersecret123", role="admin")
        check("admin created", admin.is_admin and admin.active)

        # ── Login ────────────────────────────────────────────────
        r = await c.post("/api/auth/login", json={"email": "admin@x.com", "password": "wrong"})
        check("wrong password -> 401", r.status_code == 401, r.status_code)
        wrong_msg = r.json()["detail"]
        r = await c.post("/api/auth/login", json={"email": "ghost@x.com", "password": "supersecret123"})
        check("unknown email gives the identical message (no account enumeration)",
              r.status_code == 401 and r.json()["detail"] == wrong_msg)

        r = await c.post("/api/auth/login", json={"email": "ADMIN@X.com  ", "password": "supersecret123"})
        check("email is case/space insensitive", r.status_code == 200, r.status_code)
        check("session cookie set", "liq_session" in r.cookies)
        check("cookie is httpOnly", "httponly" in r.headers.get("set-cookie", "").lower())
        token = r.json()["token"]

        r = await c.get("/api/auth/me")
        check("cookie authenticates", r.status_code == 200 and r.json()["via"] == "session", r.status_code)

        # ── Admin creates and edits accounts ─────────────────────
        r = await c.post("/api/admin/accounts", json={
            "email": "member@x.com", "password": "memberpass123", "role": "member",
            "rpm_limit": 7, "max_concurrent": 1, "daily_token_limit": 1234})
        check("admin creates member -> 201", r.status_code == 201, r.status_code)
        member_id = r.json()["account_id"]
        check("limits stored as given",
              r.json()["rpm_limit"] == 7 and r.json()["daily_token_limit"] == 1234)

        r = await c.post("/api/admin/accounts", json={"email": "member@x.com", "password": "another123"})
        check("duplicate email -> 400", r.status_code == 400, r.status_code)
        r = await c.post("/api/admin/accounts", json={"email": "x@x.com", "password": "short"})
        check("weak password -> 400", r.status_code == 400, r.json().get("detail"))
        r = await c.post("/api/admin/accounts", json={"email": "not-an-email", "password": "longenough123"})
        check("invalid email -> 400", r.status_code == 400, r.status_code)

        r = await c.patch(f"/api/admin/accounts/{member_id}", json={"rpm_limit": 50})
        check("admin edits limits", r.status_code == 200 and r.json()["rpm_limit"] == 50)

        r = await c.get("/api/admin/accounts")
        check("account list includes usage", r.status_code == 200
              and all("usage_today" in a for a in r.json()), r.status_code)

        # ── Roles ────────────────────────────────────────────────
        async with httpx.AsyncClient(transport=t, base_url="http://t") as mc:
            r = await mc.post("/api/auth/login", json={"email": "member@x.com", "password": "memberpass123"})
            check("member logs in", r.status_code == 200, r.status_code)
            r = await mc.get("/api/admin/accounts")
            check("member blocked from admin list -> 403", r.status_code == 403, r.status_code)
            r = await mc.post("/api/admin/accounts", json={"email": "z@x.com", "password": "longenough123"})
            check("member cannot create accounts -> 403", r.status_code == 403, r.status_code)
            r = await mc.get("/api/auth/me")
            check("member sees their own updated quota", r.json()["rpm_limit"] == 50)

        # ── Last-admin protection ────────────────────────────────
        r = await c.patch(f"/api/admin/accounts/{admin.account_id}", json={"role": "member"})
        check("cannot demote the last admin",
              r.status_code == 400 and "last active admin" in r.json()["detail"])
        r = await c.patch(f"/api/admin/accounts/{admin.account_id}", json={"active": False})
        check("cannot disable the last admin", r.status_code == 400, r.status_code)

        second = await accounts.create_account("admin2@x.com", "supersecret123", role="admin")
        r = await c.patch(f"/api/admin/accounts/{admin.account_id}", json={"role": "member"})
        check("demotion allowed once a second admin exists", r.status_code == 200, r.status_code)
        await accounts.update_account(admin.account_id, role="admin")

        # ── API keys belong to accounts ──────────────────────────
        r = await c.post("/api/admin/keys", json={"account_id": member_id, "label": "CI"})
        check("admin issues a key -> 201", r.status_code == 201, r.status_code)
        raw, key_id = r.json()["api_key"], r.json()["key_id"]

        async with httpx.AsyncClient(transport=t, base_url="http://t") as kc:
            r = await kc.get("/api/auth/me", headers={"X-API-Key": raw})
            check("key authenticates as its owning account",
                  r.status_code == 200 and r.json()["account_id"] == member_id
                  and r.json()["via"] == "api_key", r.status_code)
            check("key inherits the account's limits", r.json()["rpm_limit"] == 50)

        r = await c.post("/api/admin/keys", json={"account_id": "acct_nonexistent", "label": "x"})
        check("key for a missing account -> 400", r.status_code == 400, r.status_code)

        # ── Deactivation cascades ────────────────────────────────
        await c.patch(f"/api/admin/accounts/{member_id}", json={"active": False})
        async with httpx.AsyncClient(transport=t, base_url="http://t") as kc:
            r = await kc.get("/api/auth/me", headers={"X-API-Key": raw})
            check("disabling an account kills its API key", r.status_code == 401, r.status_code)
            r = await kc.post("/api/auth/login", json={"email": "member@x.com", "password": "memberpass123"})
            check("disabled account cannot log in", r.status_code == 401, r.status_code)

        await c.patch(f"/api/admin/accounts/{member_id}", json={"active": True})

        # ── Password change revokes sessions ─────────────────────
        async with httpx.AsyncClient(transport=t, base_url="http://t") as mc:
            await mc.post("/api/auth/login", json={"email": "member@x.com", "password": "memberpass123"})
            check("member session live before reset", (await mc.get("/api/auth/me")).status_code == 200)
            await c.post(f"/api/admin/accounts/{member_id}/password", json={"password": "brandnewpass123"})
            check("password reset revokes existing sessions",
                  (await mc.get("/api/auth/me")).status_code == 401)

        # ── Key revocation, logout ───────────────────────────────
        await c.delete(f"/api/admin/keys/{key_id}")
        async with httpx.AsyncClient(transport=t, base_url="http://t") as kc:
            r = await kc.get("/api/auth/me", headers={"X-API-Key": raw})
            check("revoked key -> 401", r.status_code == 401, r.status_code)

        r = await c.post("/api/auth/logout")
        check("logout -> 200", r.status_code == 200, r.status_code)
        async with httpx.AsyncClient(transport=t, base_url="http://t") as lc:
            r = await lc.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
            check("logged-out bearer token rejected", r.status_code == 401, r.status_code)

        # ── App routes require auth ──────────────────────────────
        async with httpx.AsyncClient(transport=t, base_url="http://t") as ac:
            check("app route unauthenticated -> 401",
                  (await ac.get("/api/rubrics")).status_code == 401)
            check("health stays public", (await ac.get("/health")).status_code == 200)

    print()
    print(f"{sum(results)}/{len(results)} checks passed")
    print("ACCOUNTS/AUTH PASS" if all(results) else "ACCOUNTS/AUTH FAIL")
    return 0 if all(results) else 1


sys.exit(asyncio.run(main()))
