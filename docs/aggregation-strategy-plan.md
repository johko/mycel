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

A forced tool call (`submit_facts`, same retry pattern as the planner's
`submit_plan`) extracts `Fact` objects.

> **Implemented deviation — extract *after* policy, not before.** The original
> sketch ran extraction on the agent's raw answer inside `run_agent`. That
> would let structured facts carry exactly the values OPA deny/redact strips
> from the prose, defeating the egress invariant. Extraction therefore runs on
> the **post-policy `safe_answer`** (`extract_facts` / `build_structured_answer`),
> so facts provably contain no blocked value. `source_record` is attributed
> from the record IDs the agent fetched — now derived from the observation log
> via `observed_record_ids()` (the agent is an MCP client; record IDs come from
> the connector's `list_records`/`get_record` tools).

### Changes to `node/main.py`

Populate `structured_answer` in the `/invoke` response *after* `evaluate_policy`.
`_policy_caveats()` derives `caveats` from the `PolicyDecision`. Fall back to
`structured_answer=None` if extraction fails, so the orchestrator degrades
gracefully to prose-only.

**Deliverable:** nodes return structured facts; orchestrator can use them or ignore them.

---

## Phase 3 — Two computational-social-choice aggregation strategies

Rather than many ad-hoc heuristics, add exactly **two** strategies, both
grounded in **computational social choice (COMSOC)** — the theory of
aggregating individual inputs into a collective decision. They sit alongside
`LLMSynthesisStrategy` and consume the `Fact` objects from Phase 2.

COMSOC has two classical branches; we take one strategy from each:

- **Judgment aggregation** — combining yes/no judgments on propositions → Strategy 1
- **Cardinal / graded voting** — the median-grade rule → Strategy 2

### Shared preprocessing: claim alignment (`strategies/_align.py`)

Both strategies need to know which facts *from different nodes* refer to the
same underlying proposition. Free-text `claim` strings won't match exactly, so
a shared helper `align_claims(results)` groups facts into **issues** — one
issue = one proposition several nodes may opine on. A single LLM pass clusters
the pooled facts into issues and, for each (issue, node), records whether the
node asserts it and with what `value` / `confidence`. The output is a
node × issue matrix that both strategies operate on. (Fallback when the LLM
clustering is unavailable: normalized-string grouping of `claim`.)

> **Prerequisite — overlapping queries.** Social-choice aggregation is only
> meaningful when *multiple nodes answer the same question*. The current MICE
> demo has heterogeneous nodes with disjoint data, so most issues would have a
> single voter and aggregation degenerates to passthrough. To exercise these
> strategies the planner must fan the same sub-question to several nodes — the
> direct analogue of Flower sampling *many clients for the same task*. This is
> a planner/demo change tracked separately; the strategies themselves are
> agnostic to how the overlap arises.

### Strategy 1 — `JudgmentAggregationStrategy` (`strategies/judgment.py`), name `"judgment"`

Proposition-wise majority rule from judgment aggregation theory, scoped
**per issue**.

1. Run `align_claims` → node × issue matrix.
2. For each issue, the electorate is **only the nodes that opined on it** — a
   node silent on a topic does not count against it. Group those voters by the
   value they reported and find the value with the most support (optionally
   **confidence-weighted**, so a vote carries weight ∝ its `confidence`).
3. **Accept** the issue with the winning value iff that value commands a strict
   majority of the issue's voters (support > ½·∑weights). Record any dissenting
   value in `AggregatedResult.conflicts`.
4. **Contested:** if no value reaches a majority (e.g. three nodes give three
   different figures), do not pick one — surface the split in `conflicts` and
   leave it out of the accepted set. (Picking a central value is the `median`
   strategy's job; judgment reports what the federation does and does not
   collectively affirm.) This per-issue value split is our pragmatic, honest
   stand-in for the discursive dilemma, which we cannot detect in full without
   an explicit logical-constraint model.
5. Build `node_attribution` (every voter per issue) and run a short LLM prose
   pass over the accepted + contested sets.

Best for: discrete / boolean claims where you want the federation's collective
position *and* an honest signal when the nodes that opined cannot agree.

### Strategy 2 — `MajorityJudgmentStrategy` (`strategies/majority_judgment.py`), name `"median"`

The median-grade rule (Balinski & Laraki's *Majority Judgment*; for numeric
values, the median-voter estimator).

1. Run `align_claims` → node × issue matrix.
2. For each issue, collect the grades / values the asserting nodes assign
   (grade = `confidence`; value = the fact's `value`).
3. The collective grade is the **median** grade across asserting nodes; for
   numeric `value`s the collective value is the (confidence-weighted) median
   value. The median is strategyproof and robust to a single overconfident or
   outlier node — unlike max-confidence, where the loudest node wins.
4. Ties broken by the standard MJ procedure (drop one median grade from each
   side, repeat).
5. Emit the chosen value / grade per issue, surface the spread (min/max across
   nodes) as a caveat, and run a short LLM prose pass.

Best for: contested **numeric or graded** claims where nodes disagree and you
want a robust central estimate plus an explicit disagreement spread.

### Why these two (vs. the original four)

They cover the two things that actually go wrong when independent nodes report
on shared issues: (a) *do they collectively affirm a claim?* — judgment
aggregation; (b) *when they disagree on a magnitude, what is the robust
collective value?* — the median rule. Both carry formal guarantees (majority
consistency; strategyproofness / robustness of the median) rather than the
heuristic dedup of the dropped `StructuredUnion` / `ConfidenceWeighted`
sketches.

---

## Phase 4 — Strategy selection at runtime ✅

### CLI

```bash
mycel-ask "..." --strategy llm            # default, current behavior
mycel-ask "..." --strategy judgment       # proposition-wise majority (judgment aggregation)
mycel-ask "..." --strategy median         # median-grade rule (Majority Judgment)
```

### Web UI

Dropdown on the query form (next to the question input), populated from
`GET /api/strategies` (name + label + description, sourced from
`STRATEGY_REGISTRY`). Strategy passed per-request as a query param:
`GET /api/ask?question=...&strategy=judgment`. The backend keeps one compiled
graph per strategy (lazy, reused) and rejects unknown names with 400. The SSE
`synthesizing` event carries the chosen strategy name, shown as a badge on the
answer card.

### `MYCEL_STRATEGY` env var

Default strategy when a request omits `strategy=` (and the CLI/web default).

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
│       ├── llm_synthesis.py            # current behavior, extracted  (Phase 1 ✅)
│       ├── _align.py                   # shared claim-alignment helper (Phase 3)
│       ├── judgment.py                 # JudgmentAggregationStrategy   (Phase 3)
│       └── majority_judgment.py        # MajorityJudgmentStrategy      (Phase 3)
```

---

## Implementation order

| Phase | Effort | Risk | Delivers |
|---|---|---|---|
| 1 — Protocol + LLM refactor ✅ | S | Low — pure refactor | Swappable strategy, no behavior change |
| 2 — Structured node responses ✅ | M | Medium — node API change, backward-compat needed | Machine-readable facts; Phases 3–4 unblocked |
| 3 — Two COMSOC strategies | M | Medium — claim-alignment is the hard part | `judgment` + `median` strategies |
| 4 — Runtime selection | S | Low | Strategy surfaced in UI/CLI |

Phases 1 and 2 are done. Phase 3 builds the shared `align_claims` helper first
(the hard part), then the two strategies on top of the node × issue matrix.

---

## What this looks like relative to Flower

| Flower | Mycel after this plan |
|---|---|
| `Strategy.aggregate_fit(results)` | `AggregationStrategy.aggregate(results)` |
| `FedAvg`, `FedProx`, `FedYogi` | `LLMSynthesis`, `JudgmentAggregation`, `MajorityJudgment` |
| `ParameterRecord` (typed parameters) | `Fact` (typed claims with value + confidence) |
| `num_examples` weighting | `confidence` weighting (median / majority threshold) |
| (n/a — numeric averaging) | COMSOC aggregation: median-voter & proposition-wise majority |
| `STRATEGY_REGISTRY` (Flower plugin system) | `STRATEGY_REGISTRY: dict[str, type[AggregationStrategy]]` |
| Strategy set at `ServerApp` launch | Strategy set via `--strategy` / env var / query param |
