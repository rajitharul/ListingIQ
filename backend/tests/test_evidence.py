"""
Counts quoted to a customer must be counted, including inside prose.

The recommendation engine asked the model for a sentence of "competitive
evidence", with the field description literally suggesting
"8/10 top competitors include this". Against a set of three readable
competitors it duly produced "8/10 top competitors highlight bioavailability" —
a fabricated statistic, printed in the customer's report as market evidence, in
a product whose entire premise is that its numbers are measured.

The model now names *which* pattern justifies a recommendation; Python supplies
the frequency, or says nothing at all.
"""
import asyncio, os, pathlib, sys, tempfile, types

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_tmp = tempfile.TemporaryDirectory()
os.environ["AUTH_DB_PATH"] = str(pathlib.Path(_tmp.name) / "auth.db")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

from models.schemas import (
    RubricDimension, ScoringRubric,
    ClaimPattern, CompetitorAnalysis, DimensionScore, KeywordPattern,
    ListingScore, ParsedListing, ExtractedEntities,
)

results = []
def check(label, passed, detail=""):
    results.append(passed)
    print(f"  {'ok  ' if passed else 'FAIL'} {label}{'  ' + str(detail) if detail else ''}")


ANALYSIS = CompetitorAnalysis(
    keyword_patterns=[KeywordPattern(keyword="High Absorption", frequency=5, position="title")],
    claim_patterns=[ClaimPattern(claim="Third-Party Tested", frequency=2, example_brand="Thorne")],
    trust_signals=[{"signal": "GMP certified", "frequency": 3}],
    structural_patterns={"listings_counted": 8},
    summary="s",
)

SCORES = ListingScore(overall_score=3.2, dimension_scores=[
    DimensionScore(dimension="Bioavailability Claims", weight=0.1, score=0.0,
                   explanation="e", competitor_avg=6.3, gap=6.3)])

PARSED = ParsedListing(original_title="t", original_description="d", brand_name="b",
                       platform="amazon", extracted_entities=ExtractedEntities())

RUBRIC = ScoringRubric(subcategory="X", version="1.0", dimensions=[
    RubricDimension(name="Bioavailability Claims", weight=1.0,
                    description="d", scoring_criteria="c")])


def stub(recs):
    from models.llm_responses import RecommendationResultOut
    import agents.llm_client as lc

    class _M:
        def __init__(s_, p): s_.parsed, s_.refusal = p, None
    class _C:
        def __init__(s_, p): s_.message = _M(p)
    class _U:
        prompt_tokens, completion_tokens = 10, 5
    class _Comp:
        def __init__(s_, p): s_.choices, s_.usage = [_C(p)], _U()

    seen = {}
    async def parse(**kw):
        seen["prompt"] = kw["messages"][0]["content"]
        return _Comp(RecommendationResultOut(
            recommendations=recs, quick_wins=[], strategic_moves=[]))
    client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(parse=parse)))
    lc._client = client
    lc.get_openai_client = lambda: client
    return seen


async def main():
    from agents.recommendation_engine import generate_recommendations
    from models.llm_responses import RecommendationOut

    def rec(pattern):
        return RecommendationOut(
            priority=1, dimension="Bioavailability Claims", current_score=0.0,
            projected_score=7.0, impact="high", specific_copy="c",
            evidence_pattern=pattern, expected_lift="+7.0")

    print("\nthe model attributes, Python counts")
    seen = stub([rec("High Absorption")])
    out = await generate_recommendations(SCORES, ANALYSIS, PARSED, RUBRIC)
    ev = out.recommendations[0].competitive_evidence

    check("a real keyword yields a counted sentence",
          ev == "5 of 8 analysed competitors use 'High Absorption'", ev)
    check("the number is the measured frequency, not the model's", "5 of 8" in ev)

    seen = stub([rec("Third-Party Tested")])
    out = await generate_recommendations(SCORES, ANALYSIS, PARSED, RUBRIC)
    check("a claim resolves too",
          out.recommendations[0].competitive_evidence
          == "2 of 8 analysed competitors make the claim 'Third-Party Tested'",
          out.recommendations[0].competitive_evidence)

    seen = stub([rec("gmp certified")])
    out = await generate_recommendations(SCORES, ANALYSIS, PARSED, RUBRIC)
    check("a trust signal resolves, case-insensitively",
          "3 of 8" in out.recommendations[0].competitive_evidence,
          out.recommendations[0].competitive_evidence)

    print("\nunverifiable attribution produces silence, not a guess")
    for invented in ["Clinically Proven Superiority", "", "   "]:
        stub([rec(invented)])
        out = await generate_recommendations(SCORES, ANALYSIS, PARSED, RUBRIC)
        check(f"a pattern we never counted yields no evidence ({invented!r})",
              out.recommendations[0].competitive_evidence == "",
              repr(out.recommendations[0].competitive_evidence))

    zero = ANALYSIS.model_copy(update={
        "keyword_patterns": [KeywordPattern(keyword="High Absorption", frequency=0,
                                            position="title")]})
    stub([rec("High Absorption")])
    out = await generate_recommendations(SCORES, zero, PARSED, RUBRIC)
    check("a zero frequency is not reported as evidence",
          out.recommendations[0].competitive_evidence == "")

    print("\nthe model is told not to write counts")
    stub([rec("High Absorption")])
    seen = stub([rec("High Absorption")])
    await generate_recommendations(SCORES, ANALYSIS, PARSED, RUBRIC)
    prompt = seen["prompt"]
    check("the prompt forbids stating a count", "do NOT state any count" in prompt)
    check("the prompt asks for a verbatim pattern", "copied verbatim" in prompt.lower()
          or "verbatim" in prompt)

    print("\nthe response model no longer invites a fabricated statistic")
    from models.llm_responses import RecommendationOut as RO
    check("competitive_evidence is not a model field",
          "competitive_evidence" not in RO.model_fields, list(RO.model_fields))
    check("evidence_pattern replaces it", "evidence_pattern" in RO.model_fields)
    desc = RO.model_fields["evidence_pattern"].description or ""
    check("its description does not suggest writing '8/10'", "8/10" not in desc, desc[:60])

    print()
    print(f"{sum(results)}/{len(results)} checks passed")
    print("EVIDENCE PASS" if all(results) else "EVIDENCE FAIL")
    return 0 if all(results) else 1


sys.exit(asyncio.run(main()))
