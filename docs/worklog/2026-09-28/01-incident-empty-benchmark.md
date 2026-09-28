# Every competitor excluded from the benchmark

## What was reported

A creatine listing produced a complete run — 10 agents, 28.5s, nothing marked
failed — and a competitive analysis with nothing in it:

```
10 competitor listings · benchmarked for Other
10 of 10 pages could not be read in full — shown as competitors, but excluded
from the benchmark so a failed read is not scored as a weak listing.
40 found via shopping results only
4 review article(s) excluded

Competitor Analysis
No competitor pages could be read in full, so no competitive patterns could be
measured for this run.
TOP KEYWORDS    (empty)
COMMON CLAIMS   (empty)
TRUST SIGNALS   (empty)
```

Every competitor card read **not scored**. The overall score was 0.0 / P0.

This is the failure mode the provider layer was designed to make *visible*
rather than silent, and it worked: nothing pretended to be measured. But two
separate bugs had to be fixed before a run could produce anything.

## Ruled out first

Worth recording so nobody re-checks them:

| Suspect | Finding |
|---|---|
| Firecrawl key invalid / out of credits | `POST /v2/scrape` returned **HTTP 200** |
| Firecrawl slow, hitting the deadline | Live fetches took **3.0s and 4.5s** against a 60s deadline and 30s per-page timeout |
| Page content too short for `MIN_EXTRACTED_CHARS` (200) | Returned **3,245 and 20,194 chars** |
| Serper key or organic search broken | 9 organic results, **7 usable product URLs** after filtering |
| `looks_like_product` / article filter too strict | Dropped exactly 2 of 9, both correctly (a category listing page and a Healthline round-up) |
| Selection ordering preferring address-less rows | `merge.py:183` already sorts `extractable` before `metadata_only` |
| "40 found via shopping results only" | **Not a bug.** By design — see below |

## Bug 1 — "benchmarked for Other"

`data/rubrics/loader.py`, in `resolve_subcategory`:

```python
for subcat in index["subcategories"]:
    if normalized in subcat.lower():      # input inside canonical name
        return subcat
```

Containment was tested one way only. That resolves a classifier output *shorter*
than the canonical name and drops anything *longer* to the generic rubric:

| Classifier says | Resolved to |
|---|---|
| `creatine` | Creatine Monohydrate |
| `Creatine Powder` | Creatine Monohydrate |
| `Creatine Monohydrate Powder` | **None → generic** |
| `Creatine Monohydrate Supplement` | **None → generic** |
| `Micronized Creatine Monohydrate` | **None → generic** |
| `Creatine Supplements` | **None → generic** |

`supplements_creatine_monohydrate.json` sat unused on disk while the listing was
graded on nine generic dimensions. Nothing failed loudly. The 27-entry alias
table cannot keep pace with how many ways a model can name a product, which is
why the containment test has to carry the load.

### Fix

```python
# Guarded: every string contains "", so an empty or near-empty query would
# otherwise match every rubric and return the longest one.
if len(normalized) < 3:
    return None
matches = [s for s in index["subcategories"]
           if normalized in s.lower() or s.lower() in normalized]
if matches:
    return max(matches, key=len)
```

Longest match wins so the answer cannot depend on dict iteration order —
`"Vitamin D3 + K2 Softgels"` must not resolve to whichever shorter partial
happens to be enumerated first.

**The `len < 3` guard exists because the first version of this fix was wrong.**
`"" in anything` is `True`, so an empty query matched every rubric and returned
the longest one. The new test caught it on its first run.

## Bug 2 — "10 of 10 pages could not be read"

`providers/extract/firecrawl.py` sent `onlyMainContent: True`. Firecrawl's
main-content heuristic picks the wrong region on storefronts whose product copy
sits outside a `<main>`/`<article>` landmark, and returns the nav and promo
chrome instead.

Measured against `nutricost.com/products/creatine-monohydrate`, same URL, same
few minutes:

| Request | Body | Contains "creatine" | `is_usable` |
|---|---|---|---|
| `onlyMainContent: true` (was) | 3,245 chars | **no** | reject |
| `onlyMainContent: true` + `waitFor: 4000` | 3,245 chars | **no** | reject |
| `onlyMainContent: false` | 9,559 chars | yes | **pass** |

The returned 3,245 characters were a promo banner and a nav menu that never once
said "creatine". Note the middle row: this is **not** a JavaScript rendering
problem, and adding `waitFor` fixes nothing. Only the flag matters.

### The quality guard was not at fault

`is_usable` requires at least two distinctive tokens shared with the title being
searched for. On the chrome-only body the overlap was `{"nutricost"}` — one
token, from the brand appearing in nav URLs.

It rejected the page correctly. Scoring navigation text as listing copy would
have dragged the competitor mean down and **inflated the user's percentile** —
the flattering wrong number the module docstring exists to prevent. The
"not scored" labels were the safety net doing its job, not the bug.

### Fix

`onlyMainContent: False`, with the measurement recorded in a comment beside it
so it is not flipped back for tidiness.

## Not a bug: "40 found via shopping results only"

Working as designed, and worth understanding before someone "fixes" it.

Every `link` in a Serper `/shopping` response is a
`google.com/search?ibp=oshop` interstitial, never the merchant's product page.
So `discovery/serper.py` deliberately discards the URL and keeps the merchant,
price, rating and review count. `merge.graft_shopping_metadata` then joins that
onto an organic result that *does* have an address. A shopping row that matches
nothing remains a real, priced competitor whose page cannot be read.

Reproduced with the live API for `Creatine Monohydrate Powder`:

```
queries:  'Creatine Monohydrate Powder'
          'best Creatine Monohydrate Powder'
          'Creatine Monohydrate Powder site:amazon.com'

candidates 53: withURL=13  shoppingOnly=40
report: {'articles': 4, 'domain_capped': 5, 'metadata_only': 30,
         'priced': 10, 'considered': 53}
chosen 10: readable=4  addressless=6
```

`shoppingOnly=40` and `articles=4` match the reported UI text exactly, which is
what confirmed the reproduction was the same run shape. Note `readable=4` —
there *were* fetchable pages. They all failed extraction, for the reason above.

## Why the fix did not appear to work at first

Two further runs showed the identical panel. The badge said:

```
fetched 13m ago · cached        …then…        fetched 14m ago · cached
```

The competitor set was served from `competitor_cache`, and the benchmark from
`benchmark_cache` keyed to that same set, so neither run called Firecrawl at
all. The timestamp incrementing by one minute — rather than resetting to
"fetched just now" — is the tell that no new run happened.

Both caches were cleared (4 and 2 rows). There is no in-process cache layer;
SQLite is the only one.

**When verifying a provider-layer fix, clear both caches first**, or the run
will replay the broken result and look like the fix failed.

## The test

`backend/tests/test_rubric_resolution.py`, 15 checks, plain-script style matching
the rest of the suite. It pins:

- the four spoken forms that used to fall through to generic
- that aliases and shorter-than-canonical forms still resolve
- that skincare uses the same path (`"Vitamin C Serum 20%"`)
- longest-match determinism (`"Vitamin D3 + K2 Softgels"`)
- that genuinely unknown products (`"Bluetooth Headphones"`) and empty queries
  still return `None` — the generic rubric must stay reachable, just not by
  accident
- the Firecrawl request shape: `onlyMainContent` is `False`, and `rawHtml` is
  still requested so JSON-LD remains the first choice

The request-shape checks stub `providers.http.make_client`, which is the seam
the rest of the suite uses.

## If this recurs

1. Look at the badge. `cached` means the provider layer never ran — clear
   `competitor_cache` and `benchmark_cache` and try again.
2. Check whether the rubric name in the score header matches the one in the
   Competitive Landscape panel. Disagreement means one of them is cached.
3. Fetch one competitor URL through Firecrawl by hand and run `is_usable`
   against the body with the expected title. If the overlap is thin, the fetch
   returned chrome, not copy.
4. Remember that the pipeline completing with every stage green tells you
   nothing here. Every one of these failures is designed to degrade visibly
   rather than raise.
