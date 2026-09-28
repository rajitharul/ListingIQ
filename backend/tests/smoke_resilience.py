"""
Offline smoke test for the resilience layer.

Stubs chat.completions.parse so the full LangGraph pipeline runs without
touching the OpenAI API, then exercises retry, exhaustion, and clamping.
"""
import asyncio, os, pathlib, sys, types, typing
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-a-real-key")
os.environ["LLM_RETRY_BASE_DELAY"] = "0.01"
os.environ["LLM_RETRY_MAX_DELAY"] = "0.02"

from pydantic import BaseModel
import agents.llm_client as lc


def sample(model: type[BaseModel], depth=0):
    """Build a plausible instance of any response model from its annotations."""
    vals = {}
    for name, f in model.model_fields.items():
        ann = f.annotation
        origin = typing.get_origin(ann)
        if origin is list:
            (inner,) = typing.get_args(ann)
            if isinstance(inner, type) and issubclass(inner, BaseModel):
                vals[name] = [sample(inner, depth + 1)] if depth < 2 else []
            else:
                vals[name] = [inner("x") if inner is str else inner(1)]
        elif isinstance(ann, type) and issubclass(ann, BaseModel):
            vals[name] = sample(ann, depth + 1)
        elif ann is bool:
            vals[name] = True
        elif ann is int:
            # Deliberately out of range where a range exists, to prove clamping.
            vals[name] = 250 if name == "percentile" else 3
        elif ann is float:
            vals[name] = 99.0            # every float field is over its max
        else:
            vals[name] = f"{name}-value"
    return model(**vals)


class FakeMessage:
    def __init__(self, parsed): self.parsed, self.refusal = parsed, None
class FakeChoice:
    def __init__(self, parsed): self.message = FakeMessage(parsed)
class FakeUsage:
    prompt_tokens, completion_tokens = 1234, 567
class FakeCompletion:
    def __init__(self, parsed): self.choices, self.usage = [FakeChoice(parsed)], FakeUsage()


CALLS = []

def install_fake(fail_times=0, exc=None):
    """Patch the client so parse() fails `fail_times` then returns a sample."""
    state = {"n": 0}
    async def parse(*, model, messages, response_format, **kw):
        CALLS.append(response_format.__name__)
        state["n"] += 1
        if state["n"] <= fail_times:
            raise exc
        return FakeCompletion(sample(response_format))
    client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(parse=parse))
    )
    lc._client = client
    lc.get_openai_client = lambda: client
    return state


async def main():
    from openai import APIConnectionError
    import httpx
    ok = True

    # ── 1. Full pipeline end-to-end ──────────────────────────────
    install_fake()
    CALLS.clear()
    from agents.orchestrator import run_full_pipeline
    from models.schemas import ListingInput
    lc.start_usage_tracking()
    resp = await run_full_pipeline(
        ListingInput(
            product_title="Magnesium 500mg 120 Capsules",
            product_description="Magnesium supplement capsules.",
            bullet_points=["500mg per capsule", "Easy to swallow"],
            brand_name="HealthPlus", platform="amazon",
        ),
        session_id="smoke",
    )
    print(f"  pipeline ran: {len(CALLS)} LLM calls -> {CALLS}")
    usage = lc.get_usage()
    print(f"  usage ledger: {len(usage.calls)} calls, {usage.total_tokens} tokens")
    assert len(usage.calls) == len(CALLS), "usage ledger missed calls"

    # ── 2. Clamping of out-of-range model output ─────────────────
    ds = resp.scores.dimension_scores[0]
    checks = [
        ("dimension score <= 10", ds.score <= 10.0, ds.score),
        ("competitor_avg <= 10", ds.competitor_avg <= 10.0, ds.competitor_avg),
        ("gap is derived (avg - score)", ds.gap == round(ds.competitor_avg - ds.score, 2), ds.gap),
        ("percentile clamped to <= 100", resp.scores.percentile <= 100, resp.scores.percentile),
        ("confidence clamped to <= 1", resp.category.confidence <= 1.0, resp.category.confidence),
        ("completeness clamped to <= 1", resp.listing_analysis.dimensions[0].completeness <= 1.0,
         resp.listing_analysis.dimensions[0].completeness),
        ("rating clamped to <= 5", resp.competitors.listings[0].rating <= 5.0,
         resp.competitors.listings[0].rating),
        ("rewrite score clamped to <= 10", resp.rewrites.variants[0].expected_score <= 10.0,
         resp.rewrites.variants[0].expected_score),
    ]
    for label, passed, val in checks:
        print(f"  {'ok  ' if passed else 'FAIL'} {label}: {val}")
        ok &= passed

    # Frequencies are now derived from attribution, so a stub that attributes to
    # a rank no competitor has must yield nothing rather than a phantom count.
    ts = resp.competitor_analysis.trust_signals
    passed = all(set(t) >= {"signal", "frequency", "brands"} for t in ts)
    print(f"  {'ok  ' if passed else 'FAIL'} trust_signal rows carry counted frequency + brands: {ts}")
    ok &= passed
    passed = all(t["frequency"] <= len(resp.competitors.listings) for t in ts)
    print(f"  {'ok  ' if passed else 'FAIL'} no frequency exceeds the competitor count")
    ok &= passed

    # Structural statistics are computed in Python, so they are present for any
    # competitor set regardless of what the model returned.
    sp = resp.competitor_analysis.structural_patterns
    expected = {"avg_title_length", "avg_bullet_count", "avg_description_length",
                "listings_with_description", "emoji_usage", "listings_counted"}
    passed = expected <= set(sp)
    print(f"  {'ok  ' if passed else 'FAIL'} structural stats computed in Python: {sorted(sp)}")
    ok &= passed
    passed = sp.get("listings_counted") == len(resp.competitors.listings)
    print(f"  {'ok  ' if passed else 'FAIL'} listings_counted matches the real competitor count")
    ok &= passed

    # ── 3. Retry then succeed ────────────────────────────────────
    err = APIConnectionError(request=httpx.Request("POST", "https://api.openai.com/v1"))
    install_fake(fail_times=2, exc=err)
    from models.llm_responses import CategoryClassificationOut
    lc.start_usage_tracking()
    out = await lc.structured_completion(
        response_model=CategoryClassificationOut,
        messages=[{"role": "user", "content": "hi"}],
        caller="smoke.retry", temperature=0.1, max_completion_tokens=100,
    )
    attempts = lc.get_usage().calls[0].attempts
    passed = attempts == 3
    print(f"  {'ok  ' if passed else 'FAIL'} recovered after 2 transient failures (attempts={attempts})")
    ok &= passed

    # ── 4. Exhaust retries -> LLMCallError ───────────────────────
    install_fake(fail_times=99, exc=err)
    try:
        await lc.structured_completion(
            response_model=CategoryClassificationOut,
            messages=[{"role": "user", "content": "hi"}],
            caller="smoke.exhaust", temperature=0.1, max_completion_tokens=100,
        )
        print("  FAIL expected LLMCallError, got a result")
        ok = False
    except lc.LLMCallError as e:
        passed = e.caller == "smoke.exhaust" and e.attempts == 3
        print(f"  {'ok  ' if passed else 'FAIL'} LLMCallError raised: {e}")
        ok &= passed

    print()
    print("SMOKE PASS" if ok else "SMOKE FAIL")
    return 0 if ok else 1


sys.exit(asyncio.run(main()))
