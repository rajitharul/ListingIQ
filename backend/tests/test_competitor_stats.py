"""
Competitive statistics must be COUNTED, not estimated.

These numbers reach customers as evidence ("8/10 top competitors include this"),
so they have to be arithmetic over the real listing text. Pure functions, so
this suite costs nothing.
"""
import pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agents.competitor_stats import (
    brand_key, contains_phrase, count_keyword, dedupe_by_brand,
    emoji_count, structural_patterns, tally_by_rank,
)
from models.schemas import CompetitorListing

results = []
def check(label, passed, detail=""):
    results.append(passed)
    print(f"  {'ok  ' if passed else 'FAIL'} {label}{'  ' + str(detail) if detail else ''}")


def L(rank, title, bullets=(), desc="", brand="", rating=4.5, reviews=100):
    return CompetitorListing(rank=rank, title=title, bullet_points=list(bullets),
                             description=desc, brand_name=brand, rating=rating,
                             review_count=reviews)


# ── Phrase matching ──────────────────────────────────────────────
check("exact phrase matches", contains_phrase("Magnesium Glycinate 400mg", "magnesium glycinate"))
check("matching is case-insensitive", contains_phrase("THIRD-PARTY TESTED", "third-party tested"))
check("whitespace/layout is collapsed", contains_phrase("third-party\n  tested", "third-party tested"))
check("substrings do NOT count — 'mag' is not 'magnesium'",
      not contains_phrase("magnesium glycinate", "mag"))
check("partial word at the end does not count",
      not contains_phrase("testing the waters", "tested"))
check("empty phrase never matches", not contains_phrase("anything", "   "))

# ── Keyword counting ─────────────────────────────────────────────
listings = [
    L(1, "Magnesium Glycinate 400mg", ["Third-party tested", "Vegan"], "Chelated form."),
    L(2, "Magnesium Glycinate Capsules", ["Vegan friendly"], ""),
    L(3, "Magnesium Citrate", ["Third-party tested"], "Third-party tested in the USA."),
]
freq, pos = count_keyword(listings, "magnesium glycinate")
check("counts listings, not occurrences", freq == 2, freq)
check("position is where it most often appears", pos == "title", pos)

freq, pos = count_keyword(listings, "third-party tested")
check("counted across bullets and description", freq == 2, freq)
check("a listing mentioning it twice still counts once", freq == 2, freq)
check("position resolves to bullets", pos == "bullets", pos)
check("absent keyword counts zero", count_keyword(listings, "creatine")[0] == 0)

# ── Attribution tallies ──────────────────────────────────────────
freq, brands = tally_by_rank(listings, [1, 3])
check("frequency is the size of the attribution", freq == 2, freq)
check("brands resolved from ranks", len(brands) == 2, brands)
check("duplicate ranks counted once", tally_by_rank(listings, [1, 1, 1])[0] == 1)
check("unknown ranks cannot inflate past the sample",
      tally_by_rank(listings, [1, 2, 3, 99, 100])[0] == 3)
check("empty attribution is zero", tally_by_rank(listings, [])[0] == 0)

# ── Structural statistics ────────────────────────────────────────
s = structural_patterns([
    L(1, "A" * 100, ["b1", "b2"], "desc here"),
    L(2, "B" * 50, ["b1"], ""),
])
check("avg_title_length is exact ((100+50)/2)", s["avg_title_length"] == 75, s["avg_title_length"])
check("min/max title length reported", (s["min_title_length"], s["max_title_length"]) == (50, 100))
check("avg_bullet_count is exact ((2+1)/2)", s["avg_bullet_count"] == 1.5, s["avg_bullet_count"])
check("description average excludes listings with none",
      s["avg_description_length"] == len("desc here"), s["avg_description_length"])
check("listings_with_description reported so zeros are not mistaken for short copy",
      s["listings_with_description"] == 1, s["listings_with_description"])
check("empty input returns {} rather than dividing by zero", structural_patterns([]) == {})

check("emoji detected in bullets", emoji_count("Great product ✅🔥") == 2)
check("plain text has no emoji", emoji_count("Great product") == 0)
s2 = structural_patterns([L(1, "t", ["✅ tested"]), L(2, "t", ["plain"])])
check("emoji_usage counts listings, not emoji", s2["emoji_usage"] == 1, s2["emoji_usage"])

s3 = structural_patterns([L(1, "t", rating=4.0, reviews=10), L(2, "t", rating=5.0, reviews=90)])
check("avg_rating computed", s3["avg_rating"] == 4.5, s3["avg_rating"])
check("median review count computed", s3["median_review_count"] == 90, s3["median_review_count"])

# ── Brand dedupe ─────────────────────────────────────────────────
check("brand key taken from the leading words",
      brand_key("Optimum Nutrition Micronized Creatine 300g") == "optimum nutrition micronized")
check("punctuation ignored in the brand key",
      brand_key("Nature's Bounty, High Absorption") == brand_key("Natures Bounty High absorption"))

variants = [
    {"title": "Optimum Nutrition Micronized Creatine 300g"},
    {"title": "Optimum Nutrition Micronized Creatine 600g"},
    {"title": "Optimum Nutrition Micronized Creatine Unflavored"},
    {"title": "Thorne Creatine Powder"},
    {"title": "Nutricost Creatine Monohydrate"},
]
deduped = dedupe_by_brand(variants)
check("same-brand variants collapse to one", len(deduped) == 3, [d["title"] for d in deduped])
check("the best-ranked variant is kept",
      deduped[0]["title"].endswith("300g"), deduped[0]["title"])
check("order is preserved", [d["title"].split()[0] for d in deduped] == ["Optimum", "Thorne", "Nutricost"])
check("limit respected", len(dedupe_by_brand(variants, limit=2)) == 2)
check("untitled items skipped", dedupe_by_brand([{"title": ""}, {"title": "Thorne X Y"}]) ==
      [{"title": "Thorne X Y"}])

# ── The model is no longer asked for arithmetic ──────────────────
from models.llm_responses import CompetitorAnalysisOut, KeywordPatternOut, ClaimPatternOut
check("keywords carry no model-supplied frequency",
      "frequency" not in KeywordPatternOut.model_fields)
check("claims carry attribution, not a count",
      "competitor_ranks" in ClaimPatternOut.model_fields
      and "frequency" not in ClaimPatternOut.model_fields)
check("structural statistics removed from model output",
      "structural_patterns" not in CompetitorAnalysisOut.model_fields)

# ── Figures we could not see must not be averaged as zeros ──────
# A competitor found through an open-web search has no rating and no review
# count. Dividing by the full cohort would report "competitors average 2.3
# stars" when the truth is that half of them could not be read — and that
# number is quoted back to the customer by the recommendation engine.
print("\nunobserved figures")

_mixed = [
    CompetitorListing(rank=1, title="A", rating=4.5, review_count=1200, price="$20"),
    CompetitorListing(rank=2, title="B", rating=4.7, review_count=800, price="$25"),
    CompetitorListing(rank=3, title="C"),
    CompetitorListing(rank=4, title="D"),
]
_sp = structural_patterns(_mixed)
check("rating averages only listings that have one",
      _sp["avg_rating"] == 4.6, _sp["avg_rating"])
check("how many had a rating is reported alongside",
      _sp["listings_with_rating"] == 2 and _sp["listings_counted"] == 4)
check("median reviews ignores listings with none",
      _sp["median_review_count"] == 1200, _sp["median_review_count"])
check("how many had a price is reported", _sp["listings_with_price"] == 2)
check("a cohort with no ratings at all reports 0.0, not a crash",
      structural_patterns([CompetitorListing(rank=1, title="X")])["avg_rating"] == 0.0)

# ── Frequencies are measured over what we could read ────────────
# Counting across competitors whose pages never loaded measures our extraction
# failures, not the market: "1 of 10 mention third-party testing" reads as a
# market gap when six of the nine we could not read may well mention it. It also
# made the denominators disagree — counts over ten printed beside a benchmark
# averaged over three.
print("\nonly readable competitors are analysed")

import asyncio as _asyncio, types as _types
from models.schemas import CompetitorScoutResult, ScoringRubric, RubricDimension
from models.llm_responses import (
    CompetitorAnalysisOut, KeywordPatternOut, ClaimPatternOut, TrustSignalOut)
import agents.llm_client as _lc
from agents.competitor_analyzer import analyze_competitors

_readable = CompetitorListing(rank=1, title="BrandA Magnesium Glycinate High Absorption",
                              bullet_points=["High absorption chelated form"],
                              description="d" * 200, counts_toward_benchmark=True)
_unread = CompetitorListing(rank=2, title="BrandB Magnesium Glycinate",
                            counts_toward_benchmark=False)

_planned = CompetitorAnalysisOut(
    keyword_patterns=[KeywordPatternOut(keyword="Magnesium Glycinate", position="title")],
    claim_patterns=[ClaimPatternOut(claim="High Absorption", competitor_ranks=[1])],
    trust_signals=[TrustSignalOut(signal="Third-party testing", competitor_ranks=[1])],
    common_title_format="brand first", differentiation_insights=["i"], summary="s")

class _M:
    def __init__(s_, p): s_.parsed, s_.refusal = p, None
class _C:
    def __init__(s_, p): s_.message = _M(p)
class _U:
    prompt_tokens, completion_tokens = 10, 5
class _Comp:
    def __init__(s_, p): s_.choices, s_.usage = [_C(p)], _U()

_seen = {}
async def _parse(**kw):
    _seen["prompt"] = kw["messages"][0]["content"]
    return _Comp(_planned)
_client = _types.SimpleNamespace(
    chat=_types.SimpleNamespace(completions=_types.SimpleNamespace(parse=_parse)))
_lc._client = _client
_lc.get_openai_client = lambda: _client

_rubric = ScoringRubric(subcategory="X", version="1.0", dimensions=[
    RubricDimension(name="D", weight=1.0, description="d", scoring_criteria="c")])
_scout = CompetitorScoutResult(listings=[_readable, _unread], data_source="web_search")
_out = _asyncio.run(analyze_competitors(_scout, _rubric))

check("an unreadable competitor is not sent to the model",
      "BrandB" not in _seen["prompt"])
check("the denominator is what we analysed, not what we found",
      _out.structural_patterns["listings_counted"] == 1,
      _out.structural_patterns["listings_counted"])
check("a keyword frequency cannot exceed the analysed set",
      all(k.frequency <= 1 for k in _out.keyword_patterns),
      [(k.keyword, k.frequency) for k in _out.keyword_patterns])

_none = CompetitorScoutResult(listings=[_unread], data_source="web_search")
_empty = _asyncio.run(analyze_competitors(_none, _rubric))
check("nothing readable yields no fabricated patterns",
      _empty.keyword_patterns == [] and _empty.claim_patterns == [])
check("...and says so plainly", "could be read in full" in _empty.summary, _empty.summary)

print()
print(f"{sum(results)}/{len(results)} checks passed")
print("COMPETITOR STATS PASS" if all(results) else "COMPETITOR STATS FAIL")
sys.exit(0 if all(results) else 1)
