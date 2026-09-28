# Worklog — 28 September 2026

What was done in one session, why, and what to check if it looks wrong later.

Read [01-incident-empty-benchmark.md](01-incident-empty-benchmark.md) first if
you are here because a run came back with no competitor analysis. It is the
substantial piece of work; everything else is smaller.

| Document | Covers |
|----------|--------|
| [01-incident-empty-benchmark.md](01-incident-empty-benchmark.md) | Two bugs that produced "10 of 10 pages could not be read" and "benchmarked for Other". Diagnosis, evidence, fixes, new test |
| [02-changes.md](02-changes.md) | Every file changed, plus the operational changes: accounts, caches, services |
| [03-competitor-scouting.md](03-competitor-scouting.md) | How competitor discovery actually works, end to end. Reference, not a change record |
| [04-investor-brief.md](04-investor-brief.md) | The one-page investor document in `docs/`, and the decisions behind what it says |

## Summary

**Fixed two independent bugs** that between them emptied the competitive
analysis. A backwards containment test in the rubric loader sent products with a
real rubric to the generic one, and a single Firecrawl flag
(`onlyMainContent: True`) returned page navigation instead of product copy, so
every competitor failed the quality guard and was excluded from the benchmark.
Both are one-liners; finding them was the work. Added
`tests/test_rubric_resolution.py` to pin both.

**Removed the "Paste your product URL" control** from the listing form, with the
state and handler it owned. The backend `/api/extract` path is untouched.

**Replaced the account set.** The two bootstrap accounts are gone; one admin
remains, `admin@coderemlabs.com`.

**Wrote an investor one-pager** at `docs/investor-onepager.html` and
`docs/investor-onepager.pdf`.

## Two things that are still broken, and were not touched

Both predate this session. Verified by stashing the session's changes and
re-running: they fail identically without them.

- `tests/smoke_resilience.py` — check "listings_counted matches the real competitor count"
- `tests/test_eval_harness.py` — check "setup runs once per listing"

Everything else in the offline suite passes: 17 of 18 files, plus the new one.

## One thing worth knowing before you debug anything here

`backend/providers/extract/firecrawl.py` is **not tracked by git**. `git ls-files`
does not list it. One of the two fixes lives in that file, so it will not be
committed, reviewed, or deployed by anything that works from the index until
somebody runs `git add` on it.
