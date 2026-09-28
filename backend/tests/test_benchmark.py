"""
The competitive benchmark must be MEASURED, not estimated.

Before the competitor scorer existed, the model was asked "what would the
average top-10 competitor score?" and that guess became the benchmark. These
tests pin down the replacement: competitor averages, gaps and percentiles are
all computed in Python from the competitors' own scores.
"""
import asyncio, os, pathlib, sys, tempfile, types

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_tmp = tempfile.TemporaryDirectory()
os.environ["AUTH_DB_PATH"] = str(pathlib.Path(_tmp.name) / "auth.db")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

import providers
from providers.llm import LLMProvider
from models.schemas import (
    LIVE_DATA_SOURCES,
    CompetitorBenchmarkSet,
    CompetitorScoutResult,
    CompetitorBenchmark, CompetitorDimensionStat, CompetitorListing,
    CompetitorScoreRow, CompetitorScoutResult, RubricDimension, ScoringRubric,
)

results = []
def check(label, passed, detail=""):
    results.append(passed)
    print(f"  {'ok  ' if passed else 'FAIL'} {label}{'  ' + str(detail) if detail else ''}")


RUBRIC = ScoringRubric(subcategory="Magnesium Glycinate", version="1.0", dimensions=[
    RubricDimension(name="Form Specificity", weight=0.6, description="d", scoring_criteria="c"),
    RubricDimension(name="Trust Signals", weight=0.4, description="d", scoring_criteria="c"),
])

SCOUT = CompetitorScoutResult(
    listings=[CompetitorListing(rank=i, title=f"T{i}", brand_name=f"B{i}", rating=4.5)
              for i in (1, 2, 3)],
    search_query="q", platform="amazon", data_source="rainforest_api")


async def main():
    import agents.llm_client as lc
    from agents.competitor_scorer import score_competitors
    from providers import benchmark_cache

    # ── Aggregation is arithmetic, not opinion ───────────────────
    from models.llm_responses import (
        ListingBatchScoresOut, BatchScoreRowOut, BatchDimensionScoreOut as D)

    planned = ListingBatchScoresOut(items=[
        BatchScoreRowOut(item_id=1, dimension_scores=[
            D(dimension="Form Specificity", score=8.0), D(dimension="Trust Signals", score=6.0)]),
        BatchScoreRowOut(item_id=2, dimension_scores=[
            D(dimension="Form Specificity", score=4.0), D(dimension="Trust Signals", score=2.0)]),
        BatchScoreRowOut(item_id=3, dimension_scores=[
            # An invented dimension name must be ignored, not averaged in.
            D(dimension="Form Specificity", score=6.0), D(dimension="Trust Signals", score=4.0),
            D(dimension="Made Up Dimension", score=10.0)]),
    ])

    class _M:
        def __init__(s_, p): s_.parsed, s_.refusal = p, None
    class _C:
        def __init__(s_, p): s_.message = _M(p)
    class _U:
        prompt_tokens, completion_tokens = 100, 50
    class _Comp:
        def __init__(s_, p): s_.choices, s_.usage = [_C(p)], _U()

    async def parse(**kw):
        return _Comp(planned)
    client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(parse=parse)))
    lc._client = client
    lc.get_openai_client = lambda: client

    bm = await score_competitors(SCOUT, RUBRIC)

    check("every competitor scored", len(bm.competitors) == 3, len(bm.competitors))
    check("Form Specificity mean is the real average (8+4+6)/3",
          bm.mean_for("Form Specificity") == 6.0, bm.mean_for("Form Specificity"))
    check("Trust Signals mean is the real average (6+2+4)/3",
          bm.mean_for("Trust Signals") == 4.0, bm.mean_for("Trust Signals"))
    fs = next(d for d in bm.dimensions if d.dimension == "Form Specificity")
    check("best/worst captured", (fs.best, fs.worst, fs.n) == (8.0, 4.0, 3), (fs.best, fs.worst, fs.n))
    check("invented dimension names discarded",
          {d.dimension for d in bm.dimensions} == {"Form Specificity", "Trust Signals"},
          [d.dimension for d in bm.dimensions])

    # Weighted overall uses the same weights the user's listing gets.
    top = next(c for c in bm.competitors if c.rank == 1)
    check("competitor overall uses rubric weights (8*.6 + 6*.4)",
          top.overall_score == 7.2, top.overall_score)
    check("benchmark overall_mean is the mean of those",
          bm.overall_mean == round((7.2 + 3.2 + 5.2) / 3, 2), bm.overall_mean)

    # ── Percentile is counted, not guessed ───────────────────────
    check("score above all competitors -> 100", bm.percentile_for(9.9) == 100)
    check("score below all competitors -> 0", bm.percentile_for(0.5) == 0)
    check("score beating 1 of 3 -> 33", bm.percentile_for(4.0) == 33, bm.percentile_for(4.0))
    check("exact tie counts as half", bm.percentile_for(7.2) == 83, bm.percentile_for(7.2))
    check("empty benchmark -> 0, not a crash", CompetitorBenchmark().percentile_for(5.0) == 0)

    # ── The scorer consumes measured values ──────────────────────
    from agents.benchmark_scorer import score_listing
    from models.llm_responses import BenchmarkScoreOut, DimensionScoreOut
    from models.schemas import CompetitorAnalysis, ListingAnalysis, ParsedListing, ExtractedEntities

    check("LLM is no longer asked for competitor_avg",
          "competitor_avg" not in DimensionScoreOut.model_fields)
    check("LLM is no longer asked for percentile",
          "percentile" not in BenchmarkScoreOut.model_fields)

    user_scores = BenchmarkScoreOut(dimension_scores=[
        DimensionScoreOut(dimension="Form Specificity", weight=0.6, score=2.0,
                          explanation="e", strengths=[], weaknesses=[]),
        DimensionScoreOut(dimension="Trust Signals", weight=0.4, score=1.0,
                          explanation="e", strengths=[], weaknesses=[]),
    ])
    async def parse2(**kw):
        return _Comp(user_scores)
    client.chat.completions.parse = parse2

    parsed = ParsedListing(original_title="t", original_description="", original_bullets=[],
                           brand_name="Mine", platform="amazon",
                           extracted_entities=ExtractedEntities())
    score = await score_listing(
        ListingAnalysis(), CompetitorAnalysis(), RUBRIC, parsed, bm)

    fs_score = next(d for d in score.dimension_scores if d.dimension == "Form Specificity")
    check("competitor_avg comes from the measured benchmark",
          fs_score.competitor_avg == 6.0, fs_score.competitor_avg)
    check("gap is measured_avg - user_score", fs_score.gap == 4.0, fs_score.gap)
    check("percentile measured against real competitor scores",
          score.percentile == bm.percentile_for(score.overall_score),
          (score.percentile, score.overall_score))
    check("a weak listing lands at the bottom", score.percentile == 0, score.percentile)

    # A dimension the benchmark never measured must yield a zero gap, never an
    # invented one.
    sparse = CompetitorBenchmark(dimensions=[
        CompetitorDimensionStat(dimension="Trust Signals", mean=4.0, best=6.0, worst=2.0, n=3)],
        competitors=[CompetitorScoreRow(rank=1, overall_score=5.0)])
    score2 = await score_listing(ListingAnalysis(), CompetitorAnalysis(), RUBRIC, parsed, sparse)
    unmeasured = next(d for d in score2.dimension_scores if d.dimension == "Form Specificity")
    check("unmeasured dimension gets a zero gap, not a fabricated one",
          unmeasured.gap == 0.0 and unmeasured.competitor_avg == unmeasured.score,
          (unmeasured.competitor_avg, unmeasured.gap))

    # ── Cache keys on the rubric, so editing criteria invalidates ──
    # Both cohorts are stored as one payload: they come from a single scoring
    # call, and a half-populated pair would be worse than no cache.
    SET = CompetitorBenchmarkSet(same_platform=bm, all_competitors=bm)
    await benchmark_cache.put("amazon", "Magnesium Glycinate", RUBRIC, SET)
    check("benchmark cached", await benchmark_cache.get("amazon", "Magnesium Glycinate", RUBRIC) is not None)

    edited = ScoringRubric(subcategory="Magnesium Glycinate", version="1.0", dimensions=[
        RubricDimension(name="Form Specificity", weight=0.6, description="d",
                        scoring_criteria="DIFFERENT criteria"),
        RubricDimension(name="Trust Signals", weight=0.4, description="d", scoring_criteria="c"),
    ])
    check("editing scoring_criteria invalidates the cached benchmark",
          await benchmark_cache.get("amazon", "Magnesium Glycinate", edited) is None)
    check("empty benchmark is never cached",
          (await benchmark_cache.put("amazon", "Empty", RUBRIC, CompetitorBenchmarkSet()),
           await benchmark_cache.get("amazon", "Empty", RUBRIC))[1] is None)

    # The competitor set is part of the identity. Web discovery can return a
    # different set for the same subcategory, and serving a benchmark computed
    # from one set as though it described another silently corrupts every gap.
    fp_a = benchmark_cache.competitor_set_fingerprint(SCOUT)
    other = SCOUT.model_copy(update={"listings": SCOUT.listings[:1]})
    fp_b = benchmark_cache.competitor_set_fingerprint(other)
    check("a different competitor set is a different key", fp_a != fp_b)
    check("the same set fingerprints identically",
          fp_a == benchmark_cache.competitor_set_fingerprint(SCOUT))
    await benchmark_cache.put("amazon", "Sets", RUBRIC, SET, fp_a)
    check("a benchmark is served only for the set it was computed from",
          await benchmark_cache.get("amazon", "Sets", RUBRIC, fp_a) is not None
          and await benchmark_cache.get("amazon", "Sets", RUBRIC, fp_b) is None)

    # ── Estimated benchmarks must not be cached either ────────────
    # The listing cache refused estimated data, but the benchmark *computed
    # from* that data was cached happily and then served for the rest of the
    # TTL as though it had been measured against real competitors.
    estimated = bm.model_copy(update={"data_source": "llm_knowledge", "is_live_data": False})
    await benchmark_cache.put("amazon", "Estimated", RUBRIC,
                              CompetitorBenchmarkSet(same_platform=estimated,
                                                     all_competitors=estimated))
    check("a benchmark built from ESTIMATED competitors is never cached",
          await benchmark_cache.get("amazon", "Estimated", RUBRIC) is None)

    check("a measured benchmark carries its provenance",
          bm.is_live_data is True and bm.data_source == "rainforest_api",
          (bm.data_source, bm.is_live_data))

    # ── is_live_data is an allowlist, so it fails closed ──────────
    def live(ds):
        return CompetitorScoutResult(listings=[], data_source=ds).is_live_data

    check("observed sources are live", live("rainforest_api") and live("web_search"))
    check("estimates are not live", live("llm_knowledge") is False)
    check("an UNREGISTERED source is treated as estimated, not live",
          live("some_new_provider") is False)
    check("an empty source is not live", live("") is False)
    check("every registered provider is either live or the estimator",
          all(cls.name in LIVE_DATA_SOURCES or cls.name == LLMProvider.name
              for cls in providers._PROVIDERS.values()),
          {k: v.name for k, v in providers._PROVIDERS.items()})

    print()
    print(f"{sum(results)}/{len(results)} checks passed")
    print("BENCHMARK PASS" if all(results) else "BENCHMARK FAIL")
    return 0 if all(results) else 1


sys.exit(asyncio.run(main()))
