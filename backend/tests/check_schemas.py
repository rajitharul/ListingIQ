"""Verify every LLM response model compiles to a valid OpenAI strict JSON schema."""
import pathlib, sys, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from openai.lib._pydantic import to_strict_json_schema
import models.llm_responses as M
from pydantic import BaseModel

# Discovered, not listed. A hand-maintained list silently skips any model added
# later — which is the one case this check exists to catch.
targets = sorted(
    (obj for name, obj in vars(M).items()
     if isinstance(obj, type) and issubclass(obj, BaseModel)
     and obj is not BaseModel and obj.__module__ == M.__name__),
    key=lambda m: m.__name__,
)

# Every model the pipeline passes as `response_model` must be among them.
REQUIRED = {
    "ExtractedEntitiesOut", "CategoryClassificationOut", "GeneratedRubricOut",
    "CompetitorScoutOut", "CompetitorAnalysisOut", "ListingAnalysisOut",
    "BenchmarkScoreOut", "RecommendationResultOut", "RewriteResultOut",
    "ListingBatchScoresOut", "ExtractedPagesOut",
}
missing = REQUIRED - {m.__name__ for m in targets}
if missing:
    print(f"  FAIL expected response models not found: {sorted(missing)}")
    sys.exit(1)
UNSUPPORTED = {
    "minimum","maximum","exclusiveMinimum","exclusiveMaximum","multipleOf",
    "minLength","maxLength","pattern","format","minItems","maxItems",
    "uniqueItems","default","allOf","not","oneOf",
}

def walk(node, path, problems):
    if isinstance(node, dict):
        for k in UNSUPPORTED & node.keys():
            problems.append(f"{path}: unsupported keyword '{k}' = {node[k]!r}")
        if node.get("type") == "object":
            if node.get("additionalProperties") is not False:
                problems.append(f"{path}: additionalProperties must be false")
            props = set(node.get("properties", {}))
            req = set(node.get("required", []))
            if props != req:
                problems.append(f"{path}: required != properties (missing {sorted(props - req)})")
        for k, v in node.items():
            walk(v, f"{path}.{k}", problems)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            walk(v, f"{path}[{i}]", problems)

failed = 0
for m in targets:
    try:
        schema = to_strict_json_schema(m)
    except Exception as e:
        print(f"  FAIL {m.__name__}: schema generation raised {type(e).__name__}: {e}")
        failed += 1
        continue
    problems = []
    walk(schema, m.__name__, problems)
    size = len(json.dumps(schema))
    if problems:
        failed += 1
        print(f"  FAIL {m.__name__} ({size}b)")
        for p in problems:
            print(f"       - {p}")
    else:
        print(f"  ok   {m.__name__:28s} {size:>6}b")

print()
print("FAILED" if failed else
      f"All {len(targets)} response models produce valid strict schemas.")
sys.exit(1 if failed else 0)
