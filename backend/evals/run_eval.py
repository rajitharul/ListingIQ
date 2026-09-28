#!/usr/bin/env python3
"""
Score stability and discrimination harness.

    # cheap: setup once per listing, then repeat only the scorer
    python evals/run_eval.py --mode scorer --repeats 5

    # expensive: the whole 8-agent pipeline, every repeat
    python evals/run_eval.py --mode full --repeats 3

    # re-report from saved raw results, free
    python evals/run_eval.py --analyze evals/results/<file>.json

Unlike the other test suites in this repo, this one CALLS THE REAL MODEL — a
stubbed model would only measure the stub. It prints a cost estimate and waits
for confirmation before spending anything.

Two modes because cost decides how often this gets run:

  scorer  Stages before the scorer execute once per listing and their output is reused, so
          every repeat scores IDENTICAL inputs. That isolates the scorer's own
          variance, which is what a prompt edit to benchmark_scorer changes.
          Cost per listing: 6 calls + repeats.

  full    Every repeat runs all 8 agents from scratch, so the variance measured
          includes classification flips and competitor-set churn. This is what
          a customer actually experiences. Cost per listing: repeats x 9.

Raw per-run results are always written to evals/results/ so the analysis can be
re-run, extended or diffed later without paying again.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import pathlib
import sys
import time
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agents.benchmark_scorer import score_listing
from agents.category_classifier import classify_category
from agents.competitor_analyzer import analyze_competitors
from agents.competitor_scorer import score_competitors
from agents.competitor_scout import scout_competitors
from agents.input_parser import parse_listing
from agents.listing_analyzer import analyze_listing
from agents.llm_client import LLMCallError, get_usage, start_usage_tracking
from models.schemas import ListingInput

from evals import report as report_mod

FIXTURES = pathlib.Path(__file__).parent / "fixtures.json"
RESULTS_DIR = pathlib.Path(__file__).parent / "results"


def load_fixtures(only: list[str] | None) -> list[dict]:
    data = json.loads(FIXTURES.read_text())["listings"]
    if not only:
        return data
    chosen = [l for l in data if l["id"] in only]
    missing = set(only) - {l["id"] for l in chosen}
    if missing:
        sys.exit(f"Unknown listing id(s): {', '.join(sorted(missing))}")
    return chosen


async def _prepare(listing_input: ListingInput) -> dict:
    """
    Run every stage before the scorer. Their output is the scorer's input.

    The measured competitor benchmark is part of this fixed setup, so repeats in
    scorer mode are graded against an identical benchmark — isolating the
    scorer's own variance rather than mixing in benchmark variance.
    """
    parsed = await parse_listing(listing_input)
    category, rubric = await classify_category(parsed)
    scout = await scout_competitors(category, parsed.platform, parsed.brand_name)
    comp_analysis = await analyze_competitors(scout, rubric)
    benchmark = await score_competitors(scout, rubric)
    listing_analysis = await analyze_listing(parsed, rubric)
    return {
        "parsed": parsed, "category": category, "rubric": rubric,
        "competitor_analysis": comp_analysis, "listing_analysis": listing_analysis,
        "benchmark": benchmark,
    }


def _observation(fixture: dict, repeat: int, ctx: dict, scores, elapsed: float) -> dict:
    usage = get_usage()
    return {
        "id": fixture["id"],
        "tier": fixture["tier"],
        "repeat": repeat,
        "subcategory": ctx["category"].subcategory,
        "expected_subcategory": fixture["expected_subcategory"],
        "rubric_version": ctx["rubric"].version,
        "overall_score": scores.overall_score,
        "percentile": scores.percentile,
        "dimension_scores": {d.dimension: d.score for d in scores.dimension_scores},
        "duration_s": round(elapsed, 1),
        "tokens": usage.total_tokens if usage else 0,
    }


async def run_listing(fixture: dict, mode: str, repeats: int, sem: asyncio.Semaphore) -> list[dict]:
    """Produce `repeats` observations for one fixture."""
    out: list[dict] = []
    async with sem:
        try:
            shared = await _prepare(ListingInput(**fixture["listing"])) if mode == "scorer" else None

            for r in range(repeats):
                start_usage_tracking()
                t0 = time.perf_counter()
                ctx = shared if mode == "scorer" else await _prepare(
                    ListingInput(**fixture["listing"])
                )
                scores = await score_listing(
                    ctx["listing_analysis"], ctx["competitor_analysis"],
                    ctx["rubric"], ctx["parsed"], ctx["benchmark"],
                )
                out.append(_observation(fixture, r, ctx, scores, time.perf_counter() - t0))
                print(f"    {fixture['id']:<22} repeat {r + 1}/{repeats}  "
                      f"score={scores.overall_score:>4.1f}  "
                      f"{out[-1]['duration_s']:>5.1f}s")
        except LLMCallError as e:
            # One listing failing must not discard the whole run's data.
            print(f"    {fixture['id']:<22} FAILED: {e}")
    return out


async def run(args) -> int:
    fixtures = load_fixtures(args.listings)
    per_listing = (6 + args.repeats) if args.mode == "scorer" else (args.repeats * 9)
    total_calls = per_listing * len(fixtures)

    print()
    print(f"  mode          {args.mode}")
    print(f"  listings      {len(fixtures)}")
    print(f"  repeats       {args.repeats}")
    print(f"  concurrency   {args.concurrency}")
    print(f"  LLM calls     ~{total_calls}  ({per_listing} per listing)")
    print()
    print("  This calls the real model and will cost money.")
    if not args.yes:
        if input("  Proceed? [y/N] ").strip().lower() not in ("y", "yes"):
            print("  Aborted.")
            return 1
    print()

    sem = asyncio.Semaphore(args.concurrency)
    t0 = time.perf_counter()
    batches = await asyncio.gather(
        *(run_listing(f, args.mode, args.repeats, sem) for f in fixtures)
    )
    observations = [o for batch in batches for o in batch]
    elapsed = time.perf_counter() - t0

    if not observations:
        print("\n  No observations collected — every listing failed.")
        return 1

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = RESULTS_DIR / f"{args.mode}_{args.repeats}x_{stamp}.json"
    path.write_text(json.dumps({
        "meta": {
            "mode": args.mode, "repeats": args.repeats,
            "listings": len(fixtures), "created_at": stamp,
            "duration_s": round(elapsed, 1),
            "total_tokens": sum(o["tokens"] for o in observations),
        },
        "observations": observations,
    }, indent=2))

    try:
        shown = path.relative_to(ROOT)
    except ValueError:
        shown = path          # results dir configured outside the repo
    print(f"\n  {len(observations)} observations in {elapsed:.0f}s  ->  {shown}")
    report_mod.render(json.loads(path.read_text()))
    return 0


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mode", choices=["scorer", "full"], default="scorer")
    p.add_argument("--repeats", type=int, default=5, help="runs per listing (default 5)")
    p.add_argument("--listings", type=lambda s: s.split(","),
                   help="comma-separated fixture ids; default is all")
    p.add_argument("--concurrency", type=int, default=3,
                   help="listings processed in parallel (default 3)")
    p.add_argument("--yes", action="store_true", help="skip the cost confirmation")
    p.add_argument("--analyze", metavar="FILE",
                   help="re-render the report from a saved results file and exit")
    args = p.parse_args()

    if args.analyze:
        report_mod.render(json.loads(pathlib.Path(args.analyze).read_text()))
        return 0
    if args.repeats < 2:
        sys.exit("--repeats must be at least 2; stability needs more than one measurement.")
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
