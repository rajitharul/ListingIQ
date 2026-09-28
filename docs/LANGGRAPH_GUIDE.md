# LangGraph, taught through ListingIQ

A ground-up guide to LangGraph, using this project's own code as the running example.
Read it top to bottom the first time; use Part 15 (the mapping table) as a quick reference later.

---

## Part 0 — The one-paragraph mental model

LangGraph lets you build an application as a **graph**: a set of **nodes** (functions)
connected by **edges** (arrows), all sharing one **state** object that flows through them.
Each node receives the current state, does some work, and returns a *partial* update that
gets merged back into the state. The graph engine decides which node runs next based on the
edges. That's it. Everything else — streaming, persistence, branching, parallelism,
human-in-the-loop — is built on those three primitives: **state, nodes, edges.**

`backend/agents/orchestrator.py` is a textbook example of exactly this.

---

## Part 1 — Why LangGraph exists (and why not just call functions?)

Our pipeline is 8 steps run in order. We could write:

```python
parsed = await parse_listing(inp)
category, rubric = await classify_category(parsed)
competitors = await scout(category, rubric)
# ... 5 more lines
```

That works. So why does LangGraph exist? Because as soon as you want any of these, plain
function calls get painful:

1. **Streaming progress** — "tell the UI when each step finishes." (We do this — the SSE endpoint.)
2. **Branching** — "if confidence is low, take a different path."
3. **Loops** — "keep calling the tool until the LLM is satisfied" (agent loops).
4. **Parallelism** — "run these two independent steps at once, then merge."
5. **Persistence / resume** — "save progress so I can pause, crash, or wait for a human, then continue."
6. **Observability** — "trace every step's timing, inputs, outputs" (our LangSmith wrapping + logging).

LangGraph gives you all of that *for free* once you express your app as a graph. The cost is a
bit of ceremony (defining state, registering nodes/edges). This project pays that ceremony and
currently uses maybe 40% of the payoff — mostly streaming and observability. The rest of this
guide shows the other 60%.

> **LangGraph vs LangChain:** LangChain is about *chains* — linear-ish pipelines of LLM calls
> (`prompt | model | parser`). LangGraph is the lower-level, more powerful sibling for *cyclic,
> stateful, multi-actor* workflows. LangChain "chains" can't loop or hold branching state cleanly;
> LangGraph can. They interoperate (you can call LangChain objects inside LangGraph nodes), but
> they're separate libraries.

---

## Part 2 — The State (the single most important concept)

### 2.1 What it is in our code

```python
# backend/agents/graph_state.py
class ListingIQState(TypedDict, total=False):
    listing_input: ListingInput
    session_id: str
    parsed_listing: ParsedListing
    category: CategoryClassification
    rubric: ScoringRubric
    competitor_scout_result: CompetitorScoutResult
    # ... one key per agent output
```

The **state** is the shared memory of the whole graph. In this project it's a `TypedDict` — a
dictionary with a declared shape. Every node reads keys from it and writes keys back.

Two important details in our definition:

- **`TypedDict`** — this is just a type hint. At runtime it's a plain `dict`. LangGraph uses the
  annotations to know what keys exist and (as you'll see) how to merge them.
- **`total=False`** — this means *every key is optional*. That's essential here: at the START,
  only `listing_input` and `session_id` exist. `parsed_listing` doesn't exist until Agent 1
  produces it. Without `total=False`, the type checker would demand all keys always be present.

### 2.2 The golden rule of nodes: return a *partial* update, not the whole state

Look at the end of `input_parser_node`:

```python
return {"parsed_listing": result}
```

It returns a dict with **only the key it produced**. It does *not* return the whole state.
LangGraph takes this partial dict and **merges** it into the running state.

> A node returns `{"some_key": value}`. LangGraph does `state["some_key"] = value` for you.
> Keys you don't mention are left untouched.

### 2.3 Reducers — how merging actually works (not used here yet, but must understand)

By default, when a node returns `{"parsed_listing": X}`, LangGraph **overwrites**
`state["parsed_listing"]` with `X`. That's the default reducer: "last write wins."

But sometimes you want **accumulation** instead of overwrite. The classic case is a chat message
list — each node *appends* messages, doesn't replace them. You control this with `Annotated` and a
**reducer function**:

```python
from typing import Annotated, TypedDict
import operator

class ChatState(TypedDict):
    current_step: str                          # default: overwrite
    messages: Annotated[list, operator.add]    # reducer: concatenate lists
```

Now if node A returns `{"messages": [msg1]}` and node B returns `{"messages": [msg2]}`, the final
`messages` is `[msg1, msg2]` — they're **added**, not overwritten.

LangGraph ships a smarter reducer for messages specifically:

```python
from langgraph.graph.message import add_messages

class ChatState(TypedDict):
    messages: Annotated[list, add_messages]
```

`add_messages` appends *and* de-duplicates by message ID and handles updates — it's what nearly
every chatbot/agent example uses.

**Why this matters here:** reducers are the *exact* thing that would have fixed the
parallel-execution bug (see Part 7).

### 2.4 State schemas can be Pydantic, not just TypedDict

We use `TypedDict`. LangGraph also accepts a **Pydantic `BaseModel`** as the state schema, which
gives you runtime validation:

```python
from pydantic import BaseModel

class MyState(BaseModel):
    count: int = 0
    name: str = ""
```

Trade-off: Pydantic validates on every update (safer, slower). `TypedDict` is zero-overhead but no
runtime checks. This project keeps *state* as `TypedDict` and uses Pydantic for the *values inside*
(`ParsedListing`, `ScoringRubric`, etc.). Good pattern.

---

## Part 3 — Nodes

### 3.1 What a node is

A node is **any callable that takes the state and returns a partial update.** Our nodes are
`async` functions:

```python
async def input_parser_node(state: dict) -> dict:
    li = state["listing_input"]          # read from state
    result = await parse_listing(li)     # do work
    return {"parsed_listing": result}    # write partial update
```

Good patterns in our implementation:

1. **Thin wrapper over real logic.** `input_parser_node` is just glue: read state → call
   `parse_listing()` (the real function) → return update. The business logic lives in a plain
   function independent of LangGraph. You could rip out LangGraph and `parse_listing()` still works.

2. **Defensive dict/model coercion:**
   ```python
   listing_input = ListingInput(**li) if isinstance(li, dict) else li
   ```
   This appears in every node. Why? Because when state is **serialized** (e.g., by a checkpointer,
   or across a stream boundary), Pydantic models can come back as plain dicts. This coercion makes
   nodes robust to both.

3. **Logging on ENTER/EXIT with timings** — poor-man's observability, complementing LangSmith.

### 3.2 The node signature variations

Our nodes take just `(state)`. LangGraph also lets a node take a second argument, `config`, to
access runtime configuration:

```python
async def my_node(state: MyState, config: RunnableConfig) -> dict:
    thread_id = config["configurable"]["thread_id"]
    user_id = config["configurable"].get("user_id")
    ...
```

This is how a node reads per-run settings (like which user, which thread) without them being part
of graph state. You pass these at invoke time:

```python
graph.invoke(state, config={"configurable": {"thread_id": "abc", "user_id": "u42"}})
```

`run_full_pipeline` already passes `config={"configurable": {"thread_id": session_id}}` — we just
don't read it inside nodes yet.

### 3.3 A node can be a class, a lambda, or a LangChain runnable

Anything callable works. In agent-style graphs you'll often see prebuilt nodes like `ToolNode`
(Part 9).

---

## Part 4 — Edges (control flow)

Edges define **what runs next**. `build_listingiq_graph()` uses only the simplest kind.

### 4.1 Normal (static) edges

```python
graph.add_edge(START, "input_parser")
graph.add_edge("input_parser", "category_classifier")
...
graph.add_edge("rewrite_generator", END)
```

`add_edge("a", "b")` means "after `a` finishes, run `b`." Unconditional. `START` and `END` are
special sentinel nodes:

- `START` — the virtual entry point. `add_edge(START, "input_parser")` says the graph begins there.
- `END` — the virtual exit. `add_edge("rewrite_generator", END)` says the graph stops after it.

Our entire topology is a straight line: `START → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → END`. Simple and
reliable.

> Older API you might see in tutorials: `graph.set_entry_point("x")` == `add_edge(START, "x")`, and
> `graph.set_finish_point("y")` == `add_edge("y", END)`. Both still work; the `START`/`END` form is
> preferred now.

### 4.2 Conditional edges (branching) — the heart of "agentic" behavior

A **conditional edge** runs a router function that inspects state and returns the *name* of the
next node:

```python
def route_after_classify(state: ListingIQState) -> str:
    if state["category"].confidence < 0.5:
        return "human_review"      # low confidence → ask a human
    return "competitor_scout"      # confident → continue

graph.add_conditional_edges(
    "category_classifier",         # source node
    route_after_classify,          # router: state -> next node name
    {                              # optional: map return values to nodes
        "human_review": "human_review",
        "competitor_scout": "competitor_scout",
    },
)
```

The router returns a string (or a list of strings — see fan-out below). The third argument maps
those strings to actual node names; if your router already returns real node names you can omit it.

**Concrete idea for this project:** right now, if `category_classifier` is only 30% confident, we
barrel ahead scoring against a possibly-wrong rubric. A conditional edge could route low-confidence
classifications to a rubric-regeneration node or a human check.

### 4.3 Loops — the thing linear scripts fundamentally cannot do

Because edges can point *backward*, graphs can cycle. This is how tool-calling agents work:

```python
def should_continue(state) -> str:
    last = state["messages"][-1]
    if last.tool_calls:          # LLM wants to call a tool
        return "tools"
    return END                   # LLM gave final answer

graph.add_edge(START, "agent")
graph.add_conditional_edges("agent", should_continue)
graph.add_edge("tools", "agent")   # ← loop back! tools → agent → tools → ...
```

This runs `agent → tools → agent → tools → …` until the LLM stops requesting tools. You **cannot**
write this cleanly with sequential `await` calls. This cyclic capability is *the* reason LangGraph
exists.

To prevent infinite loops, LangGraph enforces a **recursion limit** (default 25 steps). Override it
via config: `config={"recursion_limit": 100}`.

---

## Part 5 — Compiling and running

### 5.1 Build vs compile

```python
graph = StateGraph(ListingIQState)   # a mutable builder
# ... add_node, add_edge ...
compiled = graph.compile()           # frozen, runnable object
```

`StateGraph(...)` gives you a **builder** you mutate with `add_node`/`add_edge`. `.compile()`
validates the graph (checks for orphan nodes, unreachable states, bad edges) and returns an
immutable **`CompiledStateGraph`** that you actually run. `get_compiled_graph()` caches this
compiled object in a module global so we compile once:

```python
_compiled_graph = None
def get_compiled_graph(checkpointer=None):
    global _compiled_graph
    if _compiled_graph is None or checkpointer is not None:
        g = build_listingiq_graph()
        _compiled_graph = g.compile(checkpointer=checkpointer)
    return _compiled_graph
```

(Minor note: the `or checkpointer is not None` means passing a checkpointer always recompiles —
fine for our usage, but be aware it bypasses the cache.)

### 5.2 The four ways to run a compiled graph

| Method | Sync/Async | Returns | Our usage |
|---|---|---|---|
| `.invoke(state, config)` | sync | final state (all keys) | — |
| `.ainvoke(state, config)` | async | final state | `run_full_pipeline` |
| `.stream(state, config)` | sync | iterator of updates | — |
| `.astream(state, config)` | async | async iterator of updates | `/api/pipeline/stream` |

**`ainvoke`** (our non-streaming path) runs the whole graph and hands you the final accumulated
state:

```python
result = await graph.ainvoke(initial_state, config=config)
# result is the full ListingIQState with ALL keys populated
return FullPipelineResponse(
    parsed_listing=result["parsed_listing"],
    category=result["category"],
    ...
)
```

**`astream`** (our streaming path) yields *as each node finishes* — see next section.

---

## Part 6 — Streaming (we use this heavily)

### 6.1 Our streaming loop

```python
async for event in graph.astream(initial_state, config=config, stream_mode="updates"):
    for node_name, node_output in event.items():
        if node_name == "__start__":
            continue
        accumulated.update(node_output)      # merge into our own dict
        yield {"event": "node_complete", "data": ...}   # push to browser via SSE
```

### 6.2 `stream_mode` — the crucial knob

`astream` can emit *different shapes* of data depending on `stream_mode`:

- **`"updates"`** (what we use): after each node, emit `{node_name: partial_update}` — *only what
  changed*. Perfect for "step N done" progress. That's why our loop does `event.items()` and gets
  `{"input_parser": {"parsed_listing": ...}}`.

- **`"values"`**: after each node, emit the *entire accumulated state*. Heavier, but you don't need
  to accumulate yourself. With this we wouldn't need our manual `accumulated.update(...)`.

- **`"messages"`**: streams **LLM tokens** as they're generated, node by node. This is how you get
  a ChatGPT-style typewriter effect. Emits tuples of `(token, metadata)`.

- **`"custom"`**: streams arbitrary data you emit from inside a node via a `StreamWriter`. Great for
  "45% done — analyzing dimension 3 of 8" sub-progress.

- **`"debug"`**: everything, verbose, for debugging.

You can combine them: `stream_mode=["updates", "messages"]` yields tagged tuples so you get both
step-progress *and* token streaming.

**Practical upgrade:** our UI shows "step done" bumps. If we surfaced tokens
(`stream_mode=["updates","messages"]`), we could show the rewrite variants *typing out live*.

### 6.3 Why we manually accumulate

Because we chose `"updates"` (deltas only), we maintain our own `accumulated` dict and
`accumulated.update(node_output)` each step, then build `FullPipelineResponse` at the end. Correct.
Alternatively, `ainvoke` already returns the full accumulated state — which is why the
*non-streaming* path doesn't need manual accumulation. Two paths, same destination.

---

## Part 7 — Parallelism, and the bug this project hit

`CLAUDE.md` and `orchestrator.py` both say: *"We tried parallel fan-out and it caused LangGraph
barrier join bugs / KeyError / duplicate execution. Don't re-introduce parallelism without thorough
testing."* Here's exactly what happened and how it's *properly* fixed.

### 7.1 How fan-out/fan-in is supposed to work

If one node has edges to *two* nodes, both downstream nodes run **in parallel** in the same
"superstep":

```python
graph.add_edge("category_classifier", "competitor_scout")
graph.add_edge("category_classifier", "listing_analyzer")   # fan-out: both run
graph.add_edge("competitor_scout", "benchmark_scorer")
graph.add_edge("listing_analyzer", "benchmark_scorer")       # fan-in: barrier join
```

`benchmark_scorer` waits for **both** upstream nodes (a "barrier join"), then runs once. LangGraph
executes in **supersteps** (BSP model): all nodes in a wave run, their updates are collected,
merged, then the next wave fires.

### 7.2 Why it broke

The failure almost certainly came from **two parallel nodes writing the same state key without a
reducer**, or from a downstream node reading a key that didn't exist yet. When two concurrent nodes
both return `{"some_key": ...}`, LangGraph sees two competing writes to one key in the same
superstep and — with the default "overwrite" reducer — raises `InvalidUpdateError` ("can receive
only one value per step"). That's the "barrier join bug."

### 7.3 The correct fix: reducers (not "give up and go sequential")

The *intended* solution is to give any concurrently-written key a reducer so LangGraph knows how to
merge two writes:

```python
from typing import Annotated
import operator

class ListingIQState(TypedDict, total=False):
    findings: Annotated[list, operator.add]   # parallel branches can both append
```

If each parallel branch writes a **different** key (scout → `competitor_scout_result`, analyzer →
`listing_analysis`), there's *no* conflict and no reducer is needed — that configuration is safe.
The comment in `orchestrator.py` notes this: *"listing_analyzer only reads parsed_listing + rubric …
so ordering is safe."* That suggests the branches wrote distinct keys, so the real culprit was
likely a **fan-in node reading a key before its producer ran**, or a duplicated edge causing a node
to fire twice.

**Honest take:** going sequential was a *reasonable* engineering call — 60s total runtime is fine,
and sequential is trivial to reason about. But the "right" fix is understood: distinct output keys
per branch + reducers on any shared key. `competitor_scout` and `listing_analyzer` are genuinely
independent (they read only Agent-2 outputs), so they're the natural candidates to parallelize if
we ever want to shave ~15–20s. If revisited, do it on a branch with logging and test the fan-in
carefully.

---

## Part 8 — Persistence, checkpointers, threads, and memory

The biggest capability we've *wired for but not used.* `get_compiled_graph(checkpointer=None)`
accepts a checkpointer, and we pass `config={"configurable": {"thread_id": session_id}}`. Both are
the persistence machinery — currently no-ops because `checkpointer` is `None`.

### 8.1 What a checkpointer does

A **checkpointer** saves the graph's state after *every* superstep, keyed by `thread_id`. This
unlocks:

1. **Resume after crash** — restart from the last completed node instead of from scratch.
2. **Conversation memory** — a `thread_id` = a conversation; re-invoking with the same thread
   continues where it left off, with full history.
3. **Human-in-the-loop** — pause mid-graph, wait (minutes or days), resume.
4. **Time travel** — inspect or rewind to any past checkpoint.

### 8.2 The checkpointers

```python
from langgraph.checkpoint.memory import MemorySaver          # in-RAM, dev only
from langgraph.checkpoint.sqlite import SqliteSaver          # sync SQLite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver # async SQLite
from langgraph.checkpoint.postgres import PostgresSaver      # production
```

Since our app is `async` and already uses SQLite (`scoring_history.py`), the natural fit is
`AsyncSqliteSaver`:

```python
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

async with AsyncSqliteSaver.from_conn_string("data/checkpoints.db") as saver:
    graph = build_listingiq_graph().compile(checkpointer=saver)
    result = await graph.ainvoke(state, config={"configurable": {"thread_id": session_id}})
```

Now the run's every step is persisted under that `thread_id`.

### 8.3 Threads = our `session_id`

Our `session_id` → `thread_id` mapping is *exactly* the right idea, just not persisted yet. With a
checkpointer wired in, calling the pipeline again with the same `session_id` would let us build
features like "re-run just the rewrite step" or "resume a pipeline that failed at agent 6" —
because the first 5 agents' outputs are already checkpointed.

### 8.4 Reading state back

```python
snapshot = await graph.aget_state(config)     # current state for a thread
history = [s async for s in graph.aget_state_history(config)]  # every checkpoint
```

---

## Part 9 — Human-in-the-loop and interrupts

Built directly on checkpointers. Two flavors:

### 9.1 Static interrupts — pause at a node boundary

```python
graph = builder.compile(
    checkpointer=saver,
    interrupt_before=["rewrite_generator"],   # stop right before this node
)

await graph.ainvoke(state, config)            # pauses before rewrite_generator
# ... a human reviews the recommendations, maybe edits state ...
await graph.aupdate_state(config, {"recommendations": edited})
await graph.ainvoke(None, config)             # resume by invoking with None
```

### 9.2 Dynamic interrupts — pause *inside* a node with `interrupt()`

The modern approach. Inside a node:

```python
from langgraph.types import interrupt, Command

async def approval_node(state):
    decision = interrupt({"question": "Approve these rewrites?", "rewrites": state["rewrites"]})
    # execution literally suspends here until you resume
    if decision == "approve":
        return {"approved": True}
    return {"approved": False}
```

Resume by passing a `Command`:

```python
await graph.ainvoke(Command(resume="approve"), config)
```

**For this product:** a "review before publishing the optimized listing" gate is the obvious use —
pause after `rewrite_generator`, let the user tweak a variant, then persist. The `thread_id`
plumbing already exists; you'd only need a checkpointer + an interrupt.

---

## Part 10 — Prebuilt agents (`create_react_agent`, `ToolNode`)

Everything above is building a graph *by hand*, which is right for a fixed pipeline. For the *other*
major LangGraph use case — a tool-calling agent that loops — there are prebuilt shortcuts. This
project doesn't use them, but you should recognize them because most LangGraph tutorials are about
this:

```python
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI

def get_weather(city: str) -> str:
    """Get weather for a city."""
    return f"It's sunny in {city}."

agent = create_react_agent(model=ChatOpenAI(model="gpt-4o"), tools=[get_weather])
result = agent.invoke({"messages": [("user", "What's the weather in Paris?")]})
```

`create_react_agent` builds the exact loop from Part 4.3 for you: an LLM node + a `ToolNode` + the
conditional edge that loops until the model stops calling tools. It's the "just give me a working
agent" button.

`ToolNode` is the reusable node that executes whatever tools the LLM requested and appends results
to `messages` (using the `add_messages` reducer).

Our pipeline is a **fixed workflow**, not an autonomous agent, so hand-building the graph is the
correct choice. Rule of thumb: **fixed steps → build the graph yourself; open-ended "figure out
what to do" → `create_react_agent`.**

---

## Part 11 — `Command` — combine an update and a route in one return

A node can return a `Command` to *both* update state *and* decide where to go next, replacing a
separate conditional edge:

```python
from langgraph.types import Command
from typing import Literal

async def category_classifier_node(state) -> Command[Literal["competitor_scout", "human_review"]]:
    classification, rubric = await classify_category(state["parsed_listing"])
    goto = "human_review" if classification.confidence < 0.5 else "competitor_scout"
    return Command(
        update={"category": classification, "rubric": rubric},  # state update
        goto=goto,                                              # routing
    )
```

Handy when the routing decision depends on data the node just computed — no need for a separate
router function to recompute it.

---

## Part 12 — Error handling and retries

Our nodes make live OpenAI calls, so this is directly relevant. LangGraph supports per-node **retry
policies**:

```python
from langgraph.types import RetryPolicy   # (older: from langgraph.pregel import RetryPolicy)

graph.add_node(
    "competitor_scout",
    competitor_scout_node,
    retry=RetryPolicy(max_attempts=3, initial_interval=1.0, backoff_factor=2.0),
)
```

Now a transient OpenAI 429/500 in that node retries with exponential backoff instead of failing the
whole pipeline. Our streaming endpoint currently catches exceptions at the *graph* level
(`try/except` around `astream`) and emits an `error` event — good for surfacing failures, but a
`RetryPolicy` would prevent many of them from ever surfacing. Low-risk, high-value addition for a
pipeline that makes 8+ network calls.

---

## Part 13 — Subgraphs (composition at scale)

A compiled graph can be used as a **node inside another graph**:

```python
competitor_subgraph = build_competitor_graph().compile()   # scout + analyzer as a unit
main_graph.add_node("competitor_intel", competitor_subgraph)
```

The subgraph shares state keys with the parent (or you map them explicitly). Useful when a chunk of
the pipeline becomes reusable across products/verticals. Not needed at current size, but it's the
escape hatch when a single flat graph gets unwieldy.

---

## Part 14 — A complete, runnable mini-example (all concepts in ~40 lines)

Self-contained graph exercising **state + reducer + node + conditional edge + loop + checkpointer**:

```python
from typing import Annotated, TypedDict
import operator
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

class State(TypedDict):
    count: int
    log: Annotated[list[str], operator.add]   # reducer: accumulate

def increment(state: State) -> dict:
    return {"count": state["count"] + 1, "log": [f"incremented to {state['count']+1}"]}

def route(state: State) -> str:              # conditional edge / loop condition
    return "increment" if state["count"] < 3 else END

builder = StateGraph(State)
builder.add_node("increment", increment)
builder.add_edge(START, "increment")
builder.add_conditional_edges("increment", route)   # loops back or ends

graph = builder.compile(checkpointer=MemorySaver())

cfg = {"configurable": {"thread_id": "demo"}}
print(graph.invoke({"count": 0, "log": []}, cfg))
# {'count': 3, 'log': ['incremented to 1', 'incremented to 2', 'incremented to 3']}
```

Note how `count` gets **overwritten** each step (default reducer) while `log` **accumulates**
(`operator.add` reducer) — the two behaviors side by side.

---

## Part 15 — Mapping every concept back to our code

| LangGraph concept | Where it lives in ListingIQ | Status |
|---|---|---|
| **State schema** | `ListingIQState` (TypedDict, `total=False`) | used |
| **Nodes** | `*_node` functions in `agents/` | used |
| **Partial-update return** | `return {"parsed_listing": result}` | used |
| **Static edges** | `add_edge(...)` chain in `orchestrator.py` | used |
| **START / END** | `add_edge(START, "input_parser")` … `END` | used |
| **Build vs compile** | `build_listingiq_graph()` / `get_compiled_graph()` | used |
| **`ainvoke`** | `run_full_pipeline` | used |
| **`astream` + `stream_mode="updates"`** | `/api/pipeline/stream` | used |
| **Config / thread_id** | `{"configurable": {"thread_id": session_id}}` | passed, unused inside nodes |
| **Checkpointer** | `get_compiled_graph(checkpointer=...)` param | wired, always `None` |
| **Reducers (`Annotated`)** | — | not used |
| **Conditional edges / routing** | — | not used |
| **Parallel fan-out/fan-in** | tried, reverted to sequential | deliberately avoided |
| **Interrupts / human-in-loop** | — | not used |
| **RetryPolicy** | — | not used (worth adding) |
| **`create_react_agent` / `ToolNode`** | — | N/A (fixed pipeline) |
| **Subgraphs / `Command`** | — | not used |
| **LangSmith tracing** | `wrap_openai` in `llm_client.py` | used |

---

## Where to go next (concrete, in priority order)

1. **Add a checkpointer** (`AsyncSqliteSaver`) — unlocks resume + real conversation memory with
   near-zero code, and the `thread_id` plumbing is already there.
2. **Add `RetryPolicy`** to the LLM-calling nodes — cheap resilience for 8 network calls.
3. **Add one conditional edge** (low-confidence classification → rubric regen or human review) —
   the first taste of real branching.
4. **Experiment with `stream_mode=["updates","messages"]`** — live-typing rewrites in the UI.
5. **Revisit parallelism** *only* on a branch, with the reducer knowledge from Part 7.
