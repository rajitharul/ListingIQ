"""
A product with a real rubric must never be scored on the generic one.

`resolve_subcategory` tested containment one way only — `query in canonical` —
so a classifier naming the product in its own words was resolved correctly when
it said less than the canonical name ("creatine") and dropped to the generic
fallback when it said more ("Creatine Monohydrate Powder"). Nothing failed
loudly: the run completed, the UI said "benchmarked for Other", and a creatine
listing was graded on nine generic dimensions while
`supplements_creatine_monohydrate.json` sat unused on disk.

Also pins the Firecrawl request shape. `onlyMainContent: True` returned page
chrome rather than product copy on storefronts whose copy sits outside a main
landmark, every page failed the quality guard, and the benchmark came back
empty with all competitors marked "not scored".
"""
import os, pathlib, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_tmp = tempfile.TemporaryDirectory()
os.environ["AUTH_DB_PATH"] = str(pathlib.Path(_tmp.name) / "auth.db")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("FIRECRAWL_API_KEY", "fc-test")

from data.rubrics.loader import load_rubric, resolve_subcategory

results = []
def check(label, passed, detail=""):
    results.append(passed)
    print(f"  {'ok  ' if passed else 'FAIL'} {label}{'  ' + str(detail) if detail else ''}")


# ── the regression: a longer name than the canonical one ─────────
print("\nsubcategory resolution")

CREATINE = "Creatine Monohydrate"

check("exact canonical name", resolve_subcategory(CREATINE) == CREATINE)
check("alias table still wins", resolve_subcategory("creatine") == CREATINE)
check("shorter-than-canonical still resolves",
      resolve_subcategory("Creatine Powder") == CREATINE)

# These four are the bug. Each one used to return None.
for spoken in ("Creatine Monohydrate Powder",
               "Creatine Monohydrate Supplement",
               "Micronized Creatine Monohydrate",
               "creatine monohydrate powder 300g"):
    check(f"longer form resolves: {spoken!r}",
          resolve_subcategory(spoken) == CREATINE,
          resolve_subcategory(spoken))

check("a real rubric is loaded, not the generic one",
      (load_rubric("Creatine Monohydrate Powder") or None) is not None
      and load_rubric("Creatine Monohydrate Powder").subcategory == CREATINE)

# Skincare uses the same path, so the fix must hold there too.
check("skincare longer form resolves",
      resolve_subcategory("Vitamin C Serum 20%") == "Vitamin C Serum",
      resolve_subcategory("Vitamin C Serum 20%"))

# Longest match wins, so the answer cannot depend on dict iteration order.
d3k2 = resolve_subcategory("Vitamin D3 + K2 Softgels")
check("longest canonical name wins over a shorter partial",
      d3k2 == "Vitamin D3 + K2", d3k2)

# Still honest about genuinely unknown products: the generic rubric exists for
# these, and pretending to know the category would be worse than admitting it.
check("unrelated product stays unresolved",
      resolve_subcategory("Bluetooth Headphones") is None,
      resolve_subcategory("Bluetooth Headphones"))
check("empty query stays unresolved", resolve_subcategory("") is None)


# ── the Firecrawl request shape ──────────────────────────────────
print("\nfirecrawl request")

import httpx
from providers import http as phttp
from providers.extract.firecrawl import FirecrawlExtractor

sent = {}

class _Capture(httpx.AsyncClient):
    pass

def _stub(timeout=30.0):
    def handler(request):
        import json as _json
        sent.update(_json.loads(request.content))
        return httpx.Response(200, json={"success": True, "data": {
            "markdown": "Nutricost Creatine Monohydrate Powder. " * 20,
            "rawHtml": "<html></html>"}})
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=timeout)


async def _run():
    real = phttp.make_client
    phttp.make_client = _stub
    try:
        async with phttp.make_client(5) as c:
            await FirecrawlExtractor().extract_one(
                c, "https://example.com/p/creatine",
                expected_title="Nutricost Creatine Monohydrate Powder")
    finally:
        phttp.make_client = real

import asyncio
asyncio.run(_run())

check("a request was actually captured", bool(sent), sorted(sent))
check("onlyMainContent is False — True returned page chrome, not product copy",
      sent.get("onlyMainContent") is False, sent.get("onlyMainContent"))
check("rawHtml is still requested, so JSON-LD stays the first choice",
      "rawHtml" in (sent.get("formats") or []), sent.get("formats"))

print()
print(f"{sum(results)}/{len(results)} checks passed")
print("RUBRIC RESOLUTION PASS" if all(results) else "RUBRIC RESOLUTION FAIL")
sys.exit(0 if all(results) else 1)
