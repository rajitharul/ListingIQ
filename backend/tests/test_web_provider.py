"""
End to end: search finds competitors anywhere, pages are read, nothing is invented.

This is the suite that proves the system is no longer Amazon-shaped. It also
pins the two honesty properties that are easiest to lose while composing layers:

  * a page we failed to read is still shown as a competitor, but is not scored,
    so our extraction failure cannot be graded as somebody's bad copy;
  * a total extraction outage stays `web_search` — discovery data is still
    observed data, and relabelling it "AI-estimated" would be a lie in the
    opposite direction to the one the provenance system exists to prevent.
"""
import asyncio, os, pathlib, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_tmp = tempfile.TemporaryDirectory()
os.environ["AUTH_DB_PATH"] = str(pathlib.Path(_tmp.name) / "auth.db")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ["SERPER_API_KEY"] = "sp-test"
os.environ["FIRECRAWL_API_KEY"] = "fc-test"

import httpx

import providers
import providers.http as phttp
from models.schemas import CategoryClassification, ExtractedEntities
from providers.web import WebSearchProvider

results = []
def check(label, passed, detail=""):
    results.append(passed)
    print(f"  {'ok  ' if passed else 'FAIL'} {label}{'  ' + str(detail) if detail else ''}")


CAT = CategoryClassification(vertical="Supplements", category="Minerals",
                             subcategory="Magnesium Glycinate")
ENT = ExtractedEntities(format_type="capsules")

# Shopping knows who sells what, at what price — but every link it returns is a
# google.com interstitial, so it supplies no addresses. Web search supplies the
# addresses and no commercial data. The provider joins them.
_REDIRECT = "https://www.google.com/search?ibp=oshop&q=mag&prds=catalogid:1"

SHOPPING = {"shopping": [
    {"title": "Doctor's Best High Absorption Magnesium 400mg", "source": "Amazon.com",
     "link": _REDIRECT, "price": "$18.49",
     "rating": 4.6, "ratingCount": 52130, "position": 1},
    {"title": "Spring Valley Magnesium Glycinate 120ct", "source": "Walmart",
     "link": _REDIRECT, "price": "$9.97",
     "rating": 4.2, "ratingCount": 880, "position": 2},
    {"title": "Pure For You Magnesium Glycinate 30 Capsules", "source": "Pure For You",
     "link": _REDIRECT, "price": "$12.50",
     "rating": 4.8, "ratingCount": 3800, "position": 3},
]}
WEB = {"organic": [
    {"title": "Doctor's Best High Absorption Magnesium 400mg",
     "link": "https://www.amazon.com/dp/B001", "position": 1},
    {"title": "Spring Valley Magnesium Glycinate 120ct",
     "link": "https://www.walmart.com/ip/222", "position": 2},
    {"title": "Magnesium Bisglycinate | Thorne",
     "link": "https://www.thorne.example/products/mag", "position": 3},
    {"title": "MyBrand Magnesium Glycinate",
     "link": "https://www.amazon.com/dp/OWN", "position": 4},
    {"title": "Magnesium - Wikipedia",
     "link": "https://en.wikipedia.org/wiki/Magnesium", "position": 5},
    {"title": "Best magnesium 2026 roundup",
     "link": "https://brand.example/blog/best-magnesium", "position": 6},
]}

def _ld(name, brand):
    return ('<html><head><script type="application/ld+json">'
            '{"@context":"https://schema.org","@type":"Product",'
            f'"name":"{name}","brand":{{"@type":"Brand","name":"{brand}"}},'
            f'"description":"{name} is a highly absorbable magnesium supplement '
            'supporting restful sleep and muscle relaxation after training."}'
            "</script></head><body>x</body></html>")


def _md(name):
    return (f"{name} supports restful sleep and muscle recovery overnight.\n"
            f"- {name}: highly absorbable magnesium, gentle on the stomach\n"
            "- 120 servings per container, third-party tested for purity\n"
            + f"{name} magnesium is well tolerated and easy to absorb. " * 6)


# Each URL serves its own page. Serving one body for every URL would trip the
# title-mismatch guard, which is exactly what that guard is for.
PAGES = {
    "/dp/B001": ("Doctor's Best High Absorption Magnesium 400mg", "Doctor's Best"),
    "/ip/222": ("Spring Valley Magnesium Glycinate 120ct", "Spring Valley"),
    "/products/mag": ("Magnesium Bisglycinate Thorne", "Thorne"),
}

REQS = []


def router(scrape=None):
    def handle(request: httpx.Request) -> httpx.Response:
        host, path = request.url.host, request.url.path
        REQS.append(f"{host}{path}")
        if "serper" in host:
            if path.endswith("/shopping"):
                return httpx.Response(200, json=SHOPPING)
            return httpx.Response(200, json=WEB)
        if "firecrawl" in host:
            if scrape:
                return scrape(request)
            target = (request.read().decode() if request.content else "")
            name, brand = next(
                ((n, b) for frag, (n, b) in PAGES.items() if frag in target),
                ("Generic Magnesium Glycinate", "Generic"))
            return httpx.Response(200, json={
                "success": True,
                "data": {"markdown": _md(name), "rawHtml": _ld(name, brand),
                         "metadata": {"title": name}}})
        raise AssertionError(f"unexpected host {host}")
    return handle


def use(h):
    phttp.make_client = lambda timeout=30.0: httpx.AsyncClient(
        timeout=timeout, transport=httpx.MockTransport(h))


def stub_llm():
    """
    Keep the suite offline.

    The model is only called when a page publishes no structured data, so this
    suite passed for a long time without a stub — and then reached the real
    OpenAI API the moment a test removed the JSON-LD. Every suite here is
    supposed to be free and offline; that has to be enforced, not assumed.
    """
    import types
    import agents.llm_client as lc
    from models.llm_responses import ExtractedPagesOut

    calls = {"n": 0}

    class _M:
        def __init__(s_, p): s_.parsed, s_.refusal = p, None
    class _C:
        def __init__(s_, p): s_.message = _M(p)
    class _U:
        prompt_tokens, completion_tokens = 10, 5
    class _Comp:
        def __init__(s_, p): s_.choices, s_.usage = [_C(p)], _U()

    async def parse(**kw):
        calls["n"] += 1
        # The model finds nothing the page did not publish — the honest answer
        # for a stub, and it keeps extraction quality attributable to the parser.
        return _Comp(ExtractedPagesOut(items=[]))

    client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(parse=parse)))
    lc._client = client
    lc.get_openai_client = lambda: client
    return calls


async def main():
    real = phttp.make_client
    phttp.DEFAULT_BASE_DELAY = phttp.DEFAULT_MAX_DELAY = 0.0
    llm_calls = stub_llm()

    print("\nmulti-platform discovery")
    REQS.clear()
    use(router())
    res = await WebSearchProvider().fetch(CAT, "amazon", brand_name="MyBrand",
                                          limit=10, entities=ENT)

    plats = {l.platform for l in res.listings}
    check("competitors come from MORE THAN ONE platform", len(plats) >= 2, plats)
    check("a marketplace is represented", "amazon" in plats)
    check("a second marketplace is represented", "walmart" in plats)
    check("a brand's own site is represented", "dtc" in plats, plats)
    check("the breakdown sums to the listings",
          sum(res.platform_breakdown.values()) == len(res.listings), res.platform_breakdown)

    check("the user's own listing is excluded",
          all("mybrand" not in l.title.lower() for l in res.listings),
          [l.title for l in res.listings])
    check("an encyclopaedia entry never becomes a competitor",
          all("wikipedia" not in l.url for l in res.listings))

    check("ranks are dense and unique",
          sorted(l.rank for l in res.listings) == list(range(1, len(res.listings) + 1)))
    check("every competitor we can read has a real URL",
          all(l.url.startswith("http") for l in res.listings if l.url))
    check("a competitor with a URL records its domain",
          all(l.domain for l in res.listings if l.url))
    check("no competitor points at a search-engine redirect",
          all("google.com/search" not in l.url for l in res.listings))

    print("\nprovenance")
    check("data_source is web_search", res.data_source == "web_search")
    check("it is recognised as observed data", res.is_live_data is True)
    check("fetched_at is recorded", bool(res.fetched_at))
    check("both channels are named",
          res.discovery_source == "serper" and "firecrawl" in res.extraction_source,
          res.extraction_source)
    check("the queries actually issued are recorded", len(res.queries) >= 2, res.queries)
    check("the note explains the platform mix",
          "platform" in res.provider_note, res.provider_note)

    print("\ndiscovery and the page do not overwrite each other")
    amazon = next(l for l in res.listings if l.platform == "amazon")
    check("price is grafted from the shopping result", amazon.price == "$18.49", amazon.price)
    check("rating is grafted too", amazon.rating == 4.6, amazon.rating)
    check("review count is grafted too", amazon.review_count == 52130)
    check("copy comes from the page", bool(amazon.bullet_points), amazon.bullet_points)
    check("brand comes from the page's structured data",
          amazon.brand_name == "Doctor's Best", amazon.brand_name)

    dtc = next(l for l in res.listings if l.platform == "dtc" and l.url)
    check("an unmatched web competitor has NO invented price", dtc.price == "", repr(dtc.price))
    check("an unmatched web competitor has NO invented rating",
          dtc.rating == 0.0 and dtc.review_count == 0)
    check("...but still has real copy from its page", bool(dtc.bullet_points))
    check("missing prices are reported", "without a published price" in res.provider_note)

    print("\nan unreadable page is shown but not scored")
    REQS.clear()
    use(router(scrape=lambda r: httpx.Response(200, json={
        "success": True, "data": {"markdown": "hi", "rawHtml": "", "metadata": {}}})))
    thin = await WebSearchProvider().fetch(CAT, "amazon", limit=10, entities=ENT)
    check("the competitors are still returned", len(thin.listings) >= 2, len(thin.listings))
    check("none of them is scoreable",
          all(not l.counts_toward_benchmark for l in thin.listings))
    check("each says why it could not be read",
          all(l.extraction_status in ("failed", "discovery_only") and l.extraction_note
              for l in thin.listings),
          [(l.extraction_status, l.extraction_note) for l in thin.listings][:1])
    check("no copy was invented for them",
          all(not l.bullet_points and not l.description for l in thin.listings))
    check("the shortfall is reported to the user",
          "could not be read" in thin.provider_note, thin.provider_note)
    check("it is STILL observed data, not relabelled as estimated",
          thin.data_source == "web_search" and thin.is_live_data is True)

    print("\nthe note counts what is actually excluded")
    # A page can return HTTP 200 and still yield no selling copy once navigation
    # is filtered out. Counting only errors made the note disagree with the
    # number of competitors actually scored.
    use(router(scrape=lambda r: httpx.Response(200, json={
        "success": True,
        "data": {"markdown": "Thorne Magnesium Bisglycinate supports sleep. " * 8,
                 "rawHtml": "", "metadata": {"title": "Thorne Magnesium Bisglycinate"}}})))
    nocopy = await WebSearchProvider().fetch(CAT, "amazon", limit=10, entities=ENT)
    unscored = sum(1 for l in nocopy.listings if not l.counts_toward_benchmark)
    if unscored:
        check("the note's count matches the competitors actually excluded",
              f"{unscored} of {len(nocopy.listings)}" in nocopy.provider_note,
              nocopy.provider_note)
    else:
        check("every competitor had enough copy to score", True)

    print("\na total extraction outage")
    use(router(scrape=lambda r: httpx.Response(402, json={})))
    out = await WebSearchProvider().fetch(CAT, "amazon", limit=10, entities=ENT)
    check("discovery alone still yields competitors", len(out.listings) >= 2)
    check("price and rating survive from discovery",
          any(l.price and l.rating for l in out.listings))
    check("provenance is NOT downgraded to llm_knowledge",
          out.data_source == "web_search", out.data_source)
    check("every page is marked discovery-only",
          out.discovery_only_count == len(out.listings), out.discovery_only_count)

    print("\nshopping results that have no address")
    meta = [l for l in res.listings if not l.url]
    if meta:
        check("a metadata-only competitor is still priced",
              all(l.price for l in meta), [l.price for l in meta])
        check("...and is never scored, since its page was never read",
              all(not l.counts_toward_benchmark for l in meta))
        check("...and says why", all("no page address" in l.extraction_note for l in meta),
              [l.extraction_note for l in meta][:1])
    else:
        check("every shopping result matched a real URL (nothing left unaddressable)", True)

    print("\ncost contract")
    REQS.clear()
    use(router())
    res2 = await WebSearchProvider().fetch(CAT, "amazon", limit=10, entities=ENT)
    serper_calls = sum(1 for r in REQS if "serper" in r)
    fc_calls = sum(1 for r in REQS if "firecrawl" in r)
    check("one search per planned query, no hidden fan-out", serper_calls == 3, serper_calls)
    addressable = [l for l in res2.listings if l.url]
    check("at most one page fetch per competitor",
          fc_calls <= len(res2.listings), (fc_calls, len(res2.listings)))
    check("exactly one fetch per addressable competitor, none repeated",
          fc_calls == len({l.url for l in addressable}), (fc_calls, len(addressable)))
    check("no credit is spent on a search-engine redirect",
          fc_calls == len(addressable), (fc_calls, len(addressable)))

    print("\ndiscovery failure falls back honestly")
    use(lambda r: httpx.Response(500, json={}) if "serper" in r.url.host
        else httpx.Response(200, json={"success": True, "data": {}}))
    import config
    config.COMPETITOR_PROVIDER = providers.COMPETITOR_PROVIDER = "web"
    providers.COMPETITOR_ALLOW_FALLBACK = True

    class FakeLLM:
        name = "llm_knowledge"
        async def fetch(self, category, platform, brand_name="", limit=10):
            from models.schemas import CompetitorListing, CompetitorScoutResult
            return CompetitorScoutResult(
                listings=[CompetitorListing(rank=1, title="Estimated")],
                data_source="llm_knowledge", platform=platform)
    real_llm = providers.LLMProvider
    providers.LLMProvider = FakeLLM
    try:
        fb = await providers.fetch_competitors(CAT, "amazon", "MyBrand", 10, entities=ENT)
        check("a discovery outage falls back to estimates", fb.data_source == "llm_knowledge")
        check("the fallback is NOT labelled as observed", fb.is_live_data is False)
        check("the fallback explains itself", "unavailable" in fb.provider_note, fb.provider_note)
        check("estimated competitors are never cached",
              await providers.cache.get("amazon", CAT.subcategory) is None)
    finally:
        providers.LLMProvider = real_llm

    check("the suite never reached a live model API", True, f"{llm_calls['n']} stubbed call(s)")

    phttp.make_client = real

    print()
    print(f"{sum(results)}/{len(results)} checks passed")
    print("WEB PROVIDER PASS" if all(results) else "WEB PROVIDER FAIL")
    return 0 if all(results) else 1


sys.exit(asyncio.run(main()))
