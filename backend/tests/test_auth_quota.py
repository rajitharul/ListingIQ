"""
Offline tests for API-key auth and quota enforcement.

Drives the real FastAPI app over ASGI with a temporary auth database and a
stubbed model, so nothing here touches OpenAI or the developer's own data.
"""
import asyncio, os, pathlib, sys, tempfile, types

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_tmp = tempfile.TemporaryDirectory()
os.environ["AUTH_DB_PATH"] = str(pathlib.Path(_tmp.name) / "auth.db")
os.environ["AUTH_ENABLED"] = "true"
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-a-real-key")
os.environ["LLM_RETRY_BASE_DELAY"] = "0.01"

import httpx
import accounts
import agents.llm_client as lc
from pydantic import BaseModel
import typing


def sample(model, depth=0):
    vals = {}
    for name, f in model.model_fields.items():
        ann = f.annotation
        if typing.get_origin(ann) is list:
            (inner,) = typing.get_args(ann)
            if isinstance(inner, type) and issubclass(inner, BaseModel):
                vals[name] = [sample(inner, depth + 1)] if depth < 2 else []
            else:
                vals[name] = [inner("x") if inner is str else inner(1)]
        elif isinstance(ann, type) and issubclass(ann, BaseModel):
            vals[name] = sample(ann, depth + 1)
        elif ann is bool: vals[name] = True
        elif ann is int: vals[name] = 3
        elif ann is float: vals[name] = 1.0
        else: vals[name] = f"{name}-value"
    return model(**vals)


class _Msg:
    def __init__(self, p): self.parsed, self.refusal = p, None
class _Choice:
    def __init__(self, p): self.message = _Msg(p)
class _Usage:
    prompt_tokens, completion_tokens = 1000, 500
class _Completion:
    def __init__(self, p): self.choices, self.usage = [_Choice(p)], _Usage()


def stub_model(delay=0.0):
    async def parse(*, model, messages, response_format, **kw):
        if delay:
            await asyncio.sleep(delay)
        return _Completion(sample(response_format))
    client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(parse=parse)))
    lc._client = client
    lc.get_openai_client = lambda: client


LISTING = {
    "listing_input": {
        "product_title": "Magnesium 500mg 120 Capsules",
        "product_description": "Magnesium supplement capsules.",
        "bullet_points": ["500mg per capsule"],
        "brand_name": "HealthPlus", "platform": "amazon", "target_audience": "",
    },
    "session_id": "test",
}

results = []
def check(label, passed, detail=""):
    results.append(passed)
    print(f"  {'ok  ' if passed else 'FAIL'} {label}{'  ' + str(detail) if detail else ''}")


async def main():
    stub_model()
    import auth, quota
    from main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:

        # ── Auth ─────────────────────────────────────────────────
        r = await c.get("/health")
        check("health is public", r.status_code == 200, r.status_code)

        r = await c.post("/api/pipeline", json=LISTING)
        check("no key -> 401", r.status_code == 401, r.status_code)

        r = await c.post("/api/pipeline", json=LISTING, headers={"X-API-Key": "liq_live_bogus"})
        check("bad key -> 401", r.status_code == 401, r.status_code)

        r = await c.get("/api/rubrics")
        check("cheap route also needs a key", r.status_code == 401, r.status_code)

        acct = await accounts.create_account(
            "test@co.com", "supersecret123", rpm_limit=4,
            max_concurrent=1, daily_token_limit=4000)
        key_id, raw = await auth.create_key(acct.account_id, "Test Co")
        H = {"X-API-Key": raw}

        r = await c.get("/api/rubrics", headers=H)
        check("valid key -> 200", r.status_code == 200, r.status_code)

        # ── Revocation is immediate ──────────────────────────────
        acct2 = await accounts.create_account("revoked@co.com", "supersecret123")
        kid2, raw2 = await auth.create_key(acct2.account_id, "Revoked Co")
        await auth.revoke_key(kid2)
        r = await c.get("/api/rubrics", headers={"X-API-Key": raw2})
        check("revoked key -> 401", r.status_code == 401, r.status_code)

        # ── Keys are stored hashed, never in the clear ───────────
        from store import connect as _connect
        db = await _connect()
        try:
            cur = await db.execute("SELECT key_hash FROM api_keys WHERE key_id = ?", (key_id,))
            stored = (await cur.fetchone())[0]
        finally:
            await db.close()
        check("key stored hashed, not raw", stored != raw and stored == auth.hash_key(raw))

        # ── Rate limit ───────────────────────────────────────────
        quota.reset_for_tests()
        codes = [(await c.get("/api/rubrics", headers=H)).status_code for _ in range(6)]
        check("rpm limit trips after 4", codes == [200, 200, 200, 200, 429, 429], codes)
        r = await c.get("/api/rubrics", headers=H)
        check("429 carries Retry-After", "retry-after" in r.headers, dict(r.headers))

        # ── Pipeline runs and meters tokens ──────────────────────
        quota.reset_for_tests()
        r = await c.post("/api/pipeline", json=LISTING, headers=H)
        check("pipeline runs with a key", r.status_code == 200, r.status_code)
        usage = await quota.get_usage_today(acct.account_id)
        check("tokens metered to the key", usage["tokens"] > 0, usage)
        check("run counted", usage["runs"] == 1, usage["runs"])

        # ── Daily budget ─────────────────────────────────────────
        quota.reset_for_tests()
        r = await c.post("/api/pipeline", json=LISTING, headers=H)
        check("budget exhausted -> 429", r.status_code == 429, r.status_code)
        check("429 explains the budget", "budget" in r.json()["detail"].lower(),
              r.json()["detail"])

        # ── Concurrency, on a key with budget left ───────────────
        quota.reset_for_tests()
        stub_model(delay=0.25)
        acct3 = await accounts.create_account(
            "concurrent@co.com", "supersecret123", rpm_limit=100,
            max_concurrent=1, daily_token_limit=10_000_000)
        kid3, raw3 = await auth.create_key(acct3.account_id, "Concurrent Co")
        H3 = {"X-API-Key": raw3}
        both = await asyncio.gather(
            c.post("/api/pipeline", json=LISTING, headers=H3),
            c.post("/api/pipeline", json=LISTING, headers=H3),
        )
        codes = sorted(r.status_code for r in both)
        check("2nd concurrent run rejected", codes == [200, 429], codes)

        # ── Slot is released after the run ───────────────────────
        stub_model()
        r = await c.post("/api/pipeline", json=LISTING, headers=H3)
        check("slot freed after completion", r.status_code == 200, r.status_code)

        # ── SSE admission happens before the stream starts ───────
        # A fresh key is admitted even with a tiny budget: cost is only known
        # after a run, so the check is "already over", not "might go over".
        quota.reset_for_tests()
        acct4 = await accounts.create_account(
            "stream@co.com", "supersecret123", rpm_limit=100,
            max_concurrent=1, daily_token_limit=1000)
        kid4, raw4 = await auth.create_key(acct4.account_id, "Stream Co")
        H4 = {"X-API-Key": raw4}
        r = await c.post("/api/pipeline/stream", json=LISTING, headers=H4)
        check("SSE runs for a key in budget", r.status_code == 200, r.status_code)

        await quota.record_usage(acct4.account_id, 5000, 5000)   # now well over its 1000
        r = await c.post("/api/pipeline/stream", json=LISTING, headers=H4)
        check("SSE over budget -> real 429, not a broken stream",
              r.status_code == 429, r.status_code)
        check("SSE 429 is JSON, not a stream",
              r.headers.get("content-type", "").startswith("application/json"),
              r.headers.get("content-type"))

        # ── /api/usage reports the caller's own spend ────────────
        quota.reset_for_tests()
        r = await c.get("/api/usage", headers=H3)
        body = r.json()
        check("/api/usage returns the caller's quota",
              r.status_code == 200 and body["email"] == "concurrent@co.com" and body["via"] == "api_key"
              and body["tokens"] > 0 and "tokens_remaining" in body, body)

    print()
    print(f"{sum(results)}/{len(results)} checks passed")
    print("AUTH/QUOTA PASS" if all(results) else "AUTH/QUOTA FAIL")
    return 0 if all(results) else 1


sys.exit(asyncio.run(main()))
