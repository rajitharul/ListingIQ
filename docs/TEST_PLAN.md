# ListingIQ — Release Test Plan

UI test script for the multi-platform competitor discovery release.
**Scope:** UI, end to end. **Cases:** 3 setup + 17 test. **Run time:** ~45 min.

The 18 automated backend suites already pass with outbound network blocked, so
anything found here is an integration or presentation issue, not a unit-level one.

---

## 1. What actually changed

| Capability | Before | Now |
|---|---|---|
| **Who counts as a competitor** | Top 10 from one marketplace's search box. A Shopify seller was silently given Amazon results. | Whoever ranks on the open web — a marketplace listing, an eBay item, a brand's own store. Each tagged with where it was found. |
| **Entering your listing** | Paste title, bullets, description, brand by hand. | Paste the product URL and the page is read for you. Everything stays editable. |
| **The headline score** | One percentile against one pooled average. | Two cohorts: your own platform, and the wider category. The report says which one the headline used. |
| **Pages that can't be read** | Scored anyway, on whatever text came back. | Shown as real competitors, excluded from the benchmark, and labelled. |

---

## 2. Before you start — setup gate

Three things are currently wrong on this machine. Skip any of them and you will
be testing the old system while believing you are testing the new one.

**S-1 — Switch the competitor source.** `backend/.env` still says `rainforest`,
which is the Amazon-only path.

```bash
COMPETITOR_PROVIDER=web
```

**S-2 — Restart the backend.** The running process started two days ago, so it
has none of the new code loaded. ListingIQ is on **port 8001** — port 8000 is a
different project, don't kill it.

```bash
# stop the stale process, then
cd backend
./venv/bin/python main.py
```

**S-3 — Confirm it came back.**

```bash
curl -s localhost:8001/health
# expect: {"status":"healthy","engine":"listingiq","version":"1.0.0"}
```

**Known account state:** two accounts exist — `admin@listingiq.local` (admin)
and `tester@listingiq.local` (member, 20 rpm, 60k tokens/day). If a password is
lost: `python manage_accounts.py password <account_id>`.

---

## 3. Access control — regression

### TC-01 · Signed-out visitors cannot reach the analyser
*Why: the whole product is behind a login; a leak here is a billing leak.*

1. Open a private window, go to `http://localhost:3001/`
2. Then try `/admin` directly

**Expected:** both redirect to `/login`. No score data, no competitor names, no
flash of the analyser before the redirect.

### TC-02 · Member sign-in, admin link stays hidden
*Why: role separation is what lets you hand an account to a customer.*

1. Sign in as `tester@listingiq.local`
2. Check the header, then type `/admin` into the address bar

**Expected:** analyser loads; header shows remaining token budget and sign-out,
but **no** admin link. `/admin` is refused.

**Fail if:** a member can open the admin panel, or the budget shown isn't their
own 60,000.

---

## 4. Reading a listing from its URL — NEW

### TC-03 · A pasted product URL fills the form
*Why: first impression of the whole feature. If it's slow or wrong, nobody
reaches the analysis.*

1. Find *"Paste your product URL — any store"* above the form
2. Paste a real brand-store product page, e.g.
   `https://www.thorne.com/products/dp/magnesium-glycinate`
3. Press **Read page** (or Enter)

**Expected:**
- Button shows *Reading…* and is disabled while it works. Roughly 5–20 seconds.
- Title, description, bullets and brand populate below.
- A green line says which platform it was read as and how many fields were filled.
- Platform selector switches to **My own brand site** — *not* Amazon.
- Everything remains editable.

**Fail if:** the platform defaults to Amazon for a non-Amazon URL. That was the
original bug this build exists to remove.

### TC-04 · What the user typed is never overwritten — DATA INTEGRITY
*Why: someone who corrected a mangled title must not have the correction
silently reverted by the live page.*

1. Reload to clear the form
2. Type `MY CORRECTED TITLE` into Product Title and `MyBrand` into Brand Name.
   Leave the rest empty.
3. Paste the same product URL, press **Read page**

**Expected:** title still reads `MY CORRECTED TITLE`; brand still `MyBrand`.
Only empty fields fill. The confirmation names just those fields.

**Fail if:** any field you typed is replaced.

### TC-05 · A bad URL fails politely

1. Try `not-a-url`
2. Try `https://example.com/nothing-here`
3. Try a homepage with no product, e.g. `https://www.thorne.com/`

**Expected:** an amber message explaining what went wrong, ending with a note
that you can fill the fields in by hand. The form keeps whatever you typed. No
stuck spinner, no blank page, no raw stack trace.

---

## 5. The analysis run

### TC-06 · All ten stages stream to completion

1. Fill the form (the **Weak Magnesium** preset is fine, or the listing from TC-03)
2. Submit and watch the progress overlay

**Expected:**
- Ten stages tick through in order, ending at Rewrite Verifier. ~60–100 seconds.
- The pipeline diagram shows ten completed nodes, none skipped.
- Every result section renders: score, competitors, benchmark, analysis,
  recommendations, rewrites.

**Fail if:** a stage shows 0 ms, any node reads "skipped", or the run ends with
a partial page.

### TC-07 · Competitors come from more than one platform — HEADLINE
*Why: this single check is the release. Everything else is supporting evidence.*

1. Scroll to the competitor cards
2. Read the small platform badge on each card
3. Click a competitor title

**Expected:**
- **At least two different platforms** across the set — e.g. some Amazon, some
  Brand site.
- No single storefront holds more than four cards.
- Titles are links that open the real competitor page in a new tab.
- No competitor is your own brand.

**Fail if:** every competitor is on one platform, a link goes to a
`google.com/search` page, or your own store appears as a competitor.

### TC-08 · The provenance strip tells the truth
*Why: customers are being asked to trust a number. This strip is where that
trust is earned or lost.*

1. Find the provenance line under the hero score, and again above the cards

**Expected:**
- A green **Live data** pill with the competitor count.
- One grey pill per platform, e.g. `4 × Amazon`, `2 × Brand site`. These add up
  to the number of cards.
- A "fetched N minutes ago" timestamp.
- A sentence describing the mix and anything dropped or unreadable.

**Fail if:** the platform counts don't sum to the number of cards shown.

### TC-09 · Unreadable pages are shown but not scored — DATA INTEGRITY
*Why: if a page we failed to read were scored, it would score badly, drag the
competitor average down, and **inflate** the customer's percentile. A flattering
wrong number is the one nobody reports.*

1. Look for any card with an amber **not scored** badge
2. Hover it to read the reason
3. Compare against the sentence in the provenance strip

**Expected:**
- The card is still displayed with its title and link — it is a real competitor.
- It has no invented bullets or description.
- The count in "N of M pages could not be read in full" matches the number of
  badged cards.

**Fail if:** a badged card still shows bullet copy, or the counts disagree.

### TC-10 · Nothing unobserved is presented as a fact — DATA INTEGRITY
*Why: a competitor found through a web result has no published price or rating.
Showing "0.0 ★" would state something false about a real business.*

1. Find a card with no price, and one with no rating

**Expected:** they read *"no price shown"* and *"no published rating"* in muted
text. Never `$0.00`, never zero stars, never `(0 reviews)`.

**Fail if:** any zero value is rendered as though it were measured.

### TC-11 · The benchmark panel shows both cohorts
*Why: a marketplace title and a brand-site product name are good listings by
different rules. One pooled average measures house style, not quality. This
panel is also the first time the measured benchmark has ever been visible.*

1. Find **Measured Benchmark**, below the competitor cards
2. Press *Show every competitor's score*

**Expected:**
- Two cards side by side: your platform, and the wider category. One marked
  **headline**.
- Each states a percentile, the competitor count, and their average score.
- The table lists every competitor with platform and score, sorted high to low,
  with your listing highlighted in its true position.
- Any dimension measured on fewer than three competitors is called out in amber.

**Fail if:** your listing's row contradicts the headline percentile — e.g. you
sit above most competitors but are shown in a low percentile.

### TC-12 · A thin cohort refuses to be the headline
*Why: a percentile over two competitors is noise with a decimal point.*

1. Run an analysis with Platform set to **Shopify store** or **My own brand site**
2. Read the benchmark panel

**Expected:** if fewer than four competitors are found on that platform, the
headline card reads **All competitors** and an amber note explains that too few
were found on your own platform to benchmark against. The small cohort is still
computed and visible.

**Fail if:** a percentile is presented as the headline off two or three
competitors with no explanation.

### TC-13 · Rewrite scores are measured, not self-reported
*Why: the generator consistently overrates itself by about four points.*

1. Scroll to **Optimized Rewrites**

**Expected:** each variant shows a green **✓ measured** mark, with the
generator's original prediction in brackets beside it when the two disagree. The
panel states scores were re-scored through the same scorer used on competitors.

**Fail if:** a variant shows only a predicted score, or the headline number is
the prediction.

### TC-14 · The second run in a subcategory is cheap
*Why: cache hit rate is effectively the gross margin on this product.*

1. Run the same listing again without changing the subcategory
2. Compare elapsed time; check the provenance strip

**Expected:** noticeably faster. Provenance timestamp reads *· cached*, and the
same competitors return.

---

## 6. Failure behaviour

These require deliberately breaking something. Do them last, and restore the
config afterwards.

### TC-15 · A dead search key degrades honestly — DATA INTEGRITY
*Why: the one thing the product may never do is present an estimate as an
observation.*

1. In `backend/.env`, set `SERPER_API_KEY=broken`. Restart the backend.
2. Run an analysis in a **new** subcategory (an old one is served from cache)
3. Restore the real key and restart when done

**Expected:**
- The run still completes.
- A prominent **amber** banner: *AI-estimated competitors — not live marketplace
  data*.
- The note explains the live provider was unavailable.
- Running again after restoring the key returns real data — the estimates were
  never cached.

**Fail if:** estimated competitors appear under a green "Live data" pill, or
estimated results persist after the key is fixed.

### TC-16 · Limits are enforced per account

1. As `tester@` (20 rpm, 2 concurrent), submit analyses in quick succession from
   several tabs

**Expected:** beyond the concurrency limit, further runs are refused with a
readable message rather than queuing invisibly or erroring out. The header's
remaining budget decreases after each run.

### TC-17 · Admin can change a customer's limits

1. Sign in as `admin@listingiq.local`, open **Admin**
2. Change the tester's daily token limit and save
3. Try to demote or disable the only admin

**Expected:** limits save and show immediately, with tokens-used-today against
the new budget. Demoting or disabling the last admin is refused with an
explanation — that guard is what stops you locking yourself out.

---

## 7. Do not raise these as defects

Every item below looks like a bug, is not, and was verified against the live
APIs.

- **Rainforest is out of credits right now.** Amazon listings are read through
  the Rainforest product API and that account is exhausted — every lookup
  returns *402 out of credits*. The system falls back to generic page reading
  automatically, so runs still succeed, but Amazon bullet quality is lower than
  it should be.
- **Most competitors show no price.** Price and rating come from Google
  Shopping, whose links are search-engine interstitials rather than merchant
  URLs, so they're matched onto real product pages by title. A competitor whose
  title doesn't match cleanly shows without a price. Blank is correct; invented
  would not be.
- **Amazon competitors have an empty description.** Amazon sellers put long copy
  in A+ content, which is images. There is no text to extract. Description
  dimensions therefore compare against a small sample, and the provenance note
  says so.
- **A run can return fewer than ten competitors.** Duplicates of the same
  product across storefronts are merged, no single storefront may fill the set,
  and articles and category pages are rejected. Six strong distinct competitors
  beat ten padded ones.
- **The competitor set changes between subcategories.** Discovery is a live web
  search. Within one subcategory the set is cached for 24 hours, so a repeat run
  is stable.
- **Scorer evals have not been re-run.** The scorer prompt's "/10 competitors"
  denominators now use the real cohort size. The paid eval harness hasn't run
  since that change, so scoring stability across it is unverified. A known gap,
  not a test failure.

---

## 8. Severity guide

Severity is about what a paying customer would conclude, not how visible the
glitch is.

| Severity | Definition | Example from this scope |
|---|---|---|
| **S1** | A number is wrong in a way that flatters the customer, or estimated data is presented as observed. | A page we failed to read is scored; estimates under a green "Live data" pill. |
| **S2** | A core capability of this release does not work. | Every competitor on one platform; URL reading fails on valid pages. |
| **S3** | Correct data, confusing presentation. | Counts that don't reconcile between the strip and the cards. |
| **S4** | Cosmetic. | Truncation, spacing, a badge that wraps awkwardly at phone width. |

**When logging a defect,** attach the product URL or preset used, the platform
selected, the full provenance sentence, and the competitor count. Discovery is
live, so a run is not reproducible from the listing alone.
