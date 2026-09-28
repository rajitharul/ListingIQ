# Changes made

Everything altered in the session, code and operational.

## Code

### `backend/data/rubrics/loader.py` — bidirectional subcategory matching

`resolve_subcategory` tested containment one way, so a classifier output longer
than the canonical name fell through to the generic rubric. Now tests both
directions, takes the longest match, and guards against near-empty queries.
Full reasoning in [01-incident-empty-benchmark.md](01-incident-empty-benchmark.md).

Tracked by git.

### `backend/providers/extract/firecrawl.py` — `onlyMainContent: False`

The scrape request asked Firecrawl for "main content" only, which returned page
navigation rather than product copy on storefronts whose copy sits outside a
main landmark. Every page then failed the quality guard and was excluded from
the benchmark.

**Not tracked by git** — `git ls-files` does not list this file. The fix will
not be committed until somebody adds it.

### `backend/tests/test_rubric_resolution.py` — new, 15 checks

Pins both fixes. Caught a regression in the first version of the loader fix
(empty query matching every rubric) on its first run.

### `frontend/src/components/ListingInputForm.tsx` — URL import removed

Removed the "Paste your product URL — any store" label, the input, the
"Read page" button, and the success and error messages.

Also removed what that feature alone owned, so nothing was orphaned:

- `handleFetch()`
- four hooks: `url`, `fetching`, `fetchError`, `source`
- the now-unused `ExtractListingResponse` and `OwnListingSource` type imports

`tsc --noEmit` is clean. The form now runs from the demo presets straight into
Product Title.

**The backend path was deliberately left in place** — `/api/extract`,
`providers/extract/listing.py` and `tests/test_own_listing.py` are untouched,
because removing them also touches the agent catalog and is a larger change than
was asked for. The control is gone from the UI; the endpoint still answers.

## Test status after the changes

17 of 18 existing suite files pass, plus the new one.

Two failures, **both pre-existing**. Verified by stashing the session's changes
and re-running — they fail identically without them:

| Suite | Failing check |
|---|---|
| `tests/smoke_resilience.py` | listings_counted matches the real competitor count |
| `tests/test_eval_harness.py` | setup runs once per listing |

## Operational

### Accounts replaced

The CLI has no `delete` command, only `deactivate`, so removal was direct SQL
after checking every table carrying an `account_id`.

Order mattered: the new admin was created **before** anything was deleted, so
the system was never without one.

| Account | Action |
|---|---|
| `acct_54abf97decdf` · admin@listingiq.local | deleted |
| `acct_a581dac89cec` · tester@listingiq.local | deleted |
| `acct_d328dfe28b0d` · **admin@coderemlabs.com** | created, admin, active |

Also deleted: 12 sessions and 2 `daily_usage` rows belonging to those accounts.

`create-admin` refuses to run when an admin already exists, so `--force` was
needed. That guard is deliberate — it stops the bootstrap command being used
casually once the system is live.

**The two API keys were not touched.** "Local web app" and "Curl testing" both
carry `account_id: None` — orphans from before accounts existed. They were not
the deleted accounts' to lose. They will not authenticate either way: a key with
no owning account is refused rather than assigned a guessed owner. Reissue them
under the new admin if they are needed.

**Backup:** `backend/data/auth.db.bak.20260928-092746`, taken before any change.

The temporary password was generated at the terminal and is not recorded here.
Rotate it with `manage_accounts.py password acct_d328dfe28b0d`.

### Caches cleared

`competitor_cache` (4 rows) and `benchmark_cache` (2 rows) emptied, because they
were serving the pre-fix extraction failure and preventing the fix from being
exercised. The first run after this pays full discovery and page-fetch cost.

### Services

`frontend/.env.local` points at `BACKEND_URL=http://localhost:8010`.

A backend was started on **8010** and a frontend on **3010**, both bound to
localhost only. The backend runs with `reload=True`, so the worker picked up
both code fixes automatically — it restarted one second after `loader.py` was
saved.

**Port 8000 is not this project.** The uvicorn listening there is
`GRACE_FreshMart` (`app.main:app`), running since 12 September. It was
originally mistaken for this project's backend. Nothing is misrouted, because
the frontend points at 8010, but do not assume 8000 is Contrem Analyser.

## Documents produced

- `docs/investor-onepager.html`
- `docs/investor-onepager.pdf` — 5 pages, A4

See [04-investor-brief.md](04-investor-brief.md).
