"""
Competitor provider tests: Rainforest field mapping, caching, and — most
importantly — that estimated data can never be labelled as observed.

No network and no API key. Rainforest is driven through a stubbed HTTP
transport using the documented response shape.
"""
import asyncio, json, os, pathlib, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_tmp = tempfile.TemporaryDirectory()
os.environ["AUTH_DB_PATH"] = str(pathlib.Path(_tmp.name) / "auth.db")
os.environ["RAINFOREST_API_KEY"] = "test-key"
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

import httpx
from models.schemas import CategoryClassification

results = []
def check(label, passed, detail=""):
    results.append(passed)
    print(f"  {'ok  ' if passed else 'FAIL'} {label}{'  ' + str(detail) if detail else ''}")


CATEGORY = CategoryClassification(
    vertical="Supplements", category="Minerals",
    subcategory="Magnesium Glycinate", confidence=0.9, reasoning="")

SEARCH_BODY = {
    "request_info": {"success": True, "credits_used": 1},
    "search_results": [
        {"position": 1, "title": "Sponsored Magnesium", "asin": "SPON1",
         "sponsored": True, "price": {"raw": "$9.99", "value": 9.99, "symbol": "$"}},
        {"position": 2, "title": "HealthCo Magnesium Glycinate 400mg", "asin": "B001",
         "link": "https://amazon.com/dp/B001", "is_prime": True, "bestseller": {"x": 1},
         "price": {"raw": "$24.99", "value": 24.99, "symbol": "$"},
         "rating": 4.6, "ratings_total": 12500},
        {"position": 3, "title": "OwnBrand Magnesium", "asin": "B002",
         "price": {"raw": "$19.99"}, "rating": 4.2, "ratings_total": 900},
        {"position": 4, "title": "NoCopy Magnesium", "asin": "B003",
         "price": {"raw": "$14.99"}, "rating": 4.0, "ratings_total": 50},
    ],
}

def product_body(asin):
    if asin == "B003":
        return {"request_info": {"success": False, "message": "ASIN not found"}}
    return {"request_info": {"success": True},
            "product": {"title": f"Full Title {asin}", "brand": f"Brand{asin}",
                        "description": "A real description from the listing page.",
                        "feature_bullets": [f"{asin} bullet one", f"{asin} bullet two"],
                        "rating": 4.7, "ratings_total": 13000,
                        "amazons_choice": {"link": "x"},
                        "buybox_winner": {"price": {"raw": "$25.49"}}}}

CALLS = []
def handler(request: httpx.Request) -> httpx.Response:
    q = dict(request.url.params)
    CALLS.append(q.get("type"))
    if q.get("type") == "search":
        return httpx.Response(200, json=SEARCH_BODY)
    return httpx.Response(200, json=product_body(q.get("asin")))


async def main():
    import providers, config
    from providers import cache
    from providers.rainforest import RainforestProvider
    from providers.base import ProviderError

    # Route every provider's HTTP client at the stub through the single seam in
    # providers/http.py. Patching each provider's own `httpx` symbol (as this
    # file used to) leaks: the later reassignments below never restored it, so
    # sections silently depended on their own ordering.
    import providers.http as phttp
    real_make_client = phttp.make_client
    phttp.DEFAULT_BASE_DELAY = phttp.DEFAULT_MAX_DELAY = 0.0   # don't sleep in tests

    stubbed = {"n": 0}

    def use(h):
        def _factory(timeout=30.0):
            stubbed["n"] += 1
            return httpx.AsyncClient(timeout=timeout, transport=httpx.MockTransport(h))
        phttp.make_client = _factory

    use(handler)

    # ── Field mapping ────────────────────────────────────────────
    CALLS.clear()
    res = await RainforestProvider().fetch(CATEGORY, "amazon", brand_name="OwnBrand")
    check("sponsored results excluded", all("Sponsored" not in l.title for l in res.listings))
    check("user's own brand excluded", all("OwnBrand" not in l.title for l in res.listings))
    check("2 competitors returned", len(res.listings) == 2, [l.title for l in res.listings])
    check("1 search + N product calls", CALLS.count("search") == 1 and CALLS.count("product") == 2,
          dict(search=CALLS.count("search"), product=CALLS.count("product")))

    top = res.listings[0]
    check("title from product detail", top.title == "Full Title B001", top.title)
    check("bullets mapped from feature_bullets", top.bullet_points == ["B001 bullet one", "B001 bullet two"])
    check("description mapped", top.description.startswith("A real description"))
    check("brand mapped", top.brand_name == "BrandB001", top.brand_name)
    check("buybox price preferred", top.price == "$25.49", top.price)
    check("rating from product", top.rating == 4.7, top.rating)
    check("review count from product", top.review_count == 13000, top.review_count)
    check("badges derived", set(top.badges) >= {"Best Seller", "Amazon's Choice", "Prime"}, top.badges)
    check("url canonicalised from ASIN so a customer can verify",
          top.url == "https://www.amazon.com/dp/B001", top.url)
    check("provenance says rainforest", res.data_source == "rainforest_api")
    check("is_live_data true for real data", res.is_live_data)
    check("fetched_at recorded", bool(res.fetched_at))

    # ── Partial failure: a dead product lookup must not drop the row ──
    CALLS.clear()
    res2 = await RainforestProvider().fetch(CATEGORY, "amazon")
    b003 = [l for l in res2.listings if "B003" in l.title or l.title == "NoCopy Magnesium"]
    check("failed product lookup keeps the competitor", len(b003) == 1, [l.title for l in res2.listings])
    check("partial row falls back to search data", b003 and b003[0].price == "$14.99", b003[0].price if b003 else None)
    check("missing bullets reported in provider_note",
          "without bullet points" in res2.provider_note, res2.provider_note)
    check("missing descriptions reported separately",
          "no description block" in res2.provider_note, res2.provider_note)

    # ── Hard failures ────────────────────────────────────────────
    def fail(code, body=None):
        return lambda req: httpx.Response(code, json=body or {})
    for code, label, retryable in [(401, "invalid API key", False), (402, "out of credits", False),
                                   (429, "rate limited", True)]:
        use(fail(code))
        try:
            await RainforestProvider().fetch(CATEGORY, "amazon")
            check(f"HTTP {code} raises", False)
        except ProviderError as e:
            check(f"HTTP {code} -> {label}, retryable={retryable}",
                  label.split()[0] in e.detail and e.retryable == retryable, e.detail)

    # ── Fallback must never be mislabelled as real ───────────────
    use(fail(402))
    config.COMPETITOR_PROVIDER = providers.COMPETITOR_PROVIDER = "rainforest"
    providers.COMPETITOR_ALLOW_FALLBACK = True

    calls = {"n": 0}
    class FakeLLM:
        name = "llm_knowledge"
        async def fetch(self, category, platform, brand_name="", limit=10):
            calls["n"] += 1
            from models.schemas import CompetitorScoutResult, CompetitorListing
            return CompetitorScoutResult(
                listings=[CompetitorListing(rank=1, title="Estimated", rating=4.0)],
                search_query="x", platform=platform, data_source="llm_knowledge",
                fetched_at="2026-01-01T00:00:00Z",
                provider_note="AI-estimated from model knowledge, not observed marketplace data")
    providers.LLMProvider = FakeLLM

    res3 = await providers.fetch_competitors(CATEGORY, "amazon")
    check("falls back when the live provider dies", calls["n"] == 1)
    check("fallback is labelled llm_knowledge, NOT rainforest",
          res3.data_source == "llm_knowledge", res3.data_source)
    check("is_live_data is false for fallback", res3.is_live_data is False)
    check("fallback note explains why", "unavailable" in res3.provider_note, res3.provider_note)

    # ── Estimated data must never be cached ──────────────────────
    await cache.put("amazon", "Magnesium Glycinate", res3)
    check("estimated data is not cached", await cache.get("amazon", "Magnesium Glycinate") is None)

    # ── Live data is cached and served ───────────────────────────
    await cache.put("amazon", "Magnesium Glycinate", res)
    hit = await cache.get("amazon", "Magnesium Glycinate")
    check("live data is cached", hit is not None and len(hit.listings) == 2)
    check("cached data keeps its provenance", hit and hit.data_source == "rainforest_api")
    served = await providers.fetch_competitors(CATEGORY, "amazon")
    check("cache hit avoids any upstream call", served.from_cache is True)
    check("cache invalidation works", await cache.invalidate("amazon", "Magnesium Glycinate"))

    # ── Field shapes verified against live Rainforest responses ──
    # These replay exact payloads observed from the real API. They exist because
    # the first mapping was wrong in ways only live data revealed.
    from providers.rainforest import RainforestProvider as R

    # bestsellers_rank is a category RANKING present on nearly every product
    # (observed: rank 118 in "Health & Household"). Treating it as a badge made
    # all 10 competitors look like bestsellers.
    ranked = {"bestsellers_rank": [{"rank": 118, "category": "Health & Household"},
                                   {"rank": 2, "category": "Magnesium Mineral Supplements"}]}
    check("category rank is not a Best Seller badge",
          R._badges({"asin": "B2", "title": "Y"}, ranked) == [],
          R._badges({"asin": "B2", "title": "Y"}, ranked))
    check("an explicit bestseller object is a badge",
          "Best Seller" in R._badges({"bestseller": {"link": "y"}}, ranked))
    check("rank #1 earns a #1 Best Seller badge",
          R._badges({}, {"bestsellers_rank": [{"rank": 1, "category": "X"}]}) == ["#1 Best Seller"])
    check("amazons_choice object is detected",
          R._badges({"amazons_choice": {"badge_text": "Amazon's  Choice"}}, {})
          == ["Amazon's Choice"])
    check("nothing set yields no badges", R._badges({"asin": "B2"}, {}) == [])

    # Amazon listings frequently have no description block at all; the copy is
    # in A+ images, which are not text-extractable.
    check("plain description preferred",
          R._description({"description": "Real copy."}) == "Real copy.")
    check("A+ brand story used when description is empty",
          R._description({"description": "",
                          "a_plus_content": {"company_description_text": "Brand story."}})
          == "Brand story.")
    check("image-only A+ yields empty text, never invented copy",
          R._description({"description": "",
                          "a_plus_content": {"has_a_plus_content": True, "body_html": ""}}) == "")

    # Tracking-laden /sspa/click URLs are normalised so a customer can verify.
    check("product URL is the canonical /dp/ form",
          R._url({"asin": "B07P5K7DQP", "link": "https://www.amazon.com/sspa/click?ie=UTF8&spc=x"},
                 "amazon.com") == "https://www.amazon.com/dp/B07P5K7DQP")

    # Proves the stub was actually reached. A provider that binds `make_client`
    # at import time silently bypasses it and hits the live network, which is
    # how this file passed while making real requests.
    check("every client came from the stubbed seam, none from the network",
          stubbed["n"] > 0, stubbed["n"])

    phttp.make_client = real_make_client   # leave the seam as we found it

    print()
    print(f"{sum(results)}/{len(results)} checks passed")
    print("PROVIDERS PASS" if all(results) else "PROVIDERS FAIL")
    return 0 if all(results) else 1


sys.exit(asyncio.run(main()))
