"""
Reading a page must never invent what the page does not say.

The dangerous failure here is silent. A JavaScript-heavy page returning
navigation chrome, or a consent interstitial returning legal boilerplate,
produces plausible text that flows into the scorer and is graded as listing
copy — which drags the competitor mean down and *inflates* the user's
percentile. A flattering wrong number is the kind nobody reports as a bug, so
these tests pin the guard that catches it.
"""
import asyncio, os, pathlib, sys, tempfile, types

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_tmp = tempfile.TemporaryDirectory()
os.environ["AUTH_DB_PATH"] = str(pathlib.Path(_tmp.name) / "auth.db")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ["FIRECRAWL_API_KEY"] = "fc-test"

import httpx

import config
import providers.http as phttp
from providers.extract import model as gapfill
from providers.extract.base import DISCOVERY_ONLY, FAILED, STRUCTURED, ExtractedPage
from providers.extract.firecrawl import FirecrawlExtractor, is_usable
from providers.extract.structured import bullets_from_markdown, parse_product

results = []
def check(label, passed, detail=""):
    results.append(passed)
    print(f"  {'ok  ' if passed else 'FAIL'} {label}{'  ' + str(detail) if detail else ''}")


LD = """<html><head><script type="application/ld+json">
{"@context":"https://schema.org","@type":"Product",
 "name":"Thorne Magnesium Bisglycinate","brand":{"@type":"Brand","name":"Thorne"},
 "description":"Highly absorbable magnesium powder that supports restful sleep and muscle relaxation after training.",
 "offers":{"@type":"Offer","price":"42.00","priceCurrency":"USD"},
 "aggregateRating":{"@type":"AggregateRating","ratingValue":"4.7","reviewCount":"2841"}}
</script></head><body>x</body></html>"""

GOOD_MD = ("Thorne Magnesium Bisglycinate powder supports restful sleep and muscle recovery.\n"
           "- Highly absorbable magnesium bisglycinate powder\n"
           "- 200 servings per container, NSF Certified for Sport\n"
           "- Home\n"
           "* Supports restful sleep and overnight muscle relaxation\n"
           ) + ("Magnesium bisglycinate is gentle on the stomach. " * 8)


def scrape_response(markdown=GOOD_MD, html=LD, title="Thorne Magnesium Bisglycinate"):
    return {"success": True, "data": {"markdown": markdown, "rawHtml": html,
                                      "metadata": {"title": title, "statusCode": 200}}}


def use(h):
    phttp.make_client = lambda timeout=30.0: httpx.AsyncClient(
        timeout=timeout, transport=httpx.MockTransport(h))


async def main():
    real = phttp.make_client
    phttp.DEFAULT_BASE_DELAY = phttp.DEFAULT_MAX_DELAY = 0.0

    print("\nstructured data comes first")

    sp = parse_product(LD)
    check("JSON-LD gives the product name", sp["title"] == "Thorne Magnesium Bisglycinate")
    check("brand is unwrapped from the Brand node", sp["brand_name"] == "Thorne")
    check("price is rendered with its currency", sp["price"] == "$42.00", sp["price"])
    check("rating and review count map through",
          sp["rating"] == 4.7 and sp["review_count"] == 2841)
    check("a page with no JSON-LD yields nothing, not a guess",
          parse_product("<html><body>hi</body></html>") == {})
    check("malformed JSON-LD does not raise",
          parse_product('<script type="application/ld+json">{broken</script>') == {})
    check("a page with no markup at all does not raise", parse_product("") == {})

    b = bullets_from_markdown(GOOD_MD)
    check("bullets are taken verbatim from the page", len(b) == 3, b)
    check("navigation entries are not selling points", "Home" not in b, b)

    print("\nreading a page")
    use(lambda req: httpx.Response(200, json=scrape_response()))
    async with phttp.make_client(5) as c:
        page = await FirecrawlExtractor().extract_one(c, "https://thorne.example/p/1",
                                                      "Thorne Magnesium Bisglycinate")
    check("the page is marked extracted", page.status == "extracted", page.status)
    check("structured data was preferred over the model", page.method == STRUCTURED, page.method)
    check("title, brand, price and rating all populated",
          page.title and page.brand_name == "Thorne" and page.price == "$42.00" and page.rating == 4.7)
    check("bullets came from the rendered page", len(page.bullet_points) == 3)
    check("the page counts as having real copy", page.has_copy is True)
    check("nothing is still missing", page.missing_fields() == [], page.missing_fields())

    print("\nthe thin-content guard")

    check("a near-empty body is rejected", is_usable("short")[0] is False)
    banner = "We use cookies and similar technologies to improve your experience. " * 12
    ok, why = is_usable(banner, "Thorne Magnesium Bisglycinate")
    check("a LONG cookie banner is rejected on title mismatch", ok is False, why)
    check("...and the reason is recorded", "does not match" in why, why)
    check("genuine product copy passes",
          is_usable(GOOD_MD, "Thorne Magnesium Bisglycinate")[0] is True)

    use(lambda req: httpx.Response(200, json=scrape_response(markdown="tiny", html="")))
    async with phttp.make_client(5) as c:
        thin = await FirecrawlExtractor().extract_one(c, "https://x.example/1", "Thorne Magnesium")
    check("a thin page is marked failed, not extracted", thin.status == FAILED, thin.status)
    check("a thin page invents no copy",
          not thin.bullet_points and not thin.description and not thin.brand_name)
    check("a thin page says why", bool(thin.note), thin.note)

    print("\npage furniture is not selling copy")
    # Every one of these was captured from a live product page and scored on the
    # rubric as though the seller had written it.
    chrome = """- Try disabling your extensions.
- The video showcases the product in use.The video guides you through setup.
- 90 Count (Pack of 1)
- Size: Large
- [Health & Household](https://www.amazon.com/health)
- \u203a
- [**Amazon Music** Stream millions\\
- Add to Cart
- HIGH ABSORPTION: chelated magnesium glycinate for superior bioavailability
- Third-party tested for purity in a GMP certified facility
"""
    kept = bullets_from_markdown(chrome)
    check("a browser error message is not a selling point",
          not any("disabling" in k for k in kept), kept)
    check("a video widget caption is not a selling point",
          not any("video showcases" in k for k in kept))
    check("a variant picker is not a selling point",
          not any(k.startswith(("90 Count", "Size:")) for k in kept), kept)
    check("a breadcrumb link is not a selling point",
          not any("Health & Household" in k for k in kept))
    check("a truncated footer link is not a selling point",
          not any("Amazon Music" in k for k in kept))
    check("real selling copy survives all of that", len(kept) == 2, kept)

    # Both observed live. The subscription options were scored on the rubric and
    # then reported back as that brand's competitive strategy; the guide prose
    # was a retailer's own advice section, scored as if it described its product.
    subs = bullets_from_markdown("""- Delivery every 30 Days
- Delivery every 45 Days
- Subscribe & Save 15%
- One-time purchase
- Ships every 2 months
- HIGH ABSORPTION: chelated magnesium glycinate for superior bioavailability
""")
    check("a subscription frequency is not a selling point",
          not any("Delivery every" in k or "Ships every" in k for k in subs), subs)
    check("a purchase-mode option is not a selling point",
          not any("One-time" in k or "Subscribe" in k for k in subs), subs)
    check("the real bullet still survives", len(subs) == 1, subs)

    guide = bullets_from_markdown("""- Purity and Quality Standards: Look for brands that use pure magnesium glycinate without fillers.
- Absorption: Check for chelated forms and avoid blends that dilute the magnesium content.
- We recommend starting with a lower dose and increasing gradually over time.
- THIRD-PARTY TESTED: every batch verified for purity and potency by an outside lab
""")
    check("buying-guide prose is not this seller's copy",
          not any(k.startswith(("Purity", "Absorption", "We recommend")) for k in guide), guide)
    check("the seller's own claim still survives", len(guide) == 1, guide)

    check("one surviving bullet is not enough to score a listing",
          ExtractedPage(url="u", bullet_points=["a real sounding bullet point here"]).has_copy is False)
    check("two bullets are", ExtractedPage(
        url="u", bullet_points=["bullet one that is long", "bullet two that is long"]).has_copy is True)
    check("a substantial description alone is enough",
          ExtractedPage(url="u", description="d" * 150).has_copy is True)
    check("a short description alone is not",
          ExtractedPage(url="u", description="short").has_copy is False)

    print("\nfailure isolation")

    for code, label in [(402, "out of credits"), (429, "rate limited"), (403, "invalid API key")]:
        use(lambda req, c=code: httpx.Response(c, json={}))
        async with phttp.make_client(5) as c:
            p = await FirecrawlExtractor().extract_one(c, "https://x.example/1")
        check(f"HTTP {code} degrades one page, never raises",
              p.status == DISCOVERY_ONLY and label.split()[0] in p.note, (p.status, p.note))

    def explode(request):
        raise httpx.ConnectError("dns", request=request)
    use(explode)
    async with phttp.make_client(5) as c:
        p = await FirecrawlExtractor().extract_one(c, "https://x.example/1")
    check("a transport failure degrades one page", p.status == DISCOVERY_ONLY, p.note)

    print("\nconcurrency and deadline")

    live = {"now": 0, "max": 0}
    async def slow_handler(request):
        live["now"] += 1
        live["max"] = max(live["max"], live["now"])
        await asyncio.sleep(0.05)
        live["now"] -= 1
        return httpx.Response(200, json=scrape_response())
    use(slow_handler)

    config.FIRECRAWL_MAX_CONCURRENCY = 3
    import providers.extract.firecrawl as fc
    fc.FIRECRAWL_MAX_CONCURRENCY = 3
    targets = [(f"https://thorne.example/p/{i}", "Thorne Magnesium Bisglycinate") for i in range(9)]
    pages = await FirecrawlExtractor().extract_many(targets)
    check("every target gets a result", len(pages) == 9, len(pages))
    check("results stay in the order requested",
          [p.url for p in pages] == [u for u, _ in targets])
    check("concurrency is bounded, not unbounded fan-out", live["max"] <= 3, live["max"])

    async def hang(request):
        await asyncio.sleep(5)
        return httpx.Response(200, json=scrape_response())
    use(hang)
    fc.EXTRACT_DEADLINE_SECONDS = 0.2
    slow_pages = await FirecrawlExtractor().extract_many(
        [("https://thorne.example/slow", "Thorne Magnesium")])
    check("the whole-stage deadline fires instead of hanging",
          slow_pages[0].status == DISCOVERY_ONLY, slow_pages[0].status)
    check("a timed-out page says so", "deadline" in slow_pages[0].note, slow_pages[0].note)
    fc.EXTRACT_DEADLINE_SECONDS = 60.0

    print("\ntotal extractor outage")
    use(lambda req: httpx.Response(402, json={}))
    out = await FirecrawlExtractor().extract_many(
        [(f"https://x.example/{i}", "") for i in range(3)])
    check("every page degrades, none raises",
          all(p.status == DISCOVERY_ONLY for p in out), [p.status for p in out])

    missing = await FirecrawlExtractor(api_key="").extract_many([("https://x.example/1", "")])
    check("no API key degrades rather than raising",
          missing[0].status == DISCOVERY_ONLY and "not set" in missing[0].note, missing[0].note)

    print("\nthe model fills only gaps")

    calls = {"n": 0, "prompt": ""}
    class _M:
        def __init__(s, p): s.parsed, s.refusal = p, None
    class _C:
        def __init__(s, p): s.message = _M(p)
    class _U:
        prompt_tokens, completion_tokens = 10, 5
    class _Comp:
        def __init__(s, p): s.choices, s.usage = [_C(p)], _U()

    from models.llm_responses import ExtractedPageOut, ExtractedPagesOut
    import agents.llm_client as lc

    planned = ExtractedPagesOut(items=[
        ExtractedPageOut(item_id=0, title="Filled Title", brand_name="FilledBrand",
                         bullet_points=["from the page one", "from the page two"],
                         description="A description read off the page itself, long enough to count."),
        ExtractedPageOut(item_id=99, title="INVENTED", brand_name="INVENTED",
                         bullet_points=["invented"], description="invented"),
    ])

    async def parse(**kw):
        calls["n"] += 1
        calls["prompt"] = kw["messages"][0]["content"]
        return _Comp(planned)
    client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(parse=parse)))
    lc._client = client
    lc.get_openai_client = lambda: client

    complete = ExtractedPage(url="https://a.example/1", title="T", brand_name="B",
                             bullet_points=["x" * 20], description="d" * 200,
                             body="body", status="extracted", method=STRUCTURED)
    gappy = ExtractedPage(url="https://b.example/2", status="extracted",
                          body="raw page text about the product " * 20)

    await gapfill.fill_gaps([complete, gappy])
    check("one call covers the whole batch", calls["n"] == 1, calls["n"])
    check("a page with complete structured data is NOT sent to the model",
          "https://a.example/1" not in calls["prompt"])
    check("a page with gaps is sent", "https://b.example/2" in calls["prompt"])
    check("the prompt names which fields are still needed", "Still needed" in calls["prompt"])
    check("gaps are filled", gappy.title == "Filled Title" and gappy.brand_name == "FilledBrand")
    check("the method records that the model was involved", "model" in gappy.method, gappy.method)
    check("the complete page was left untouched",
          complete.title == "T" and complete.method == STRUCTURED)
    check("an invented page id cannot become a competitor",
          complete.title != "INVENTED" and gappy.title != "INVENTED")

    calls["n"] = 0
    await gapfill.fill_gaps([complete])
    check("a batch needing nothing makes NO model call at all", calls["n"] == 0, calls["n"])

    calls["n"] = 0
    await gapfill.fill_gaps([ExtractedPage(url="https://c.example/3", status=FAILED, body="")])
    check("a failed page is never sent to the model", calls["n"] == 0, calls["n"])

    phttp.make_client = real

    print("\nplatform-aware routing")
    # Verified against live pages: an Amazon product page publishes no
    # schema.org markup and ~150k chars of navigation, so generic extraction
    # returns category links as bullet points. Where a platform has a real
    # product API, use it.
    from providers.extract.amazon import AmazonExtractor, asin_from_url
    from providers.extract.composite import PlatformAwareExtractor

    check("an ASIN is recovered from a product URL",
          asin_from_url("https://www.amazon.com/Pure-Encaps/dp/B0058HWV9S") == "B0058HWV9S")
    check("a /gp/product URL works too",
          asin_from_url("https://www.amazon.co.uk/gp/product/B07TNJRN9N?th=1") == "B07TNJRN9N")
    check("a non-Amazon URL yields no ASIN",
          asin_from_url("https://www.thorne.com/products/mag") == "")
    check("an Amazon search page is not a product URL",
          asin_from_url("https://www.amazon.com/s?k=magnesium") == "")

    seen = {"amazon": [], "generic": []}

    class FakeAmazon:
        name = "rainforest_product"
        available = True
        def handles(self, url): return bool(asin_from_url(url))
        async def extract_many(self, targets):
            seen["amazon"].extend(u for u, _ in targets)
            return [ExtractedPage(url=u, title="A", bullet_points=["clean bullet one"],
                                  description="d" * 200, brand_name="B",
                                  status="extracted", method=STRUCTURED)
                    for u, _ in targets]

    class FakeGeneric:
        name = "firecrawl"
        async def extract_many(self, targets):
            seen["generic"].extend(u for u, _ in targets)
            return [ExtractedPage(url=u, title="G", status="extracted") for u, _ in targets]

    router = PlatformAwareExtractor(generic=FakeGeneric(), amazon=FakeAmazon())
    order = [("https://www.amazon.com/x/dp/B00000001A", "t1"),
             ("https://www.thorne.com/products/mag", "t2"),
             ("https://www.amazon.com/y/dp/B00000002B", "t3"),
             ("https://shop.example/p/1", "t4")]
    out = await router.extract_many(order)

    check("Amazon URLs go to the product API",
          seen["amazon"] == [order[0][0], order[2][0]], seen["amazon"])
    check("everything else goes to the generic reader",
          seen["generic"] == [order[1][0], order[3][0]], seen["generic"])
    check("no URL is read twice", len(seen["amazon"]) + len(seen["generic"]) == 4)
    check("results come back in the order requested",
          [p.url for p in out] == [u for u, _ in order])
    check("each result is the one its own reader produced",
          [p.title for p in out] == ["A", "G", "A", "G"], [p.title for p in out])
    check("the extractor names both readers",
          "firecrawl" in router.name and "rainforest" in router.name, router.name)

    nokey = PlatformAwareExtractor(generic=FakeGeneric(),
                                   amazon=AmazonExtractor(api_key=""))
    seen["generic"].clear()
    await nokey.extract_many([("https://www.amazon.com/x/dp/B00000001A", "t")])
    check("without an Amazon key, Amazon falls through to the generic reader",
          seen["generic"] == ["https://www.amazon.com/x/dp/B00000001A"], seen["generic"])
    check("...and the name does not claim a reader it cannot use",
          "rainforest" not in nokey.name, nokey.name)

    print("\na failing specialised reader falls back")
    # Observed live: Rainforest credits ran out and every Amazon competitor came
    # back empty while the generic reader sat idle. Routing to a better reader
    # must never be worse than not routing at all.
    class DeadAmazon:
        name = "rainforest_product"
        available = True
        def handles(self, url): return bool(asin_from_url(url))
        async def extract_many(self, targets):
            return [ExtractedPage(url=u, status=DISCOVERY_ONLY, note="out of credits")
                    for u, _ in targets]

    seen["generic"].clear()
    degraded = PlatformAwareExtractor(generic=FakeGeneric(), amazon=DeadAmazon())
    out2 = await degraded.extract_many(
        [("https://www.amazon.com/x/dp/B00000001A", "t"),
         ("https://shop.example/p/1", "t2")])
    check("a dead platform API falls back to the generic reader",
          "https://www.amazon.com/x/dp/B00000001A" in seen["generic"], seen["generic"])
    check("the page is read rather than left empty",
          all(p.status == "extracted" for p in out2), [p.status for p in out2])
    check("the generic page is not fetched twice",
          seen["generic"].count("https://shop.example/p/1") == 1, seen["generic"])

    class DeadBoth:
        name = "firecrawl"
        async def extract_many(self, targets):
            return [ExtractedPage(url=u, status=DISCOVERY_ONLY, note="also down")
                    for u, _ in targets]
    both = PlatformAwareExtractor(generic=DeadBoth(), amazon=DeadAmazon())
    out3 = await both.extract_many([("https://www.amazon.com/x/dp/B00000001A", "t")])
    check("when both readers fail, the competitor degrades rather than vanishing",
          len(out3) == 1 and out3[0].status == DISCOVERY_ONLY, out3[0].status)
    check("...and still explains itself", bool(out3[0].note), out3[0].note)

    print("\nan article never consumes a competitor slot")
    # Two of ten slots in an observed run went to editorial round-ups. They were
    # correctly left unscored, but the slots were already spent by then — the
    # title is enough to judge, and it is known before anything is fetched.
    from providers.discovery.base import Candidate
    from providers.discovery.merge import merge_candidates
    pool = [
        Candidate(url="https://www.everydayhealth.com/supplements/best-magnesium",
                  title="Best RD-Reviewed Magnesium Supplements 2026"),
        Candidate(url="https://www.target.com/p/best-mag",
                  title="Best Magnesium Glycinate for Anxiety"),
        Candidate(url="https://www.amazon.com/a/dp/B00000001A",
                  title="Pure Encapsulations Magnesium Glycinate 180 Capsules"),
        Candidate(url="https://www.gnc.com/p/1",
                  title="Liposomal Magnesium Glycinate - 240 Capsules"),
    ]
    picked, rep = merge_candidates(pool, limit=10)
    check("round-ups are dropped before a slot is spent", rep["articles"] == 2, rep["articles"])
    check("only real products remain", len(picked) == 2, [c.title for c in picked])
    check("how many were dropped is reported", "articles" in rep)

    print("\narticle detection is narrow on purpose")
    from providers.extract.firecrawl import looks_like_article
    for title, want in [
        ("Magnesium Glycinate 400mg, Third-Party Tested, 180 Capsules", False),
        ("Magnesium Glycinate | Clinically Tested Bisglycinate", False),
        ("Doctor's Best High Absorption Magnesium, Reviewed Formula", False),
        ("Best RD-Reviewed Magnesium Supplements 2026", True),
        ("The 12 Best Magnesium Supplements We Tested", True),
        ("Top 10 Magnesium Glycinate Brands", True),
        ("Magnesium Glycinate vs Citrate: which to choose", True),
    ]:
        check(f"{'article' if want else 'product '}: {title[:46]}",
              looks_like_article(title, False) is want)
    check("structured Product markup outweighs a promotional title",
          looks_like_article("Best Magnesium Glycinate 400mg", True) is False)

    print()
    print(f"{sum(results)}/{len(results)} checks passed")
    print("EXTRACTION PASS" if all(results) else "EXTRACTION FAIL")
    return 0 if all(results) else 1


sys.exit(asyncio.run(main()))
