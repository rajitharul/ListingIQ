"""
Query planning is deterministic, and the cache key does not depend on the model.

The subtle failure this guards against: query strings are built from
`ExtractedEntities`, which an LLM regenerates every run. If the cache key
covered the generated strings, almost every run would miss, hit rate would go to
zero, and the caching the unit economics rest on would stop working while still
looking like it worked. The fingerprint therefore covers the stable inputs only.
"""
import os, pathlib, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_tmp = tempfile.TemporaryDirectory()
os.environ["AUTH_DB_PATH"] = str(pathlib.Path(_tmp.name) / "auth.db")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

from models.schemas import CategoryClassification, ExtractedEntities
from providers import query as q

results = []
def check(label, passed, detail=""):
    results.append(passed)
    print(f"  {'ok  ' if passed else 'FAIL'} {label}{'  ' + str(detail) if detail else ''}")


CAT = CategoryClassification(vertical="Supplements", category="Minerals",
                             subcategory="Magnesium Glycinate")
ENT = ExtractedEntities(format_type="capsules", dosage_info="400 mg per serving",
                        certifications=["USP Verified"])

print("\nquery composition")

plan = q.build_query_plan(CAT, ENT, platform="amazon", brand_name="Nature Made")

check("a shopping query is always produced", len(plan.shopping) >= 1, plan.shopping)
check("the subcategory anchors it", "Magnesium Glycinate" in plan.shopping[0])
check("the most specific qualifier is included", "capsules" in plan.shopping[0])
check("AT LEAST ONE open-web query always exists — shopping under-returns DTC",
      len(plan.web) >= 1, plan.web)
check("a platform-scoped query targets the user's own platform",
      any("site:amazon.com" in w for w in plan.web), plan.web)
check("a certification becomes its own query",
      any("USP" in w for w in plan.web), plan.web)

check("the user's BRAND never appears in any query",
      all("nature" not in x.lower() for x in plan.all_queries), plan.all_queries)
check("no query uses negative search syntax",
      all("-" not in x.split(" site:")[0] for x in plan.all_queries), plan.all_queries)
check("queries stay short enough for shopping recall",
      all(len(x.replace("site:", "").split()) <= 8 for x in plan.all_queries), plan.all_queries)
check("queries are unique", len(set(plan.all_queries)) == len(plan.all_queries))

print("\nplatform scoping")

dtc = q.build_query_plan(CAT, ENT, platform="shopify")
check("a platform with no single domain gets NO site: query",
      not any("site:" in w for w in dtc.web), dtc.web)
check("...but still gets open-web queries", len(dtc.web) >= 1)

none = q.build_query_plan(CAT, ENT, platform="")
check("no platform yields no site: query", not any("site:" in w for w in none.web))

uk = q.build_query_plan(CAT, ENT, platform="amazon_uk")
check("a regional alias scopes to its own domain",
      any("site:amazon.co.uk" in w for w in uk.web), uk.web)

print("\nfingerprint stability — the cache economics")

a = q.build_query_plan(CAT, ENT, platform="amazon")
b = q.build_query_plan(CAT, ENT, platform="amazon")
check("identical inputs give an identical fingerprint", a.fingerprint() == b.fingerprint())

drifted = q.build_query_plan(
    CAT, ExtractedEntities(format_type="veggie capsules", dosage_info="400mg",
                           certifications=["NSF Certified"]), platform="amazon")
check("MODEL DRIFT in entities does NOT change the fingerprint",
      a.fingerprint() == drifted.fingerprint(),
      (a.fingerprint(), drifted.fingerprint()))
check("...even though it did change the queries", a.all_queries != drifted.all_queries)

check("a different platform is a different key",
      a.fingerprint() != q.build_query_plan(CAT, ENT, platform="walmart").fingerprint())
check("a regional alias folds to the same key as its canonical platform",
      a.fingerprint() == uk.fingerprint())
check("a different subcategory is a different key",
      a.fingerprint() != q.build_query_plan(
          CategoryClassification(vertical="v", category="c", subcategory="Creatine"),
          ENT, platform="amazon").fingerprint())
check("a different limit is a different key",
      a.fingerprint() != q.build_query_plan(CAT, ENT, platform="amazon", limit=20).fingerprint())
check("a different country is a different key",
      a.fingerprint() != q.build_query_plan(CAT, ENT, platform="amazon", country="uk").fingerprint())

# fingerprint() recomputes on every call, so the baseline has to be captured
# before the version is bumped — comparing a live plan against itself afterwards
# would compare two post-bump values and always agree.
_baseline = a.fingerprint()
_v = q.DISCOVERY_VERSION
try:
    q.DISCOVERY_VERSION = _v + 1
    check("bumping DISCOVERY_VERSION invalidates every key",
          q.build_query_plan(CAT, ENT, platform="amazon").fingerprint() != _baseline)
finally:
    q.DISCOVERY_VERSION = _v
check("...and restoring it restores the key", a.fingerprint() == _baseline)

check("subcategory case and padding do not fork the key",
      a.fingerprint() == q.build_query_plan(
          CategoryClassification(vertical="v", category="c",
                                 subcategory="  magnesium glycinate  "),
          ENT, platform="amazon").fingerprint())

print("\ndegenerate input")

bare = q.build_query_plan(
    CategoryClassification(vertical="Supplements", category="Minerals", subcategory=""))
check("an empty subcategory still yields a usable query",
      bool(bare.shopping and bare.shopping[0].strip()), bare.shopping)
check("no entities at all is fine", bool(q.build_query_plan(CAT).shopping))

print()
print(f"{sum(results)}/{len(results)} checks passed")
print("QUERY PLAN PASS" if all(results) else "QUERY PLAN FAIL")
sys.exit(0 if all(results) else 1)
