"""
Offline tests for the eval harness: statistics, report rendering, and the
runner's plumbing.

Costs nothing. The statistics are pure functions, the report is driven with
synthetic observations whose right answers are known by construction, and the
runner is exercised against a stubbed model — so a crash in the orchestration
surfaces here rather than part-way through a paid run.
"""
import argparse, asyncio, io, json, os, pathlib, sys, contextlib, tempfile, types, typing

os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-a-real-key")

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from evals.stats import (
    consistency, spearman, summarize, tier_correlation, verdict,
    SD_STABLE, SD_UNSTABLE, DIM_SD_UNSTABLE, MIN_TIER_CORRELATION,
)
from evals import report

results = []
def check(label, passed, detail=""):
    results.append(passed)
    print(f"  {'ok  ' if passed else 'FAIL'} {label}{'  ' + str(detail) if detail else ''}")


# ── summarize ────────────────────────────────────────────────────
s = summarize([5.0, 5.0, 5.0])
check("identical values -> sd 0", s.sd == 0.0 and s.mean == 5.0, s)
s = summarize([4.0, 6.0])
check("mean of two", s.mean == 5.0 and s.lo == 4.0 and s.hi == 6.0, s)
check("single value -> sd 0, not a crash", summarize([7.0]).sd == 0.0)
check("empty -> zeros, not a crash", summarize([]).n == 0)
s = summarize([1.0, 2.0, 3.0, 4.0])
check("sample sd (n-1), not population", abs(s.sd - 1.291) < 0.001, s.sd)
check("spread is hi-lo", summarize([2.0, 9.0]).spread == 7.0)

# ── verdict ──────────────────────────────────────────────────────
check("sd at the stable threshold is stable", verdict(SD_STABLE) == "stable")
check("just over stable -> acceptable", verdict(SD_STABLE + 0.01) == "acceptable")
check("at the unstable threshold is still acceptable", verdict(SD_UNSTABLE) == "acceptable")
check("over the limit -> UNSTABLE", verdict(SD_UNSTABLE + 0.01) == "UNSTABLE")

# ── consistency ──────────────────────────────────────────────────
m, frac = consistency(["A", "A", "A"])
check("unanimous -> 1.0", m == "A" and frac == 1.0)
m, frac = consistency(["A", "A", "B", "B"])
check("tie picks a modal value and reports 0.5", frac == 0.5, (m, frac))
m, frac = consistency(["A", "B", "C", "A"])
check("modal value wins", m == "A" and frac == 0.5, (m, frac))
check("empty -> (None, 0.0)", consistency([]) == (None, 0.0))

# ── spearman ─────────────────────────────────────────────────────
check("perfect positive -> 1.0", spearman([1, 2, 3, 4], [10, 20, 30, 40]) == 1.0)
check("perfect negative -> -1.0", spearman([1, 2, 3, 4], [40, 30, 20, 10]) == -1.0)
check("monotonic but non-linear still 1.0", spearman([1, 2, 3, 4], [1, 4, 9, 16]) == 1.0)
check("constant series -> None, not 0.0", spearman([1, 1, 1, 1], [1, 2, 3, 4]) is None)
check("too few pairs -> None", spearman([1, 2], [1, 2]) is None)
check("mismatched lengths -> None", spearman([1, 2, 3], [1, 2]) is None)
rho = spearman([1, 2, 2, 3], [1, 2, 3, 4])
check("ties handled via average ranks", rho is not None and 0.8 < rho < 1.0, rho)

# ── tier_correlation ─────────────────────────────────────────────
rho = tier_correlation(["weak", "moderate", "strong"], [2.0, 5.0, 8.0])
check("tiers ordered correctly -> 1.0", rho == 1.0, rho)
rho = tier_correlation(["weak", "moderate", "strong"], [8.0, 5.0, 2.0])
check("tiers inverted -> -1.0", rho == -1.0, rho)
check("unknown tier labels ignored",
      tier_correlation(["bogus", "weak", "moderate", "strong"], [9.0, 2.0, 5.0, 8.0]) == 1.0)


# ── report rendering ─────────────────────────────────────────────
def payload(spec):
    """spec: list of (id, tier, subcat, [scores]) -> a results payload."""
    obs = []
    for lid, tier, subcat, scores in spec:
        for i, sc in enumerate(scores):
            obs.append({
                "id": lid, "tier": tier, "repeat": i,
                "subcategory": subcat[i] if isinstance(subcat, list) else subcat,
                "expected_subcategory": subcat[0] if isinstance(subcat, list) else subcat,
                "rubric_version": "1.0",
                "overall_score": sc,
                "percentile": int(sc * 10),
                "dimension_scores": {"Form Specificity": sc, "Trust Signals": sc},
                "duration_s": 1.0, "tokens": 100,
            })
    return {"meta": {"mode": "scorer", "repeats": len(spec[0][3]), "total_tokens": 100},
            "observations": obs}


def render_quiet(p):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ok = report.render(p)
    return ok, buf.getvalue()

# A clean run: stable, consistent, well ordered.
ok, out = render_quiet(payload([
    ("weak-a", "weak", "Magnesium Glycinate", [2.0, 2.1, 1.9]),
    ("mod-a", "moderate", "Creatine Monohydrate", [5.0, 5.1, 4.9]),
    ("strong-a", "strong", "Vitamin C Serum", [8.0, 8.1, 7.9]),
]))
check("clean run passes every gate", ok is True)
check("clean run reports PASS verdict", "VERDICT: PASS" in out)

# An unstable scorer must fail.
ok, out = render_quiet(payload([
    ("weak-a", "weak", "Magnesium Glycinate", [1.0, 4.0, 2.0]),
    ("mod-a", "moderate", "Creatine Monohydrate", [5.0, 5.1, 4.9]),
    ("strong-a", "strong", "Vitamin C Serum", [8.0, 8.1, 7.9]),
]))
check("wide score spread fails", ok is False)
check("failure names instability", "unstable" in out.lower(), )

# Inverted tiers: perfectly stable, but useless. Must still fail.
ok, out = render_quiet(payload([
    ("weak-a", "weak", "Magnesium Glycinate", [8.0, 8.0, 8.0]),
    ("mod-a", "moderate", "Creatine Monohydrate", [5.0, 5.0, 5.0]),
    ("strong-a", "strong", "Vitamin C Serum", [2.0, 2.0, 2.0]),
]))
check("stable but inverted ranking still fails", ok is False)
check("failure names tier correlation", "correlation" in out.lower())

# Classification drift invalidates comparison even when scores look fine.
ok, out = render_quiet(payload([
    ("weak-a", "weak", ["Magnesium Glycinate", "Creatine Monohydrate", "Magnesium Glycinate"],
     [2.0, 2.1, 1.9]),
    ("mod-a", "moderate", "Creatine Monohydrate", [5.0, 5.1, 4.9]),
    ("strong-a", "strong", "Vitamin C Serum", [8.0, 8.1, 7.9]),
]))
check("classification drift fails", ok is False)
check("failure names drift", "drift" in out.lower())


# ── runner plumbing, against a stubbed model ─────────────────────
from pydantic import BaseModel
import agents.llm_client as lc


def sample(model, depth=0):
    vals = {}
    for name, f in model.model_fields.items():
        ann = f.annotation
        if typing.get_origin(ann) is list:
            (inner,) = typing.get_args(ann)
            if isinstance(inner, type) and issubclass(inner, BaseModel):
                vals[name] = [sample(inner, depth + 1)] if depth < 2 else []
            else:
                vals[name] = [inner("x") if inner is str else inner(1)]
        elif isinstance(ann, type) and issubclass(ann, BaseModel):
            vals[name] = sample(ann, depth + 1)
        elif ann is bool: vals[name] = True
        elif ann is int: vals[name] = 3
        elif ann is float: vals[name] = 5.0
        else: vals[name] = f"{name}-value"
    return model(**vals)


class _M:
    def __init__(self, p): self.parsed, self.refusal = p, None
class _C:
    def __init__(self, p): self.message = _M(p)
class _U:
    prompt_tokens, completion_tokens = 900, 400
class _Comp:
    def __init__(self, p): self.choices, self.usage = [_C(p)], _U()

CALLS = []
async def _parse(*, model, messages, response_format, **kw):
    CALLS.append(response_format.__name__)
    return _Comp(sample(response_format))

_client = types.SimpleNamespace(
    chat=types.SimpleNamespace(completions=types.SimpleNamespace(parse=_parse)))
lc._client = _client
lc.get_openai_client = lambda: _client

from evals import run_eval


async def _run_harness():
    tmp = pathlib.Path(tempfile.mkdtemp())
    run_eval.RESULTS_DIR = tmp
    args = argparse.Namespace(
        mode="scorer", repeats=3, listings=["weak-magnesium", "strong-magnesium"],
        concurrency=2, yes=True, analyze=None,
    )
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = await run_eval.run(args)
    written = list(tmp.glob("*.json"))
    return code, buf.getvalue(), written

code, out, written = asyncio.run(_run_harness())
check("runner completes against a stubbed model", code == 0, code)
check("results file written", len(written) == 1, [p.name for p in written])

saved = json.loads(written[0].read_text())
check("one observation per listing per repeat",
      len(saved["observations"]) == 6, len(saved["observations"]))
# Scorer mode must run the expensive setup stages ONCE per listing while the
# scorer repeats. Asserting the composition rather than a total, because the
# stub's unknown subcategory also triggers the LLM rubric-generation fallback.
scout_calls = CALLS.count("CompetitorScoutOut")
score_calls = CALLS.count("BenchmarkScoreOut")
check("setup runs once per listing", scout_calls == 2, scout_calls)
bench_calls = CALLS.count("ListingBatchScoresOut")
check("competitor benchmark measured once per listing, not per repeat",
      bench_calls == 2, bench_calls)
check("scorer runs once per repeat", score_calls == 6, score_calls)
check("scorer mode far cheaper than full mode",
      len(CALLS) < 2 * 3 * 8, f"{len(CALLS)} vs {2 * 3 * 8} for full mode")
check("observations carry tier and subcategory",
      all({"tier", "subcategory", "overall_score", "dimension_scores"} <= set(o)
          for o in saved["observations"]))
check("tokens recorded per observation",
      all(o["tokens"] > 0 for o in saved["observations"]))
check("report rendered after the run", "VERDICT:" in out)

# --analyze re-renders a saved file without re-running anything
before = len(CALLS)
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    run_eval.report_mod.render(saved)
check("--analyze path re-renders for free",
      "VERDICT:" in buf.getvalue() and len(CALLS) == before)

print()
print(f"{sum(results)}/{len(results)} checks passed")
print("EVAL HARNESS PASS" if all(results) else "EVAL HARNESS FAIL")
sys.exit(0 if all(results) else 1)
