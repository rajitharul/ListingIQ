# The investor one-pager

`docs/investor-onepager.html` and `docs/investor-onepager.pdf` (5 pages, A4).

A single self-contained HTML file with no assets and no build step. The PDF is
rendered from it, so the HTML is the source — regenerate rather than editing the
PDF.

## What it says

Hook → the problem → every storefront → what the seller gets → before/after →
three steps → why this is hard to copy.

The opening is deliberately plain-spoken:

> You're about to put a product up for sale. Is your listing good enough?
> Most sellers have no idea. They write it, they publish it, and they hope.

Three illustrated beats (product ready · nobody tells you if it's good ·
competitors sit beside you), then the product name, then three promises, then
the punchline:

> To make the sale you have to stand above your competitors: better content,
> written for your customer. **We do that for you.**

## Decisions that are not obvious from reading it

**It is named Contrem Analyser throughout**, including the `<title>`. The
codebase and the application UI say **ListingIQ**. These disagree. If the app is
demonstrated in the same meeting as this document, they will look like two
products.

**The "$0.03 per analysis" claim from the README was removed.** It could not be
verified, and the eval figures (~157k tokens across ~120 calls) imply a full
run costs meaningfully more. The page says "under $1" instead. Against a
$500–2,000 consultant the argument loses nothing and gains a number that
survives scrutiny. **The README still carries the $0.03 claim and should be
corrected.**

**The eval evidence was cut on request.** Earlier drafts led with the measured
scoring results — stability sd 0.29 against a 0.75 limit, tier discrimination
0.859, 100% classification consistency, and the anchored-criteria finding
(1.10 → 0.00). That was the strongest and least fakeable material on the page.
It now survives only as a qualitative claim under "Judgement that is tested".
Worth having those numbers to hand verbally; an investor who engages will ask.

**The honest-gaps column was also cut on request.** It disclosed that competitor
data came from model knowledge rather than a live feed, that memory was not
wired in, and that score bands overlap. That disclosure is now absent, so a
reader will assume competitor figures shown in a demo are observed. Note this is
no longer true in the same way — competitors are now fetched live — but the
score-band overlap still stands.

**Platform claims were taken from the code, not guessed.**
`backend/providers/platforms.py` defines the registry, and the pills on the page
list exactly what it supports: Amazon, eBay, Walmart, Etsy, Shopify, Target,
Best Buy, AliExpress, iHerb, Daraz, Noon, and a brand's own store. The three
worked examples (eBay's 80-character title cap and absent bullets, Amazon's
image-based A+ content, Shopify's prose-not-bullets) also come from that file.

**No buttons and no links.** The page is for reading, not operating.

**Em dashes were removed throughout** at the author's request — 18 of them,
rewritten as sentences rather than swapped for commas.

## Design

Minimal by request, after an earlier pastel-mesh-and-grain version was rejected
as misaligned and off-colour.

White ground, near-black type, hairline rules, Inter. One accent, `#5D4E9C`,
carried only by type — wordmark, section eyebrows, the product-name reveal, the
step numerals, and the "as rewritten" label. That is the lavender from the
rejected palette, stepped down until it passes contrast on white (≈6.9:1); the
original `#DDD6EB` is invisible as text.

The single block of fill is the black punchline bar.

### Alignment

The original grids used `auto-fit` with a minimum card width. At print width
three-item rows silently collapsed to 2 + 1 and left an orphan — the misalignment
that was reported. Fixed by pinning explicit column counts, and pinning them
again inside the print stylesheet so the responsive breakpoint cannot override
them.

## Regenerating the PDF

No PDF renderer is installed. The PDF was produced with the Chromium that
Playwright had already put on disk:

```
/home/coderem/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome \
  --headless --disable-gpu --no-sandbox --no-pdf-header-footer \
  --print-to-pdf=docs/investor-onepager.pdf --virtual-time-budget=10000 \
  http://127.0.0.1:<port>/investor-onepager.html
```

Serve the `docs` folder first; `file://` works less reliably for fonts.

From a browser instead: **Ctrl+P → Save as PDF**, A4, **Background graphics ON**,
default margins. Print from Chrome or Edge rather than Firefox.

Two print rules are load-bearing and were both bugs first:

- Do **not** set a `background` shorthand on `body` inside `@media print`. It
  resets `background-image` and flattens the page. (Now moot — the minimal
  design has no mesh — but the trap remains.)
- Keep `break-inside: avoid` on cards, **not** on whole `<section>` elements.
  On sections it forces each one onto a fresh page and fills the document with
  white space.
