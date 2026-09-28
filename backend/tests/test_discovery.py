"""
Discovery finds competitors anywhere, and never invents what it did not see.

Two things are easy to get wrong here and expensive to notice later:

  * An organic web result carries no price and no rating. Recording those as
    0.0 makes "competitors average 2.2 stars" look like a market fact when it
    is an absence of data.
  * The same product sold on a marketplace and on the brand's own site has two
    different titles. Counted twice it is scored twice and pulls the mean.
"""
import asyncio, os, pathlib, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_tmp = tempfile.TemporaryDirectory()
os.environ["AUTH_DB_PATH"] = str(pathlib.Path(_tmp.name) / "auth.db")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ["SERPER_API_KEY"] = "test-key"

import httpx

import providers.http as phttp
from models.schemas import CategoryClassification, ExtractedEntities
from providers.base import ProviderError
from providers.discovery.base import Candidate
from providers.discovery import merge as merge_mod
from providers.discovery.merge import merge_candidates, exclude_own_brand
from providers.discovery.serper import SerperDiscovery, looks_like_product
from providers.query import build_query_plan

results = []
def check(label, passed, detail=""):
    results.append(passed)
    print(f"  {'ok  ' if passed else 'FAIL'} {label}{'  ' + str(detail) if detail else ''}")


CAT = CategoryClassification(vertical="Supplements", category="Minerals",
                             subcategory="Magnesium Glycinate")
ENT = ExtractedEntities(format_type="capsules")

# Mirrors the live API: every shopping `link` is a google.com/search
# interstitial, never the merchant's own page.
def _redirect(q="x"):
    return f"https://www.google.com/search?ibp=oshop&q={q}&prds=catalogid:123"

SHOPPING = {"shopping": [
    {"title": "Doctor's Best High Absorption Magnesium 400mg", "source": "Amazon.com",
     "link": _redirect(), "price": "$18.49",
     "rating": 4.6, "ratingCount": 52130, "position": 1, "productId": "pid-1"},
    {"title": "Spring Valley Magnesium Glycinate", "source": "Walmart",
     "link": _redirect(), "price": "$9.97",
     "rating": 4.2, "ratingCount": 880, "position": 2},
    {"title": "", "source": "Nowhere", "price": "$1"},
]}
WEB = {"organic": [
    {"title": "Magnesium Glycinate 400mg | Thorne", "link": "https://www.thorne.example/products/mag",
     "snippet": "…", "position": 1},
    {"title": "Magnesium - Wikipedia", "link": "https://en.wikipedia.org/wiki/Magnesium", "position": 2},
    {"title": "Best magnesium 2026", "link": "https://brand.example/blog/best-magnesium", "position": 3},
]}

CALLS = []


def handler(request: httpx.Request) -> httpx.Response:
    CALLS.append(str(request.url).rsplit("/", 1)[-1])
    assert request.headers.get("x-api-key") == "test-key", "key must travel in the header"
    if request.url.path.endswith("/shopping"):
        return httpx.Response(200, json=SHOPPING)
    if request.url.path.endswith("/search"):
        return httpx.Response(200, json=WEB)
    raise AssertionError(f"unexpected path {request.url.path}")


def use(h):
    phttp.make_client = lambda timeout=30.0: httpx.AsyncClient(
        timeout=timeout, transport=httpx.MockTransport(h))


async def main():
    real = phttp.make_client
    phttp.DEFAULT_BASE_DELAY = phttp.DEFAULT_MAX_DELAY = 0.0
    use(handler)

    plan = build_query_plan(CAT, ENT, platform="amazon", brand_name="MyBrand", limit=10)

    print("\nserper mapping")
    CALLS.clear()
    cands = await SerperDiscovery().discover(plan)

    check("both channels are queried",
          CALLS.count("shopping") == len(plan.shopping) and CALLS.count("search") == len(plan.web),
          CALLS)

    shop = [c for c in cands if c.channel == "shopping"]
    web = [c for c in cands if c.channel == "web"]

    top = shop[0]
    check("merchant comes from `source`", top.merchant == "Amazon.com", top.merchant)
    check("price is preserved verbatim, not reformatted", top.price == "$18.49", top.price)
    check("rating maps through", top.rating == 4.6, top.rating)
    check("ratingCount becomes review_count", top.review_count == 52130, top.review_count)
    check("productId is captured for exact dedupe", top.product_id == "pid-1")
    check("an untitled result is dropped", len(shop) == 2, len(shop))
    check("a second merchant is represented",
          any(c.platform == "walmart" for c in shop))

    # The live API returns every shopping link as a google.com interstitial.
    # Carrying it would mean fetching a Google Shopping page and scoring it as
    # somebody's listing copy.
    check("a shopping result carries NO url — its link is a redirect",
          all(c.url == "" for c in shop), [c.url for c in shop])
    check("platform comes from the merchant name instead",
          top.platform == "amazon", top.platform)
    check("an unknown merchant is a brand site, not a marketplace",
          SerperDiscovery._from_shopping(
              [{"title": "x", "source": "Life Extension"}])[0].platform == "dtc")

    check("a web result carries NO price", all(c.price == "" for c in web), [c.price for c in web])
    check("a web result carries NO rating — absence, not zero stars",
          all(c.rating == 0.0 and c.review_count == 0 for c in web))
    check("a web result is flagged as having no commercial signal",
          all(not c.has_commercial_signal for c in web))
    check("shopping results DO have a commercial signal",
          all(c.has_commercial_signal for c in shop))
    check("an unknown storefront resolves to dtc, not a marketplace",
          web and web[0].platform == "dtc", [c.platform for c in web])

    print("\nnon-product filtering")
    check("an encyclopaedia entry is not a competitor",
          not looks_like_product("https://en.wikipedia.org/wiki/Magnesium"))
    check("a blog round-up is not a competitor",
          not looks_like_product("https://brand.example/blog/best-magnesium"))
    check("a health publisher is not a competitor",
          not looks_like_product("https://www.healthline.com/nutrition/magnesium"))
    check("a real product page survives",
          looks_like_product("https://www.thorne.example/products/mag"))
    # Every web query returns the same stub, so the product URL legitimately
    # appears once per query; duplicates are collapsed at merge, not here.
    check("non-product results were actually filtered out",
          {c.url for c in web} == {"https://www.thorne.example/products/mag"},
          [c.url for c in web])
    check("a marketplace search page is not a competitor",
          not looks_like_product("https://www.amazon.com/x/s?k=magnesium"))
    check("a google shopping redirect is never extractable",
          not looks_like_product(_redirect()))
    check("a storefront home page is not a listing",
          not looks_like_product("https://www.naturemade.com/"))
    check("a certification directory is not a competitor",
          not looks_like_product("https://www.quality-supplements.org/usp_verified_products"))
    check("a real product URL with tracking params survives",
          looks_like_product("https://www.thorne.com/products/dp/mag?srsltid=abc"))

    print("\ngrafting shopping metadata onto real URLs")
    grafted = [
        Candidate(url="https://www.thorne.example/products/mag", channel="web",
                  title="Thorne Magnesium Bisglycinate 200 Servings"),
        Candidate(url="", channel="shopping", price="$42.00", rating=4.7,
                  review_count=2841, merchant="Thorne",
                  title="Thorne Magnesium Bisglycinate, 200 servings"),
        Candidate(url="", channel="shopping", price="$9.99", rating=3.1,
                  review_count=12, merchant="Walmart",
                  title="Completely Different Vitamin C Serum"),
    ]
    extractable, leftover = merge_mod.graft_shopping_metadata(grafted)
    web0 = extractable[0]
    check("a web result gains the price shopping knew", web0.price == "$42.00", web0.price)
    check("...and the rating", web0.rating == 4.7 and web0.review_count == 2841)
    check("...and the merchant name", web0.merchant == "Thorne", web0.merchant)
    check("an unmatched shopping result is kept as metadata-only",
          len(leftover) == 1 and leftover[0].merchant == "Walmart", len(leftover))
    check("a non-matching product does NOT donate its price",
          web0.price != "$9.99")

    priced = [Candidate(url="https://a.example/1", channel="web", title="X",
                        price="$1.00", rating=5.0)]
    kept_web, _ = merge_mod.graft_shopping_metadata(
        priced + [Candidate(url="", channel="shopping", title="X", price="$99.00")])
    check("a web result that already has a price keeps it",
          kept_web[0].price == "$1.00", kept_web[0].price)

    print("\nmerge and dedupe")
    raw = [
        Candidate(url="https://www.amazon.com/dp/1", channel="shopping", position=1,
                  title="Nature's Bounty Magnesium Glycinate 400 mg, 120 Capsules"),
        Candidate(url="https://nb.example/products/mag", channel="web", position=1,
                  title="Magnesium Glycinate 400mg | Natures Bounty"),
        Candidate(url="https://www.amazon.com/dp/2", channel="shopping", position=2,
                  title="Nature's Bounty Magnesium Glycinate 200 mg, 60 Capsules"),
        Candidate(url="https://www.amazon.com/dp/1?ref=x", channel="shopping", position=3,
                  title="Nature's Bounty Magnesium Glycinate 400 mg, 120 Capsules"),
        Candidate(url="https://www.amazon.com/dp/3", channel="shopping", position=4,
                  title="Doctors Best High Absorption Magnesium"),
        Candidate(url="https://www.amazon.com/dp/4", channel="shopping", position=5,
                  title="Thorne Magnesium Bisglycinate Powder"),
        Candidate(url="https://www.amazon.com/dp/5", channel="shopping", position=6,
                  title="Pure Encapsulations Magnesium Glycinate"),
        Candidate(url="https://www.amazon.com/dp/6", channel="shopping", position=7,
                  title="NOW Foods Magnesium Glycinate Tablets"),
        Candidate(url="https://www.walmart.com/ip/9", channel="shopping", position=8,
                  title="Spring Valley Magnesium Glycinate"),
    ]
    chosen, rep = merge_candidates(raw, limit=10, max_per_domain=4)
    titles = [c.title for c in chosen]

    check("the SAME product on a different storefront collapses",
          not any("| Natures Bounty" in t for t in titles), titles)
    check("a same-brand size variant collapses", rep["duplicates"] >= 1, rep)
    check("the same URL with tracking params collapses",
          len({c.url.split("?")[0] for c in chosen}) == len(chosen))
    check("no storefront exceeds the cap",
          sum(1 for c in chosen if c.domain == "amazon.com") <= 4,
          [c.domain for c in chosen])
    check("capping let a second storefront into the cohort",
          any(c.domain == "walmart.com" for c in chosen), [c.domain for c in chosen])
    check("what was dropped is reported, not hidden",
          rep["same_product"] >= 1 and rep["domain_capped"] >= 1, rep)

    check("different products from one brand are NOT merged",
          len({c.url for c in chosen}) == len(chosen))

    print("\nown-brand exclusion")
    own = [Candidate(url="https://a.example/1", title="Nature Made Magnesium 400mg"),
           Candidate(url="https://a.example/2", title="Pure Encapsulations Magnesium"),
           Candidate(url="https://a.example/3", title="Doctors Best Pure Magnesium")]
    kept = exclude_own_brand(own, "Nature Made")
    check("the user's own listing is excluded", len(kept) == 2, [c.title for c in kept])
    check("a one-word brand does not delete every title containing that word",
          len(exclude_own_brand(own, "Pure")) == 2,
          [c.title for c in exclude_own_brand(own, "Pure")])
    check("no brand name means nothing is excluded", len(exclude_own_brand(own, "")) == 3)

    # Observed live: naturemade.com ranked for the category term with a title
    # that never says "Nature Made", so the title-only check let the user's own
    # store into their own competitive set.
    bydomain = [Candidate(url="https://www.naturemade.com/products/magnesium-glycinate",
                          title="High Absorption Magnesium Glycinate Capsules 200 mg"),
                Candidate(url="https://www.thorne.com/products/mag",
                          title="Magnesium Bisglycinate")]
    kept_d = exclude_own_brand(bydomain, "Nature Made")
    check("the user's own STORE is excluded even when the title omits the brand",
          len(kept_d) == 1 and "thorne" in kept_d[0].url, [c.url for c in kept_d])
    check("a short brand name does not match domains by accident",
          len(exclude_own_brand(bydomain, "Pure")) == 2)

    print("\nrank is the join key")
    for i, c in enumerate(chosen, start=1):
        c.position = i
    check("ranks are dense and unique",
          sorted(c.position for c in chosen) == list(range(1, len(chosen) + 1)))

    print("\nerror taxonomy")
    for code, want, retryable in [(401, "invalid API key", False), (402, "out of credits", False),
                                  (429, "rate limited", True), (500, "HTTP 500", True)]:
        use(lambda req, c=code: httpx.Response(c, json={}))
        try:
            await SerperDiscovery().discover(plan)
            check(f"HTTP {code} raises", False)
        except ProviderError as e:
            check(f"HTTP {code} -> {want}, retryable={retryable}",
                  want.split()[0] in e.detail and e.retryable == retryable, e.detail)

    use(handler)
    try:
        await SerperDiscovery(api_key="").discover(plan)
        check("a missing key raises", False)
    except ProviderError as e:
        check("a missing key fails fast and is not retryable",
              "not set" in e.detail and e.retryable is False, e.detail)

    print("\npartial failure")
    state = {"n": 0}
    def flaky(request):
        state["n"] += 1
        if request.url.path.endswith("/search"):
            return httpx.Response(500, json={})
        return httpx.Response(200, json=SHOPPING)
    use(flaky)
    partial = await SerperDiscovery().discover(plan)
    check("one failing channel does not lose the other", len(partial) >= 2, len(partial))
    check("the surviving results are the shopping ones",
          all(c.channel == "shopping" for c in partial))

    use(lambda req: httpx.Response(200, json={"shopping": [], "organic": []}))
    try:
        await SerperDiscovery().discover(plan)
        check("an empty result set raises rather than returning nothing", False)
    except ProviderError as e:
        check("an empty result set raises rather than returning nothing", True, e.detail)

    print("\ncost contract")
    CALLS.clear()
    use(handler)
    await SerperDiscovery().discover(plan)
    check("exactly one request per planned query — no hidden fan-out",
          len(CALLS) == len(plan.all_queries), (len(CALLS), len(plan.all_queries)))

    phttp.make_client = real

    print()
    print(f"{sum(results)}/{len(results)} checks passed")
    print("DISCOVERY PASS" if all(results) else "DISCOVERY FAIL")
    return 0 if all(results) else 1


sys.exit(asyncio.run(main()))
