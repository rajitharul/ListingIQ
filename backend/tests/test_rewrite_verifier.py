"""
Rewrite scores must be MEASURED, not self-reported.

`expected_score` is the generator grading its own output, and it was the basis
of the product's strongest claim ("takes you from 2.9 to 9.2"). These tests pin
down that variants are re-scored through the same batch scorer used on the
competitors, and that an optimistic projection stays visible instead of being
presented as a result.
"""
import asyncio, os, pathlib, sys, tempfile, types

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_tmp = tempfile.TemporaryDirectory()
os.environ["AUTH_DB_PATH"] = str(pathlib.Path(_tmp.name) / "auth.db")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

from models.schemas import (
    CompetitorBenchmark, CompetitorScoreRow, ListingRewrite, RewriteResult,
    RubricDimension, ScoringRubric,
)

results = []
def check(label, passed, detail=""):
    results.append(passed)
    print(f"  {'ok  ' if passed else 'FAIL'} {label}{'  ' + str(detail) if detail else ''}")


RUBRIC = ScoringRubric(subcategory="X", version="1.0", dimensions=[
    RubricDimension(name="Form Specificity", weight=0.6, description="d", scoring_criteria="c"),
    RubricDimension(name="Trust Signals", weight=0.4, description="d", scoring_criteria="c"),
])

BENCHMARK = CompetitorBenchmark(
    competitors=[CompetitorScoreRow(rank=i, overall_score=s)
                 for i, s in enumerate([4.0, 5.0, 6.0, 7.0], start=1)],
    overall_mean=5.5)


def variant(name, expected):
    return ListingRewrite(variant_name=name, strategy="s", title=f"{name} title",
                          bullet_points=["b1", "b2"], description="d",
                          expected_score=expected, key_changes=["c"])


async def main():
    import agents.llm_client as lc
    from agents.rewrite_verifier import verify_rewrites
    from models.llm_responses import (
        ListingBatchScoresOut, BatchScoreRowOut, BatchDimensionScoreOut as D)

    # The generator claims 9.2 / 8.8 / 8.0; the scorer measures much lower.
    planned = ListingBatchScoresOut(items=[
        BatchScoreRowOut(item_id=0, dimension_scores=[
            D(dimension="Form Specificity", score=7.0), D(dimension="Trust Signals", score=6.0)]),
        BatchScoreRowOut(item_id=1, dimension_scores=[
            D(dimension="Form Specificity", score=5.0), D(dimension="Trust Signals", score=5.0)]),
        BatchScoreRowOut(item_id=2, dimension_scores=[
            D(dimension="Form Specificity", score=3.0), D(dimension="Trust Signals", score=2.0)]),
    ])

    class _M:
        def __init__(s_, p): s_.parsed, s_.refusal = p, None
    class _C:
        def __init__(s_, p): s_.message = _M(p)
    class _U:
        prompt_tokens, completion_tokens = 100, 50
    class _Comp:
        def __init__(s_, p): s_.choices, s_.usage = [_C(p)], _U()

    calls = {"n": 0}
    async def parse(**kw):
        calls["n"] += 1
        return _Comp(planned)
    client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(parse=parse)))
    lc._client = client
    lc.get_openai_client = lambda: client

    rewrites = RewriteResult(
        variants=[variant("keyword-optimized", 9.2), variant("benefit-led", 8.8),
                  variant("trust-forward", 8.0)],
        original_score=2.9, best_variant_score=9.2)

    out = await verify_rewrites(rewrites, RUBRIC, BENCHMARK)

    check("all variants scored in ONE call", calls["n"] == 1, calls["n"])
    check("every variant marked verified", all(v.is_verified for v in out.variants))
    check("scores_verified flag set", out.scores_verified is True)

    v0 = out.variants[0]
    check("measured score uses rubric weights (7*.6 + 6*.4)",
          v0.measured_score == 6.6, v0.measured_score)
    check("the generator's projection is preserved for comparison",
          v0.expected_score == 9.2, v0.expected_score)
    check("measured score replaces the projection as the headline",
          out.best_variant_score == 6.6, out.best_variant_score)
    check("optimism is visible: projected 9.2 vs measured 6.6",
          abs((v0.expected_score - v0.measured_score) - 2.6) < 1e-9)

    check("per-dimension measured scores retained",
          v0.measured_dimension_scores == {"Form Specificity": 7.0, "Trust Signals": 6.0},
          v0.measured_dimension_scores)

    # Percentile against the same measured competitor set (4,5,6,7).
    check("percentile measured against the real competitors",
          v0.measured_percentile == BENCHMARK.percentile_for(6.6), v0.measured_percentile)
    check("a 6.6 beats 3 of 4 competitors -> 75", v0.measured_percentile == 75,
          v0.measured_percentile)

    # Worst variant scored 2.6 — below every competitor.
    worst = out.variants[2]
    check("a bad rewrite is reported as bad, not as its 8.0 claim",
          worst.measured_score == 2.6 and worst.measured_percentile == 0,
          (worst.measured_score, worst.measured_percentile))

    # ── Unscored variants stay honest ────────────────────────────
    partial = ListingBatchScoresOut(items=[
        BatchScoreRowOut(item_id=0, dimension_scores=[
            D(dimension="Form Specificity", score=8.0), D(dimension="Trust Signals", score=8.0)]),
        # item 1 missing entirely, plus an id that does not exist
        BatchScoreRowOut(item_id=99, dimension_scores=[
            D(dimension="Form Specificity", score=10.0), D(dimension="Trust Signals", score=10.0)]),
    ])
    async def parse2(**kw):
        return _Comp(partial)
    client.chat.completions.parse = parse2

    out2 = await verify_rewrites(
        RewriteResult(variants=[variant("a", 9.0), variant("b", 9.0)],
                      original_score=1.0, best_variant_score=9.0),
        RUBRIC, BENCHMARK)
    check("scored variant is verified", out2.variants[0].is_verified)
    check("unscored variant is NOT marked verified", out2.variants[1].is_verified is False)
    check("unscored variant has no fabricated measured score",
          out2.variants[1].measured_score == 0.0)
    check("an invented item id cannot become a variant score",
          out2.variants[0].measured_score == 8.0, out2.variants[0].measured_score)

    # ── Nothing to verify ────────────────────────────────────────
    empty = await verify_rewrites(RewriteResult(), RUBRIC, BENCHMARK)
    check("no variants -> unchanged, no crash", empty.variants == [] and not empty.scores_verified)

    print()
    print(f"{sum(results)}/{len(results)} checks passed")
    print("REWRITE VERIFIER PASS" if all(results) else "REWRITE VERIFIER FAIL")
    return 0 if all(results) else 1


sys.exit(asyncio.run(main()))
