"""
Renders an eval run into a report and an overall verdict.

Reads only the saved results JSON, so it can be re-run against old results for
free — useful for diffing a prompt change against the previous baseline.
"""
from __future__ import annotations

from collections import defaultdict

from evals.stats import (
    DIM_SD_STABLE,
    DIM_SD_UNSTABLE,
    MIN_TIER_CORRELATION,
    SD_UNSTABLE,
    consistency,
    spearman,
    summarize,
    tier_correlation,
    verdict,
)

W = 78


def _rule(char: str = "─") -> None:
    print("  " + char * W)


def _header(title: str) -> None:
    print()
    print(f"  {title}")
    _rule()


def render(payload: dict) -> bool:
    """Print the report. Returns True if the run passes every gate."""
    meta = payload["meta"]
    obs = payload["observations"]
    by_listing: dict[str, list[dict]] = defaultdict(list)
    for o in obs:
        by_listing[o["id"]].append(o)

    print()
    _rule("═")
    print(f"  ListingIQ eval — mode={meta['mode']}  repeats={meta['repeats']}  "
          f"listings={len(by_listing)}  tokens={meta.get('total_tokens', 0):,}")
    _rule("═")

    failures: list[str] = []

    # ── Overall score stability ──────────────────────────────────
    _header("OVERALL SCORE STABILITY")
    print(f"  {'listing':<22} {'tier':<9} {'mean':>6} {'sd':>6} {'range':>12}   verdict")
    worst_sd, worst_id = 0.0, ""
    for lid, runs in sorted(by_listing.items()):
        s = summarize([r["overall_score"] for r in runs])
        v = verdict(s.sd)
        if s.sd > worst_sd:
            worst_sd, worst_id = s.sd, lid
        print(f"  {lid:<22} {runs[0]['tier']:<9} {s.mean:>6.2f} {s.sd:>6.2f} "
              f"{s.lo:>5.1f}-{s.hi:<5.1f}   {v}")
    _rule()
    if worst_sd > SD_UNSTABLE:
        failures.append(
            f"overall score unstable: sd {worst_sd:.2f} on '{worst_id}' "
            f"(limit {SD_UNSTABLE})"
        )
        print(f"  worst: sd {worst_sd:.2f} on '{worst_id}' — exceeds {SD_UNSTABLE} limit  FAIL")
    else:
        print(f"  worst: sd {worst_sd:.2f} on '{worst_id}' — within {SD_UNSTABLE} limit  PASS")

    # ── Per-dimension stability ──────────────────────────────────
    _header("LEAST STABLE DIMENSIONS")
    dim_rows = []
    for lid, runs in by_listing.items():
        names = set()
        for r in runs:
            names |= set(r["dimension_scores"])
        for name in names:
            vals = [r["dimension_scores"][name] for r in runs if name in r["dimension_scores"]]
            if len(vals) < 2:
                continue
            s = summarize(vals)
            dim_rows.append((s.sd, name, lid, s, len(vals), len(runs)))
    dim_rows.sort(reverse=True, key=lambda r: r[0])

    if not dim_rows:
        print("  (not enough repeats to measure)")
    else:
        print(f"  {'dimension':<34} {'listing':<20} {'mean':>6} {'sd':>6}  verdict")
        for sd, name, lid, s, seen, total in dim_rows[:10]:
            note = "" if seen == total else f"  [only {seen}/{total} runs]"
            print(f"  {name[:34]:<34} {lid[:20]:<20} {s.mean:>6.2f} {sd:>6.2f}  "
                  f"{verdict(sd, DIM_SD_STABLE, DIM_SD_UNSTABLE)}{note}")
        # Aggregate by dimension name: the per-listing table above is usually
        # one loose dimension repeated, and it is the dimension's
        # scoring_criteria prose that needs the edit, not any one listing.
        agg: dict[str, list[float]] = defaultdict(list)
        for sd, name, _lid, _s, _seen, _total in dim_rows:
            agg[name].append(sd)
        ranked = sorted(
            ((sum(v) / len(v), name, len(v)) for name, v in agg.items()),
            reverse=True,
        )
        print()
        print(f"  worst dimensions overall (mean sd across listings):")
        for mean_sd, name, n in ranked[:5]:
            print(f"    {name[:44]:<44} {mean_sd:>5.2f}  across {n} listing(s)")

        _rule()
        unstable_dims = {name for sd, name, *_ in dim_rows if sd > DIM_SD_UNSTABLE}
        if unstable_dims:
            failures.append(
                f"{len(unstable_dims)} dimension(s) exceed sd {DIM_SD_UNSTABLE}: "
                f"{', '.join(sorted(unstable_dims))}"
            )
            print(f"  over the {DIM_SD_UNSTABLE} limit: {', '.join(sorted(unstable_dims))}")
            print("  tighten the scoring_criteria prose for these in their rubric  FAIL")
        else:
            print(f"  all dimensions within the {DIM_SD_UNSTABLE} limit  PASS")

    # ── Classification stability ─────────────────────────────────
    _header("CLASSIFICATION STABILITY")
    print(f"  {'listing':<22} {'chosen subcategory':<28} {'agree':>6}  expected?")
    drift = []
    for lid, runs in sorted(by_listing.items()):
        modal, agree = consistency([r["subcategory"] for r in runs])
        expected = runs[0]["expected_subcategory"]
        matches = "yes" if modal == expected else f"NO ({expected})"
        if agree < 1.0 or modal != expected:
            drift.append(lid)
        print(f"  {lid:<22} {str(modal)[:28]:<28} {agree:>6.0%}  {matches}")
    _rule()
    if drift:
        # Different rubrics between repeats means the scores were never
        # measured on the same criteria, which invalidates their comparison.
        failures.append(f"classification drift or mismatch on {len(drift)} listing(s)")
        print(f"  drift or mismatch on: {', '.join(drift)}  FAIL")
    else:
        print("  every listing classified consistently and as expected  PASS")

    # ── Discrimination ───────────────────────────────────────────
    _header("TIER DISCRIMINATION")
    tiers, means = [], []
    for lid, runs in sorted(by_listing.items()):
        tiers.append(runs[0]["tier"])
        means.append(summarize([r["overall_score"] for r in runs]).mean)
    rho = tier_correlation(tiers, means)

    by_tier: dict[str, list[float]] = defaultdict(list)
    for t, m in zip(tiers, means):
        by_tier[t].append(m)
    for t in ("weak", "moderate", "strong"):
        if by_tier[t]:
            s = summarize(by_tier[t])
            print(f"  {t:<10} n={s.n}  mean {s.mean:>5.2f}   range {s.lo:.1f}-{s.hi:.1f}")
    _rule()
    if rho is None:
        print("  not enough variation to compute rank correlation  SKIP")
    elif rho < MIN_TIER_CORRELATION:
        failures.append(f"tier correlation {rho} below {MIN_TIER_CORRELATION}")
        print(f"  spearman(tier, score) = {rho}  — below {MIN_TIER_CORRELATION}: the scorer "
              f"is not reliably ranking strong above weak  FAIL")
    else:
        print(f"  spearman(tier, score) = {rho}  — at or above {MIN_TIER_CORRELATION}  PASS")

    # ── Percentile coherence ─────────────────────────────────────
    _header("PERCENTILE COHERENCE")
    rho_p = spearman([o["overall_score"] for o in obs], [o["percentile"] for o in obs])
    if rho_p is None:
        print("  not enough variation to compute  SKIP")
    else:
        print(f"  spearman(overall_score, percentile) = {rho_p}")
        print("  percentile is supplied by the model rather than derived from the score,")
        print("  so this is a diagnostic, not a gate. A low value means the two numbers")
        print("  shown side by side in the UI disagree with each other.")

    # ── Verdict ──────────────────────────────────────────────────
    print()
    _rule("═")
    if failures:
        print(f"  VERDICT: FAIL — {len(failures)} gate(s) not met")
        for f in failures:
            print(f"    · {f}")
    else:
        print("  VERDICT: PASS — every gate met")
    _rule("═")
    print()
    return not failures
