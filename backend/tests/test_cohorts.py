"""
Two cohorts, one scoring call, and a headline number that says what it measured.

Once competitors can come from anywhere, pooling them into a single mean stops
measuring listing quality: a 200-character keyword-stacked marketplace title and
a brand site's 40-character product name are good listings by different rules,
and the average measures whichever house style dominated the search.

So the same scored rows are aggregated twice. The tests below pin the three
things that make that honest rather than merely more numbers: it costs no extra
LLM call, a cohort too small to mean anything is not used as the headline, and a
competitor whose page we failed to read is never scored as though it were a
badly written listing.
"""
import asyncio, os, pathlib, sys, tempfile, types

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_tmp = tempfile.TemporaryDirectory()
os.environ["AUTH_DB_PATH"] = str(pathlib.Path(_tmp.name) / "auth.db")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

import config
from models.schemas import (
    CompetitorBenchmarkSet, CompetitorListing, CompetitorScoreRow,
    CompetitorScoutResult, RubricDimension, ScoringRubric,
)

results = []
def check(label, passed, detail=""):
    results.append(passed)
    print(f"  {'ok  ' if passed else 'FAIL'} {label}{'  ' + str(detail) if detail else ''}")


RUBRIC = ScoringRubric(subcategory="X", version="1.0", dimensions=[
    RubricDimension(name="Form Specificity", weight=0.6, description="d", scoring_criteria="c"),
    RubricDimension(name="Trust Signals", weight=0.4, description="d", scoring_criteria="c"),
])


def listing(rank, platform, title=None, scoreable=True):
    return CompetitorListing(
        rank=rank, title=title or f"Brand{rank} Magnesium Glycinate {rank}00mg",
        bullet_points=["b1", "b2"], description="d" * 200,
        platform=platform, url=f"https://{platform}.example/p/{rank}",
        counts_toward_benchmark=scoreable)


def scout(listings, platform="amazon"):
    return CompetitorScoutResult(listings=listings, platform=platform,
                                 data_source="web_search")


def stub_scores(scores_by_rank):
    """A model that returns the given per-rank scores, counting its calls."""
    from models.llm_responses import (
        ListingBatchScoresOut, BatchScoreRowOut, BatchDimensionScoreOut as D)
    import agents.llm_client as lc

    calls = {"n": 0, "ids": []}
    planned = ListingBatchScoresOut(items=[
        BatchScoreRowOut(item_id=r, dimension_scores=[
            D(dimension="Form Specificity", score=s),
            D(dimension="Trust Signals", score=s)])
        for r, s in scores_by_rank.items()])

    class _M:
        def __init__(s_, p): s_.parsed, s_.refusal = p, None
    class _C:
        def __init__(s_, p): s_.message = _M(p)
    class _U:
        prompt_tokens, completion_tokens = 10, 5
    class _Comp:
        def __init__(s_, p): s_.choices, s_.usage = [_C(p)], _U()

    async def parse(**kw):
        calls["n"] += 1
        calls["ids"] = [l for l in kw["messages"][0]["content"].splitlines()
                        if l.startswith("LISTING")]
        return _Comp(planned)

    client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(parse=parse)))
    lc._client = client
    lc.get_openai_client = lambda: client
    return calls


async def main():
    from agents.competitor_scorer import score_competitor_cohorts, score_competitors
    from agents.benchmark_cohorts import aggregate, split_cohorts

    print("\nboth cohorts from one scoring call")
    config.BENCHMARK_MIN_COHORT = 4
    import agents.benchmark_cohorts as bc
    bc.BENCHMARK_MIN_COHORT = 4

    listings = ([listing(i, "amazon") for i in range(1, 6)]
                + [listing(6, "walmart"), listing(7, "dtc")])
    calls = stub_scores({1: 8.0, 2: 7.0, 3: 6.0, 4: 5.0, 5: 4.0, 6: 2.0, 7: 1.0})

    cohorts = await score_competitor_cohorts(scout(listings), RUBRIC)
    check("ONE model call produces both cohorts", calls["n"] == 1, calls["n"])

    same, every = cohorts.same_platform, cohorts.all_competitors
    check("the same-platform cohort holds only that platform",
          {r.platform for r in same.competitors} == {"amazon"},
          {r.platform for r in same.competitors})
    check("the category cohort holds every competitor", len(every.competitors) == 7)
    check("same-platform mean is its own average",
          same.overall_mean == 6.0, same.overall_mean)
    check("category mean is lower — the DTC pages score badly here",
          every.overall_mean < same.overall_mean, (every.overall_mean, same.overall_mean))
    check("each cohort names itself",
          same.cohort == "same_platform" and every.cohort == "all_competitors")
    check("each cohort lists its platforms",
          same.platforms == ["amazon"] and set(every.platforms) == {"amazon", "walmart", "dtc"})
    check("provenance travels to both",
          same.is_live_data and every.is_live_data and same.data_source == "web_search")

    print("\nthe headline says which cohort it used")
    check("a full same-platform cohort leads", cohorts.primary_cohort == "same_platform")
    check("primary resolves to the same-platform benchmark",
          cohorts.primary.overall_mean == same.overall_mean)
    check("no explanation is needed when nothing degraded", cohorts.note == "")

    thin = ([listing(1, "amazon"), listing(2, "amazon")]
            + [listing(i, "walmart") for i in range(3, 8)])
    stub_scores({i: 5.0 for i in range(1, 8)})
    tc = await score_competitor_cohorts(scout(thin), RUBRIC)
    check("a cohort below the floor does NOT lead",
          tc.primary_cohort == "all_competitors", tc.primary_cohort)
    check("the fallback explains itself in words a customer can read",
          "too few to benchmark" in tc.note, tc.note)
    check("the small cohort is still computed and available",
          len(tc.same_platform.competitors) == 2)
    check("primary now resolves to the category benchmark",
          tc.primary.cohort == "all_competitors")

    print("\nunreadable pages are shown but never scored")
    mixed = [listing(1, "amazon"), listing(2, "amazon"),
             listing(3, "amazon", scoreable=False),
             listing(4, "amazon"), listing(5, "amazon")]
    calls = stub_scores({1: 8.0, 2: 8.0, 4: 8.0, 5: 8.0})
    mc = await score_competitor_cohorts(scout(mixed), RUBRIC)
    check("an unreadable competitor is not sent to the scorer",
          len(calls["ids"]) == 4, len(calls["ids"]))
    check("it does not appear in the benchmark",
          len(mc.all_competitors.competitors) == 4)
    check("the mean is not dragged down by a page we failed to read",
          mc.all_competitors.overall_mean == 8.0, mc.all_competitors.overall_mean)
    check("n reports the real sample size",
          all(d.n == 4 for d in mc.all_competitors.dimensions),
          [d.n for d in mc.all_competitors.dimensions])

    none_readable = [listing(i, "amazon", scoreable=False) for i in range(1, 4)]
    calls = stub_scores({})
    nc = await score_competitor_cohorts(scout(none_readable), RUBRIC)
    check("nothing scoreable means NO model call at all", calls["n"] == 0, calls["n"])
    check("...and an empty benchmark, not a fabricated one",
          nc.all_competitors.competitors == [] and nc.all_competitors.overall_mean == 0.0)

    print("\naggregation is arithmetic, not estimation")
    rows = [CompetitorScoreRow(rank=1, platform="amazon", overall_score=8.0,
                               dimension_scores={"Form Specificity": 9.0, "Trust Signals": 3.0}),
            CompetitorScoreRow(rank=2, platform="amazon", overall_score=4.0,
                               dimension_scores={"Form Specificity": 5.0, "Trust Signals": 7.0})]
    agg = aggregate(rows, RUBRIC, cohort="all_competitors")
    fs = next(d for d in agg.dimensions if d.dimension == "Form Specificity")
    check("mean is the true average", fs.mean == 7.0, fs.mean)
    check("best and worst are real values", fs.best == 9.0 and fs.worst == 5.0)
    check("a dimension nobody was scored on is absent, not zero",
          all(d.dimension in ("Form Specificity", "Trust Signals") for d in agg.dimensions))
    check("an empty cohort does not divide by zero",
          aggregate([], RUBRIC, cohort="same_platform").overall_mean == 0.0)

    print("\nregional platforms fold together")
    uk = [listing(i, "amazon") for i in range(1, 6)]
    stub_scores({i: 6.0 for i in range(1, 6)})
    uc = await score_competitor_cohorts(scout(uk, platform="amazon_uk"), RUBRIC)
    check("an amazon_uk seller is benchmarked against Amazon listings",
          len(uc.same_platform.competitors) == 5, len(uc.same_platform.competitors))
    check("...and that cohort leads", uc.primary_cohort == "same_platform")

    print("\nback-compatible single-benchmark caller")
    stub_scores({i: 5.0 for i in range(1, 8)})
    one = await score_competitors(scout(listings), RUBRIC)
    check("score_competitors still returns one CompetitorBenchmark",
          one.cohort == "all_competitors" and len(one.competitors) == 7)

    print("\nthe listing score reports its basis")
    from agents.benchmark_scorer import score_listing
    from models.schemas import (
        CompetitorAnalysis, ExtractedEntities, ListingAnalysis, ParsedListing)
    from models.llm_responses import BenchmarkScoreOut, DimensionScoreOut

    import agents.llm_client as lc
    planned = BenchmarkScoreOut(dimension_scores=[
        DimensionScoreOut(dimension="Form Specificity", weight=0.6, score=7.0,
                          explanation="e", strengths=[], weaknesses=[]),
        DimensionScoreOut(dimension="Trust Signals", weight=0.4, score=7.0,
                          explanation="e", strengths=[], weaknesses=[])])
    class _M:
        def __init__(s_, p): s_.parsed, s_.refusal = p, None
    class _C:
        def __init__(s_, p): s_.message = _M(p)
    class _U:
        prompt_tokens, completion_tokens = 10, 5
    class _Comp:
        def __init__(s_, p): s_.choices, s_.usage = [_C(p)], _U()
    async def parse(**kw): return _Comp(planned)
    client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(parse=parse)))
    lc._client = client
    lc.get_openai_client = lambda: client

    parsed = ParsedListing(original_title="t", original_description="d", brand_name="b",
                           platform="amazon", extracted_entities=ExtractedEntities())
    score = await score_listing(ListingAnalysis(), CompetitorAnalysis(), RUBRIC, parsed,
                                same, wide_benchmark=every)
    check("the headline percentile names its cohort",
          score.percentile_basis == "same_platform", score.percentile_basis)
    check("the cohort size is reported", score.percentile_cohort_n == 5,
          score.percentile_cohort_n)
    check("a category percentile is reported too", score.category_cohort_n == 7)
    check("beating weaker cross-platform competitors gives a higher category percentile",
          score.category_percentile >= score.percentile,
          (score.percentile, score.category_percentile))
    check("both percentiles are counted, not guessed",
          score.percentile == same.percentile_for(score.overall_score)
          and score.category_percentile == every.percentile_for(score.overall_score))

    solo = await score_listing(ListingAnalysis(), CompetitorAnalysis(), RUBRIC, parsed, same)
    check("omitting the wide benchmark does not crash or invent one",
          solo.category_cohort_n == len(same.competitors))

    print()
    print(f"{sum(results)}/{len(results)} checks passed")
    print("COHORTS PASS" if all(results) else "COHORTS FAIL")
    return 0 if all(results) else 1


sys.exit(asyncio.run(main()))
