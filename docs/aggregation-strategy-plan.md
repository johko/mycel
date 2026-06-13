# Aggregation Strategy — Implementation Plan

Inspired by Flower's `Strategy` abstraction: swap the aggregation logic without touching the graph. The goal is to offer the user named, pluggable policies (like `FedAvg` vs `FedProx`) while keeping the current LLM-synthesis behavior as the default.

---

## Design overview

```
OrchestratorState
  plan → [execute in parallel] → NodeResult[]
                                      │
                              AggregationStrategy.aggregate()
                                      │
                               AggregatedResult
                                      │
                              synthesize_node()      ← becomes a thin wrapper
                                      │
                               final_answer: str
```

The strategy receives the full `list[NodeResult]` and returns an `AggregatedResult` — a structured intermediate that always carries both machine-readable content and a prose summary. The final `synthesize_node` formats that into the answer the user sees.

---

## Phase 1 — Strategy protocol + LLM strategy refactor

**Goal:** introduce the abstraction without changing any visible behavior.

### New file: `src/mycel/orchestrator/strategies/__init__.py`

Exports `AggregationStrategy`, `AggregatedResult`, and the concrete strategies by name.

### New file: `src/mycel/orchestrator/strategies/base.py`

```python
from typing import Protocol
from mycel.orchestrator.graph import NodeResult   # already defined

class AggregatedResult:
    summary: str          # human-readable prose for the final answer
    facts: list[dict]     # machine-readable claims (populated in later phases)
    conflicts: list[dict] # detected contradictions (populated in Phase 3)
    node_attribution: dict[str, list[str]]  # node_id → list of fact keys it contributed

class AggregationStrategy(Protocol):
    name: str
    async def aggregate(self, results: list[NodeResult]) -> AggregatedResult: ...
```

### New file: `src/mycel/orchestrator/strategies/llm_synthesis.py`

Move the current `_SYNTH_SYSTEM_PROMPT` + `chat_with_retry` call out of `graph.py` into a `LLMSynthesisStrategy` class. This is a pure refactor — the prompt and LLM call are identical, just relocated.

`LLMSynthesisStrategy.aggregate()`:
1. Format results with `_format_results()` (same as today)
2. Call the LLM with the synth prompt
3. Return `AggregatedResult(summary=llm_response, facts=[], conflicts=[], node_attribution={})`

### Changes to `graph.py`

- `build_graph()` gains a `strategy: AggregationStrategy = LLMSynthesisStrategy(model)` parameter
- `synthesize_node` calls `strategy.aggregate(state["results"])` and writes `aggregated.summary` to `final_answer`
- Remove the inline prompt and LLM call from `graph.py`

### Changes to `cli.py` and `web.py`

- `--strategy` argument (CLI) and `MYCEL_STRATEGY` env var (web), defaulting to `"llm"`
- A `STRATEGY_REGISTRY: dict[str, type[AggregationStrategy]]` in `strategies/__init__.py` maps names to classes

**Deliverable:** everything still works identically; strategy is now swappable.

---

## Phase 2 — Structured node response schema

**Goal:** give the strategy machine-readable content to work with. This is the prerequisite for Phases 3 and 4.

### Changes to `schemas.py`

```python
class Fact(BaseModel):
    claim: str           # natural-language statement
    value: Any | None    # extracted scalar if present (e.g. 12.3, "up", True)
    unit: str | None     # e.g. "kWh", "%", None
    confidence: float    # 0.0–1.0, node-estimated
    source_record: str | None  # record ID the node read this from

class StructuredAnswer(BaseModel):
    facts: list[Fact]
    summary: str         # prose answer (same as current answer field)
    caveats: list[str]   # policy-imposed limitations ("raw values blocked", etc.)

class InvokeResponse(BaseModel):
    node_id: str
    answer: str                          # kept for backward compatibility
    structured_answer: StructuredAnswer | None = None
    policy_decision: PolicyDecision
```

### Changes to `node/agent.py`

After the LLM produces its prose answer, a second forced tool call extracts `Fact` objects from it. The node already has the `touched_records` — this is where the `source_record` field is populated.

New tool: `submit_structured_answer` (forced, same retry pattern as planner's `submit_plan`).

### Changes to `node/main.py`

Populate `structured_answer` in the `/invoke` response. Fall back to `structured_answer=None` if extraction fails, so the orchestrator degrades gracefully to prose-only.

**Deliverable:** nodes return structured facts; orchestrator can use them or ignore them.

---

## Phase 3 — Concrete aggregation strategies

Each strategy lives in its own file under `strategies/`.

### `StructuredUnionStrategy` (`strategies/structured_union.py`)

Aggregation logic (pure Python, no LLM):
1. Collect all `Fact` objects across all nodes
2. Deduplicate: group by normalized `claim` string (lowercased, stripped)
3. For duplicates, keep the one with the highest `confidence`
4. Build `node_attribution` map
5. Format the deduplicated facts as a structured prompt context
6. One LLM call for final prose (shorter prompt than today because facts are pre-structured)

Best for: questions where nodes return independent, non-overlapping facts.

### `ConflictAwareStrategy` (`strategies/conflict_aware.py`)

Aggregation logic:
1. Run `StructuredUnion` dedup
2. Conflict detection: for facts with the same `claim` key but different `value`, flag as a conflict
3. Pass conflicts explicitly to the LLM with instructions to surface disagreement, not paper over it
4. `AggregatedResult.conflicts` populated

Best for: queries where nodes might contradict each other (e.g., different departments disagree on a metric).

### `ConfidenceWeightedStrategy` (`strategies/confidence_weighted.py`)

Aggregation logic:
1. Same as `StructuredUnion`, but when resolving duplicates, weight by `confidence * num_examples_equivalent` (node reports its own record count)
2. Conflicts where confidence is close (within 0.1) are escalated to the LLM; clear winners are resolved programmatically
3. Each fact in the LLM prompt carries its confidence score so the model can calibrate hedging language

Best for: queries where nodes have unequal data quality or coverage.

### `VotingStrategy` (`strategies/voting.py`) — stretch goal

Nodes receive the same question; the strategy counts how many independently arrive at the same claim. Claims with majority support (`>50%` of responding nodes) are marked as high-confidence. Minority claims are surfaced but flagged. Useful when nodes are homogeneous and you want consensus rather than union.

---

## Phase 4 — Strategy selection at runtime

### CLI

```bash
mycel-ask "..." --strategy llm            # default, current behavior
mycel-ask "..." --strategy union          # StructuredUnion
mycel-ask "..." --strategy conflict       # ConflictAware
mycel-ask "..." --strategy confidence     # ConfidenceWeighted
```

### Web UI

Dropdown on the query form (next to the question input). Strategy name stored in a query param: `GET /api/ask?question=...&strategy=union`. The SSE `plan` event includes the chosen strategy name so the UI can display it.

### `MYCEL_STRATEGY` env var

Default strategy for all requests when not overridden per-request.

---

## File map

```
src/mycel/
├── schemas.py                          # add Fact, StructuredAnswer; extend InvokeResponse
├── node/
│   └── agent.py                        # add structured extraction tool call
├── orchestrator/
│   ├── graph.py                        # build_graph(strategy=) param; thin synthesize_node
│   ├── cli.py                          # --strategy arg
│   ├── web.py                          # strategy= query param + env var
│   └── strategies/
│       ├── __init__.py                 # STRATEGY_REGISTRY, re-exports
│       ├── base.py                     # AggregationStrategy protocol, AggregatedResult
│       ├── llm_synthesis.py            # current behavior, extracted
│       ├── structured_union.py         # Phase 3
│       ├── conflict_aware.py           # Phase 3
│       └── confidence_weighted.py      # Phase 3
```

---

## Implementation order

| Phase | Effort | Risk | Delivers |
|---|---|---|---|
| 1 — Protocol + LLM refactor | S | Low — pure refactor | Swappable strategy, no behavior change |
| 2 — Structured node responses | M | Medium — node API change, backward-compat needed | Machine-readable facts; Phases 3–4 unblocked |
| 3 — Concrete strategies | M per strategy | Low — isolated files | Named policies user can select |
| 4 — Runtime selection | S | Low | Strategy surfaced in UI/CLI |

Start with Phase 1 (pure refactor, can't break anything), then Phase 2 (the enabling change), then implement strategies one at a time in Phase 3.

---

## What this looks like relative to Flower

| Flower | Mycel after this plan |
|---|---|
| `Strategy.aggregate_fit(results)` | `AggregationStrategy.aggregate(results)` |
| `FedAvg`, `FedProx`, `FedYogi` | `LLMSynthesis`, `StructuredUnion`, `ConflictAware`, `ConfidenceWeighted` |
| `ParameterRecord` (typed parameters) | `Fact` (typed claims with value + confidence) |
| `num_examples` weighting | `confidence` weighting |
| `STRATEGY_REGISTRY` (Flower plugin system) | `STRATEGY_REGISTRY: dict[str, type[AggregationStrategy]]` |
| Strategy set at `ServerApp` launch | Strategy set via `--strategy` / env var / query param |
