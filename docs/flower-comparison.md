# Mycel vs. Flower — Federated Architecture Comparison

Mycel is an **agentic** take on federated principles: instead of distributing model training, it federates *knowledge access* — autonomous Diplomat nodes hold private data behind OPA egress policies, and a central orchestrator queries them to answer user questions. This document maps mycel's current implementation against the concepts that make the Flower (flwr) federated learning framework tick, and identifies the gaps.

---

## What Flower does (the reference model)

Flower's core loop is:

```
ServerApp
  └─ Strategy (FedAvg, FedProx, …)
        1. sample_clients()        → pick which clients participate
        2. configure_fit()         → send global model + hyper-params
        3. → clients train locally, return (parameters_delta, num_examples, metrics)
        4. aggregate_fit()         → weighted-average the deltas (FedAvg: ∑ nᵢ·Δwᵢ / ∑ nᵢ)
        5. configure_evaluate()    → send updated model for eval
        6. aggregate_evaluate()    → aggregate loss/accuracy metrics
        REPEAT for N rounds until convergence criterion met
```

Key primitives:

| Flower concept | Role |
|---|---|
| **ServerApp / ClientApp** | Typed entry-points; apps declare what messages they handle |
| **Strategy** | Pluggable aggregation: FedAvg, FedProx, FedYogi, QFedAvg, … |
| **ParameterRecord / MetricsRecord / ConfigsRecord** | Structured, typed data containers — not free text |
| **Message (train / evaluate / query)** | Strongly-typed round-trip protocol |
| **Mods** | Middleware stack (DP noise injection, secure aggregation, logging) |
| **Rounds + convergence** | The loop knows *when to stop* |
| **Secure Aggregation** | Server sees only the aggregate, never individual client updates |
| **Differential Privacy** | Clipping + noise baked into the Mods layer |

---

## Mycel — what exists today

### Parallel concepts ✅

| Flower | Mycel equivalent | Notes |
|---|---|---|
| ServerApp / ServerRound | `OrchestratorState` + LangGraph graph | Single-shot; no rounds |
| ClientApp | `DiplomatAgent` (node) | Each node is its own LLM + datastore + OPA sidecar |
| Data locality | Node data never leaves; only `/invoke` responses do | Core invariant, correctly implemented |
| `sample_clients()` | `make_plan()` (planner LLM) | LLM decides which nodes to query and with what |
| `configure_fit()` | Per-node `query` string in `PlannedCall` | Text, not typed parameters |
| Client training step | `run_agent()` tool-calling loop | Agent reads records, produces prose answer |
| Secure output filtering | OPA `evaluate_policy()` | Deny / redact / oblige — analogous to secure aggregation at the *semantic* level |
| Audit log | `log_decision()` per node | Query hashes only; per-decision, not per-round |
| Client registry | `registry.yaml` + `Registry` model | Static YAML; no dynamic join/leave |
| Observability | SSE stream of `plan / node_start / node_result / synthesizing / final` events | Good; Flower exposes similar per-round metrics |

### What Flower has that mycel does not ❌

#### 1. A real aggregation strategy (the biggest gap)

Flower's `aggregate_fit()` does a mathematically defined operation on structured data (weighted parameter averaging). Mycel's "aggregation" is the synthesizer LLM reading free-text answers and writing prose — it is non-deterministic, cannot resolve contradictions, cannot weight by confidence, and has no formal semantics.

```
Flower:  aggregate_fit([( Δw₁, n₁=500 ), ( Δw₂, n₂=300 ), …])
         → Δw_global = (500·Δw₁ + 300·Δw₂) / 800

Mycel:   synthesize_node([
           "Energy Wizards: trend is up 12%",
           "Archivists: consumption records are classified",
         ])
         → LLM writes a paragraph — no formal merge, no conflict detection
```

See [Aggregation gap — design options](#aggregation-gap--design-options) below.

#### 2. Typed message protocol / structured node responses

Flower nodes return `(parameters, num_examples, metrics)` — machine-readable. Mycel nodes return `{answer: str, policy_decision: PolicyDecision}` — only the policy metadata is structured; the answer itself is unstructured text.

This makes it impossible to do anything programmatic with the content: you cannot aggregate numbers, detect duplicate claims, surface contradictions, or weight by confidence without LLM re-parsing.

#### 3. Parallel round execution

Flower can train all sampled clients in parallel (async gRPC). Mycel's `execute_node` calls nodes **sequentially** in a `for` loop — a 3-node federation is 3× slower than necessary, and there is no partial-failure resilience (if node 2 hangs, node 3 never runs within the timeout).

#### 4. Multiple rounds / iterative refinement

Flower converges over many rounds; later rounds can use earlier aggregate results to refine. Mycel is strictly single-shot: `plan → execute → synthesize → done`. There is no mechanism for the synthesizer to ask a follow-up question back to a node if the initial answer was incomplete.

#### 5. Client sampling strategy (pluggable)

In Flower, strategy.sample() is a policy you can swap: random, round-robin, power-of-choice, reputation-weighted. In mycel, "which nodes to call" is decided by the planner LLM on every request — ad-hoc, non-deterministic, and hard to audit or tune independently of the model.

#### 6. Convergence / termination criteria

Flower stops when a metric threshold is met or a round budget is exhausted. Mycel always does exactly one round.

#### 7. Secure Aggregation

Flower's SecAgg mod ensures the server sees only the *sum* of client updates, not individual updates. Mycel's OPA filtering controls what *one node* releases but gives the orchestrator full visibility into each node's answer before synthesis — there is no aggregation-level privacy guarantee.

#### 8. Differential Privacy

Flower has a DP mod that clips and noises updates before aggregation. Mycel has no equivalent. (OPA deny/redact is access control, not DP.)

#### 9. Persistent state / global model

Flower maintains a global model that improves across rounds. Mycel is stateless between requests — there is no "global knowledge artifact" that accumulates across many federation queries.

---

## Aggregation gap — design options

This is the most actionable missing piece. Here are concrete directions, ordered by implementation complexity:

### Option A — Structured node responses (low effort, high leverage)

Change `InvokeResponse.answer: str` to a typed schema:

```python
class StructuredAnswer(BaseModel):
    facts: list[Fact]          # {claim: str, value: Any, unit: str | None, confidence: float}
    summary: str               # prose for the synthesizer
    caveats: list[str]         # policy-imposed limitations
```

The synthesizer then aggregates `facts` programmatically (union, dedup, conflict-flag) before passing the result to the LLM for final prose. This is the direct analogue of Flower's `ParameterRecord`.

### Option B — Per-claim provenance tracking (medium effort)

After synthesis, run a second LLM pass that re-reads the final answer and tags each sentence with the node(s) that contributed it. Surfaces when nodes agree, disagree, or when the synthesizer hallucinated beyond any node's answer.

This mirrors Flower's per-client metrics aggregation — `aggregate_evaluate()` keeps track of which client contributed what to the loss.

### Option C — Weighted synthesis with confidence scores (medium effort)

Have each node return a `confidence: float` alongside its answer. The synthesizer prompt is augmented with these scores so it can resolve contradictions by trusting the more confident source — analogous to Flower's `num_examples`-weighted FedAvg, where clients with more data carry more weight.

### Option D — Iterative follow-up rounds (high effort)

After the first synthesis pass, add a second LangGraph node that detects gaps or contradictions in the synthesized answer and generates follow-up queries back to specific nodes. This is the full Flower multi-round loop, translated to the agentic domain.

### Option E — Formal aggregation strategy abstraction (high effort, most aligned with Flower)

Introduce a `Strategy` protocol analogous to Flower's:

```python
class AggregationStrategy(Protocol):
    def aggregate(self, results: list[NodeResult]) -> AggregatedResult: ...
```

Implementations: `LLMSynthesis` (current), `StructuredUnion`, `ConflictAware`, `ConfidenceWeighted`. Swappable without changing the graph — exactly how Flower's `FedAvg` vs `FedProx` work.

---

## Summary scorecard

| Federated principle | Flower | Mycel |
|---|---|---|
| Data stays local | ✅ | ✅ |
| Typed message protocol | ✅ | ⚠ policy metadata only; answer is free text |
| Pluggable aggregation strategy | ✅ | ❌ LLM synthesis only |
| Parallel client execution | ✅ | ❌ sequential |
| Multiple rounds / convergence | ✅ | ❌ single-shot |
| Configurable client sampling | ✅ pluggable | ⚠ LLM-decided, non-deterministic |
| Policy / access control | ⚠ basic | ✅ OPA-enforced, per-field |
| Secure aggregation | ✅ | ❌ |
| Differential privacy | ✅ | ❌ |
| Persistent global state | ✅ | ❌ |
| Audit log | ⚠ via Mods | ✅ per-decision |
| Observability / streaming | ✅ | ✅ SSE |
| Dynamic node join/leave | ✅ | ❌ static YAML |
