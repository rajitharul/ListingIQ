# How competitor scouting works

Reference, not a change record. Written while diagnosing the empty-benchmark
incident, using the creatine run as the worked example.

Nothing here asks a model "who are the top 10 competitors in this category".
That would be a fabricated statistic presented to a customer as evidence. Every
competitor is something a search engine actually returned.

```
query plan  →  discovery (Serper)  →  merge & dedupe  →  extraction  →  scoring
              who sells this & where    one row per        read each page
                                        real product
```

Composed by `WebSearchProvider.fetch()` in `providers/web.py`.

## 1. Build the queries — `providers/query.py`

Pure function, no I/O. From the classified subcategory plus extracted entities.
For the creatine listing:

| Leg | Query |
|---|---|
| Shopping | `Creatine Monohydrate Powder` |
| Web | `best Creatine Monohydrate Powder` |
| Web, platform-scoped | `Creatine Monohydrate Powder site:amazon.com` |

The qualifier is the most narrowing entity available — format type, else dosage
strength.

The open-web leg always runs. Shopping indexes merchant feeds and structurally
under-returns direct-to-consumer stores, so without it the "whole category"
cohort is just more marketplaces and earns nothing the same-platform cohort did
not already say.

The `site:` leg exists so the same-platform cohort is reliably populated rather
than left to whatever Shopping surfaced. Shopping does not honour `site:`.

**The user's brand never appears in the query.** A `-brand` term silently drops
legitimate competitors that merely mention the brand. Exclusion is a post-filter.

Everything downstream is seeded by the classified subcategory, which is why a
classification bug is never only a scoring bug — it reshapes the searches too.

## 2. Discovery, two channels — `providers/discovery/serper.py`

They answer different halves of the question.

**Google Shopping** knows the commerce: who sells it, at what price, what
rating, how many reviews, ranked by commercial relevance. It does not give an
address. Every `link` is a `google.com/search?ibp=oshop` interstitial, verified
against the live API, so the URL is **deliberately discarded** and the platform
taken from the `source` merchant name instead. Fetching that link would scrape a
Google results page and score it as somebody's listing copy.

**Google organic** is the mirror image: real product URLs, no commercial data.

Creatine run: 53 candidates — 13 with URLs, 40 shopping-only.

## 3. Merge — `providers/discovery/merge.py`

Where the two halves become one set.

`graft_shopping_metadata` matches a shopping row to a web row by **title
containment**, not Jaccard. "Spring Valley Magnesium Glycinate 120ct" against
"Spring Valley High Absorption Magnesium Glycinate Capsules for Bone and Muscle
Support" scores 0.40 by Jaccard and 0.80 by containment.

Containment alone is unsafe inside one category, because every title contains
the category term. So a match also needs **shared tokens that are not the
category term**, or a storefront that corroborates it. A successful graft yields
a competitor that is both readable and priced; the creatine run grafted 10.

Then dedupe in layers: exact identity, order-independent token identity, and a
per-storefront cap. Where the heuristics disagree the code **under-collapses on
purpose** — keeping a duplicate slightly overstates the cohort, while merging
two genuinely different SKUs deletes a real competitor.

Selection order is `extractable` first, then `metadata_only`: a page that can be
read is worth more than one that can only be priced.

## 4. Extraction — `providers/extract/`

Only candidates with a real URL are fetched. `PlatformAwareExtractor` routes:

- **Amazon → product API.** Amazon publishes no `schema.org` markup and returns
  ~150,000 characters of markdown that is almost entirely navigation. Generic
  extraction yields category links as bullet points.
- **Everything else → Firecrawl**, which handles the JS rendering and
  bot-blocking that make a plain GET useless.

Per page, in order of preference:

1. `schema.org/Product` JSON-LD from the raw HTML — exact and free
2. bullets as the page renders them, verbatim from markdown
3. one batched model call for whatever is still missing

A specialised reader that fails falls back to the generic one. That is from a
live incident: Rainforest credits ran out, every Amazon competitor came back
empty, and Firecrawl sat idle. A specialised reader failing must never be worse
than not having routed there at all.

## The rules that make the numbers trustworthy

The load-bearing part. Each was written after the opposite behaviour shipped.

- **A page we could not read is still a real competitor.** Shown, with
  `counts_toward_benchmark=False`. Scoring an extraction failure drags the
  competitor mean down and *inflates* the user's percentile — a flattering wrong
  number, which nobody reports as a bug.
- **What was not observed stays unobserved.** An organic-only competitor has no
  price and no rating; those stay empty, never `0.0`, because the statistics
  layer averages them.
- **Degrading is not estimating.** If extraction fails wholesale the result stays
  `web_search` and says what was thin. It never falls through to the
  model-estimated provider, which would be a lie in the other direction.
- **Navigation is well-formed markdown.** Breadcrumbs, footer columns, variant
  pickers and browser error messages all arrive as valid list items.
  `"Try disabling your extensions."` was once captured as a competitor's only
  selling point and scored on the rubric. Hence the chrome filter and a minimum
  bullet count — one surviving bullet is an extraction artefact far more often
  than a listing with exactly one selling point.
- **"Tested" and "reviewed" are product claims, not article markers.**
  "Third-Party Tested" is among the commonest real supplement claims. The article
  filter matches shapes like "Best N", "Top N" and "we tested", and any page
  publishing `schema.org/Product` is exempt regardless of its title.

## Cost

Roughly 3 search queries plus one page fetch per competitor — about a cent per
uncached subcategory, against 11 requests for the Amazon-only path.

Caching carries the rest of the day, which is exactly why a provider fix looks
like it failed until both caches are cleared.
