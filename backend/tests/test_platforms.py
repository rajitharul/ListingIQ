"""
A domain must never be mistaken for a marketplace it isn't.

The old provider did `_DOMAINS.get(platform.lower(), "amazon.com")`, so any
platform it did not recognise was silently searched on Amazon. A Shopify seller
got ten Amazon competitors presented as their own platform's top sellers, with
nothing in the output to reveal the substitution. These tests pin the replacement:
an unrecognised domain resolves to `dtc`, and no code path can produce a
marketplace by default.

Also covers `normalize.py`, which now owns product identity so that `providers/`
no longer has to import from `agents/`.
"""
import os, pathlib, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_tmp = tempfile.TemporaryDirectory()
os.environ["AUTH_DB_PATH"] = str(pathlib.Path(_tmp.name) / "auth.db")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

import normalize as nz
from providers import platforms as pf

results = []
def check(label, passed, detail=""):
    results.append(passed)
    print(f"  {'ok  ' if passed else 'FAIL'} {label}{'  ' + str(detail) if detail else ''}")


# ── detect(): the bug this module exists to prevent ──────────────
print("\nplatform detection")

check("amazon.com recognised", pf.detect("https://www.amazon.com/dp/B001") == "amazon")
check("regional amazon folds to one slug",
      pf.detect("https://www.amazon.co.uk/dp/B1") == "amazon")
check("longest domain wins (amazon.com.au not amazon.com)",
      pf.detect("https://www.amazon.com.au/dp/B1") == "amazon")
check("walmart recognised", pf.detect("https://www.walmart.com/ip/123") == "walmart")
check("ebay recognised", pf.detect("https://www.ebay.com/itm/5") == "ebay")
check("myshopify subdomain recognised",
      pf.detect("https://mystore.myshopify.com/products/x") == "shopify")

# The headline assertion.
check("UNKNOWN domain resolves to dtc, NOT amazon",
      pf.detect("https://weird-store.example/p/1") == "dtc",
      pf.detect("https://weird-store.example/p/1"))
check("no url at all is 'generic', not a marketplace", pf.detect("") == "generic")
check("a non-url string cannot yield a marketplace",
      pf.detect("not a url") not in ("amazon", "walmart", "ebay"))
check("www. prefix is stripped before matching",
      pf.detect("http://amazon.com/dp/X") == "amazon")
check("a lookalike domain is not amazon",
      pf.detect("https://amazon.com.evil.example/dp/X") == "dtc",
      pf.detect("https://amazon.com.evil.example/dp/X"))

# ── domain_for(): no invented site: scopes ───────────────────────
print("\nsearch scoping")

check("marketplace yields a search domain", pf.domain_for("amazon") == "amazon.com")
check("regional alias keeps its own domain", pf.domain_for("amazon_uk") == "amazon.co.uk")
check("dtc yields NO domain to scope to", pf.domain_for("dtc") == "")
check("shopify yields no domain (not one site)", pf.domain_for("shopify") == "")
check("unknown platform yields no domain", pf.domain_for("wat") == "")
check("empty platform yields no domain", pf.domain_for("") == "")

# ── profiles ─────────────────────────────────────────────────────
print("\nformat profiles")

check("amazon expects bullets", pf.profile("amazon").bullets_expected is True)
check("amazon description is not text (A+ is images)",
      pf.profile("amazon").description_is_text is False)
check("ebay has a short title cap", pf.profile("ebay").title_char_target == (60, 80))
check("ebay does not expect bullets", pf.profile("ebay").bullets_expected is False)
check("dtc titles are short, not 200 chars",
      pf.profile("dtc").title_char_target[1] <= 100, pf.profile("dtc").title_char_target)
check("a junk platform still returns a profile, no KeyError",
      pf.profile("nonsense").slug == "generic")
check("alias resolves to canonical profile", pf.profile("amazon_de").slug == "amazon")
check("every registered slug has a profile",
      all(pf.profile(s).slug for s in pf.all_slugs()))
check("no profile is marketplace-searchable without a domain",
      all(bool(pf.profile(s).domains) for s in pf.all_slugs() if pf.profile(s).searchable))

# ── normalize.py ─────────────────────────────────────────────────
print("\nproduct identity")

check("brand_key unchanged: apostrophes do not shift the window",
      nz.brand_key("Nature's Bounty, High Absorption") == nz.brand_key("Natures Bounty High absorption"),
      nz.brand_key("Nature's Bounty, High Absorption"))
check("brand_key takes three words", nz.brand_key("Nature Made Magnesium 400mg") == "nature made magnesium")

MKT = "Nature's Bounty Magnesium Glycinate 400 mg, 120 Capsules"
DTC_T = "Magnesium Glycinate 400mg | Natures Bounty"
check("brand_key does NOT collapse the same product across platforms",
      nz.brand_key(MKT) != nz.brand_key(DTC_T))
check("token similarity DOES collapse it",
      nz.title_similarity(MKT, DTC_T) >= 0.6, round(nz.title_similarity(MKT, DTC_T), 3))
check("unrelated products stay apart",
      nz.title_similarity("Optimum Nutrition Creatine Monohydrate", "Vitamin C Serum") < 0.2)
check("units are joined: '400 mg' == '400mg'",
      "400mg" in nz.significant_tokens("Magnesium 400 mg"))
check("filler words are dropped", "premium" not in nz.significant_tokens("Premium Magnesium"))
check("identity is order-independent",
      nz.product_identity("Magnesium Glycinate Bounty") == nz.product_identity("Bounty Glycinate Magnesium"))
check("accents fold", nz.significant_tokens("Nutrición") == nz.significant_tokens("Nutricion"))
check("empty titles are never similar", nz.title_similarity("", "anything") == 0.0)

check("registrable_domain strips www", nz.registrable_domain("https://www.walmart.com/ip/1") == "walmart.com")
check("registrable_domain keeps subdomains",
      nz.registrable_domain("https://shop.brand.co.uk/x") == "shop.brand.co.uk")
check("registrable_domain on junk is empty", nz.registrable_domain("") == "")

# ── dedupe still behaves as the old module did ───────────────────
print("\ndedupe (moved, not changed)")

items = [{"title": "BrandA Nutrition Magnesium 200mg"},
         {"title": "BrandA Nutrition Magnesium 400mg"},
         {"title": "BrandB Labs Magnesium"}, {"title": ""}]
out = nz.dedupe_by_brand(items)
check("same-brand variants collapse", len(out) == 2, [i["title"] for i in out])
check("best-ranked variant is kept", out[0]["title"] == "BrandA Nutrition Magnesium 200mg")

# Known limit of the three-word window, pinned so it is a documented property
# rather than a surprise: variants that differ inside the first three words do
# not collapse. Cross-platform matching uses title_similarity for this reason.
close = [{"title": "BrandA Magnesium 200mg"}, {"title": "BrandA Magnesium 400mg"}]
check("variants differing within the 3-word window do NOT collapse (known limit)",
      len(nz.dedupe_by_brand(close)) == 2)
check("...but token similarity catches them",
      nz.title_similarity(close[0]["title"], close[1]["title"]) >= 0.4,
      round(nz.title_similarity(close[0]["title"], close[1]["title"]), 3))
check("untitled items are skipped", all(i["title"] for i in out))
check("limit is respected", len(nz.dedupe_by_brand(items, limit=1)) == 1)

print()
print(f"{sum(results)}/{len(results)} checks passed")
print("PLATFORMS PASS" if all(results) else "PLATFORMS FAIL")
sys.exit(0 if all(results) else 1)
