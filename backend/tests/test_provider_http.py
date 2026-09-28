"""
`ProviderError.retryable` must mean something.

The flag was set in five places in `rainforest.py` and read nowhere: there was
no retry loop in the provider layer at all, so a single upstream 429 failed a
whole fetch while the LLM client retried the identical class of failure. These
tests pin that `providers/http.request_json` honours the flag in both
directions, and that the shared client factory is the one seam tests patch.
"""
import asyncio, os, pathlib, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_tmp = tempfile.TemporaryDirectory()
os.environ["AUTH_DB_PATH"] = str(pathlib.Path(_tmp.name) / "auth.db")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

import httpx

import providers.http as ph
from providers.base import ProviderError

results = []
def check(label, passed, detail=""):
    results.append(passed)
    print(f"  {'ok  ' if passed else 'FAIL'} {label}{'  ' + str(detail) if detail else ''}")


def classify(response: httpx.Response) -> ProviderError | None:
    """A representative vendor taxonomy."""
    if response.status_code == 401:
        return ProviderError("t", "invalid API key", retryable=False)
    if response.status_code == 402:
        return ProviderError("t", "out of credits", retryable=False)
    if response.status_code == 429:
        return ProviderError("t", "rate limited", retryable=True)
    if response.status_code >= 400:
        return ProviderError("t", f"HTTP {response.status_code}", retryable=True)
    return None


def client_for(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def main():
    # Keep the suite fast: the backoff policy is exercised, not slept through.
    ph.DEFAULT_BASE_DELAY = 0.0
    ph.DEFAULT_MAX_DELAY = 0.0

    print("\nretry policy")

    calls = {"n": 0}
    def flaky(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, json={"e": "slow down"})
        return httpx.Response(200, json={"ok": True})

    async with client_for(flaky) as c:
        body = await ph.request_json(c, "GET", "https://x.test/a",
                                     provider="t", classify=classify, retries=2)
    check("a retryable failure is retried and can succeed", body == {"ok": True}, body)
    check("it retried exactly until success", calls["n"] == 3, calls["n"])

    calls["n"] = 0
    def always_401(request):
        calls["n"] += 1
        return httpx.Response(401, json={"e": "nope"})

    err = None
    async with client_for(always_401) as c:
        try:
            await ph.request_json(c, "GET", "https://x.test/a",
                                  provider="t", classify=classify, retries=2)
        except ProviderError as e:
            err = e
    check("a NON-retryable failure is not retried", calls["n"] == 1, calls["n"])
    check("it raises with the vendor's detail", err and "invalid API key" in err.detail, err)
    check("and stays marked non-retryable", err and err.retryable is False)

    calls["n"] = 0
    def always_429(request):
        calls["n"] += 1
        return httpx.Response(429, json={})

    err = None
    async with client_for(always_429) as c:
        try:
            await ph.request_json(c, "GET", "https://x.test/a",
                                  provider="t", classify=classify, retries=2)
        except ProviderError as e:
            err = e
    check("retries are bounded, not infinite", calls["n"] == 3, calls["n"])
    check("exhaustion raises the last error", err and "rate limited" in err.detail)

    print("\ntransport failures")

    calls["n"] = 0
    def timeout(request):
        calls["n"] += 1
        raise httpx.ReadTimeout("too slow", request=request)

    err = None
    async with client_for(timeout) as c:
        try:
            await ph.request_json(c, "GET", "https://x.test/a",
                                  provider="t", classify=classify, retries=1)
        except ProviderError as e:
            err = e
    check("a timeout is retried", calls["n"] == 2, calls["n"])
    check("a timeout surfaces as a ProviderError", err and "timed out" in err.detail, err)

    calls["n"] = 0
    def bad_json(request):
        calls["n"] += 1
        return httpx.Response(200, text="<html>not json</html>")

    err = None
    async with client_for(bad_json) as c:
        try:
            await ph.request_json(c, "GET", "https://x.test/a",
                                  provider="t", classify=classify, retries=2)
        except ProviderError as e:
            err = e
    check("a non-JSON body is NOT retried — replaying cannot help", calls["n"] == 1, calls["n"])
    check("non-JSON is reported as such", err and "non-JSON" in err.detail, err)

    print("\nrequest shaping")

    seen = {}
    def echo(request):
        seen["headers"] = dict(request.headers)
        seen["method"] = request.method
        seen["body"] = request.content
        return httpx.Response(200, json={"ok": 1})

    async with client_for(echo) as c:
        await ph.request_json(c, "POST", "https://x.test/s", provider="t",
                              classify=classify, json_body={"q": "magnesium"},
                              headers={"X-API-KEY": "secret"})
    check("POST body is sent as JSON", b"magnesium" in seen["body"], seen["body"])
    check("custom auth headers reach the vendor", seen["headers"].get("x-api-key") == "secret")
    check("method is honoured", seen["method"] == "POST")

    print("\nthe test seam")
    check("make_client is the single patch point", callable(ph.make_client))
    check("make_client returns an httpx client",
          isinstance(ph.make_client(1.0), httpx.AsyncClient))

    print()
    print(f"{sum(results)}/{len(results)} checks passed")
    print("PROVIDER HTTP PASS" if all(results) else "PROVIDER HTTP FAIL")
    return 0 if all(results) else 1


sys.exit(asyncio.run(main()))
