"""
Reading the user's own listing from a URL — and never overwriting what they typed.

Two properties matter here. The first is that a field the user filled in wins
over whatever the live page says: someone who pasted a corrected title must not
have the correction silently reverted. The second is that the platform becomes
an observed fact rather than a dropdown, because the platform now decides which
cohort they are benchmarked against.

Also pins the `_AGENT_CATALOG` / graph assertion. CLAUDE.md claimed a test
enforced that for some time; none did, so a node added to the graph but not the
catalog would run, cost money, and never appear in the trace.
"""
import asyncio, os, pathlib, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_tmp = tempfile.TemporaryDirectory()
os.environ["AUTH_DB_PATH"] = str(pathlib.Path(_tmp.name) / "auth.db")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ["FIRECRAWL_API_KEY"] = "fc-test"

from models.schemas import ListingInput
from providers.extract.base import DISCOVERY_ONLY, FAILED, STRUCTURED, ExtractedPage
from providers.extract.listing import extract_listing

results = []
def check(label, passed, detail=""):
    results.append(passed)
    print(f"  {'ok  ' if passed else 'FAIL'} {label}{'  ' + str(detail) if detail else ''}")


class StubExtractor:
    name = "stub"
    def __init__(self, page): self.page = page
    async def extract_many(self, targets):
        return [self.page.__class__(**{**vars(self.page), "url": targets[0][0]})]


def good_page():
    return ExtractedPage(
        url="", title="Thorne Magnesium Bisglycinate",
        description="Highly absorbable magnesium supporting restful sleep and recovery." * 3,
        bullet_points=["Highly absorbable", "200 servings"],
        brand_name="Thorne", body="body text", status="extracted", method=STRUCTURED)


async def main():
    print("\nreading a page into a listing")
    listing, src = await extract_listing(
        "https://www.thorne.example/products/mag", extractor=StubExtractor(good_page()))

    check("the title is taken from the page", listing.product_title == "Thorne Magnesium Bisglycinate")
    check("bullets are taken from the page", len(listing.bullet_points) == 2)
    check("the brand is taken from the page", listing.brand_name == "Thorne")
    check("the URL is remembered", listing.listing_url.endswith("/products/mag"))
    check("status is recorded", src.status == "extracted")
    check("which fields came from the page is recorded",
          set(src.fields_filled) >= {"product_title", "brand_name"}, src.fields_filled)
    check("fetched_at is recorded", bool(src.fetched_at))

    print("\nthe platform is observed, not assumed")
    check("an unknown storefront is a brand site, NOT amazon",
          listing.platform == "dtc", listing.platform)
    check("the detection is reported separately", src.platform_detected == "dtc")

    amz, asrc = await extract_listing(
        "https://www.amazon.com/dp/B001", extractor=StubExtractor(good_page()))
    check("a marketplace URL is detected as that marketplace", amz.platform == "amazon")

    chosen, _ = await extract_listing(
        "https://www.amazon.com/dp/B001",
        existing=ListingInput(product_title="", platform="shopify"),
        extractor=StubExtractor(good_page()))
    check("an explicit platform choice beats detection", chosen.platform == "shopify")

    auto, _ = await extract_listing(
        "https://www.walmart.com/ip/1",
        existing=ListingInput(product_title="", platform="auto"),
        extractor=StubExtractor(good_page()))
    check("'auto' defers to detection", auto.platform == "walmart")

    print("\nwhat the user typed always wins")
    typed = ListingInput(
        product_title="My Corrected Title", brand_name="MyBrand",
        bullet_points=["my own bullet"], platform="auto")
    merged, msrc = await extract_listing(
        "https://www.thorne.example/products/mag", existing=typed,
        extractor=StubExtractor(good_page()))
    check("a typed title is NOT overwritten", merged.product_title == "My Corrected Title")
    check("a typed brand is NOT overwritten", merged.brand_name == "MyBrand")
    check("typed bullets are NOT overwritten", merged.bullet_points == ["my own bullet"])
    check("only the empty field was filled",
          msrc.fields_filled == ["product_description"], msrc.fields_filled)

    everything = ListingInput(product_title="T", product_description="D" * 50,
                              bullet_points=["b"], brand_name="B")
    _, fullsrc = await extract_listing(
        "https://x.example/1", existing=everything, extractor=StubExtractor(good_page()))
    check("a fully-filled form loses nothing and says so",
          fullsrc.fields_filled == [] and "already filled" in fullsrc.note, fullsrc.note)

    print("\nan unreadable page fails safely")
    for status, note in [(FAILED, "only 3 chars of body copy"),
                         (DISCOVERY_ONLY, "out of credits")]:
        page = ExtractedPage(url="", status=status, note=note)
        base = ListingInput(product_title="Kept")
        out, s2 = await extract_listing("https://x.example/1", existing=base,
                                        extractor=StubExtractor(page))
        check(f"a {status} page reports failure", s2.status == "failed", s2.status)
        check(f"a {status} page explains why", note in s2.note, s2.note)
        check(f"a {status} page invents nothing",
              out.product_title == "Kept" and not out.bullet_points and not out.brand_name)

    print("\n'auto' is resolved before the pipeline reads it")
    # /api/extract resolved it, but a listing submitted with the selector left
    # on "auto" carried the literal string into the pipeline, where
    # canonical("auto") is "generic" — so the same-platform cohort matched
    # nothing, the thin-cohort fallback fired on every run, and the report
    # displayed the platform as "auto".
    from agents.input_parser import resolve_platform
    from providers import platforms as pf

    check("a URL decides when the selector says auto",
          resolve_platform(ListingInput(
              product_title="t", platform="auto",
              listing_url="https://www.thorne.com/products/dp/mag")) == "dtc")
    check("a marketplace URL resolves to that marketplace",
          resolve_platform(ListingInput(
              product_title="t", platform="auto",
              listing_url="https://www.amazon.com/x/dp/B00000001A")) == "amazon")
    check("an explicit choice still beats detection",
          resolve_platform(ListingInput(
              product_title="t", platform="shopify",
              listing_url="https://www.amazon.com/x/dp/B00000001A")) == "shopify")
    check("auto with no URL falls back to generic, not a marketplace",
          resolve_platform(ListingInput(product_title="t", platform="auto")) == "generic")
    check("an empty platform is handled",
          resolve_platform(ListingInput(product_title="t", platform="")) == "generic")

    check("'auto' never reaches the cohort split",
          all(resolve_platform(ListingInput(product_title="t", platform=p_, listing_url=u))
              != "auto"
              for p_ in ("auto", "", "amazon")
              for u in ("", "https://www.thorne.com/products/dp/mag")))
    check("a resolved platform has a real label, not 'Other'",
          pf.label_for(resolve_platform(ListingInput(
              product_title="t", platform="auto",
              listing_url="https://www.walmart.com/ip/1"))) == "Walmart")

    print("\nthe trace catalog matches the graph")
    import main
    main._assert_catalog_matches_graph()
    check("catalog and graph agree", True)

    main._AGENT_CATALOG["ghost"] = {"role": "core", "parent": "START"}
    try:
        main._assert_catalog_matches_graph()
        check("an extra catalog entry is caught", False)
    except RuntimeError as e:
        check("an extra catalog entry is caught", "ghost" in str(e))
    finally:
        main._AGENT_CATALOG.pop("ghost")

    dropped = main._AGENT_CATALOG.pop("rewrite_verifier")
    try:
        main._assert_catalog_matches_graph()
        check("a node missing from the catalog is caught", False)
    except RuntimeError as e:
        check("a node missing from the catalog is caught", "rewrite_verifier" in str(e))
    finally:
        main._AGENT_CATALOG["rewrite_verifier"] = dropped

    check("the graph is still 10 nodes", len(main._AGENT_CATALOG) == 10,
          len(main._AGENT_CATALOG))
    check("/api/extract did not become a pipeline node",
          "extract" not in main._AGENT_CATALOG)

    print("\nthe route rejects nonsense before spending anything")
    routes = {r.path for r in main.app.routes}
    check("/api/extract is registered", "/api/extract" in routes)

    print()
    print(f"{sum(results)}/{len(results)} checks passed")
    print("OWN LISTING PASS" if all(results) else "OWN LISTING FAIL")
    return 0 if all(results) else 1


sys.exit(asyncio.run(main()))
