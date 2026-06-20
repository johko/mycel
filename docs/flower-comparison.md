# Mycel vs. Flower — Federated Architecture Comparison

Mycel is an **agentic** take on federated principles: instead of distributing model training, it federates *knowledge access* — autonomous Diplomat nodes hold private data behind OPA egress policies, and a central orchestrator queries them to answer user questions. This document maps mycel's implementation against the concepts that make the Flower (flwr) federated learning framework tick, tracks what has been built, and identifies the gaps that remain.

> **Status:** the four-phase aggregation plan ([aggregation-strategy-plan.md](aggregation-strategy-plan.md)) is implemented and live-verified. The three biggest gaps this document originally flagged — no aggregation strategy, no structured responses, sequential execution — are now closed. See [Recently closed](#recently-closed-gaps).

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

## Mycel — parallel concepts ✅

| Flower | Mycel equivalent | Notes |
|---|---|---|
| ServerApp / ServerRound | `OrchestratorState` + LangGraph graph | Single-shot; no rounds |
| ClientApp | `DiplomatAgent` (node) | LLM agent = MCP client to the owner's data connector (MCP server) + OPA sidecar |
| Data locality | Owner's data stays behind the connector; only `/invoke` responses leave | Ingress (connector) + egress (OPA), both owner-controlled |
| `sample_clients()` | `make_plan()` (planner LLM) + registry `tags` | LLM picks nodes; tags advertise data + overlap to guide it |
| `configure_fit()` | Per-node `query` in `PlannedCall` | Planner fans the same query to nodes sharing a fact |
| Client training step | `run_agent()` tool-calling loop | Agent reads records, produces a prose answer |
| `(parameters, num_examples, metrics)` | `StructuredAnswer{facts, summary, caveats}` | Machine-readable `Fact{claim, value, unit, confidence, source_record}` |
| **Strategy** (FedAvg, FedProx, …) | `AggregationStrategy` protocol (`llm` / `judgment` / `median`) | Swappable via `--strategy`, `?strategy=`, `MYCEL_STRATEGY` |
| `aggregate_fit()` weighting by `num_examples` | confidence-weighted `judgment` / `median` | A node's vote ∝ its `confidence` |
| Parallel client training (async gRPC) | `asyncio.gather` in `execute_node` | Nodes invoked concurrently; per-node failures isolated |
| Secure output filtering | OPA `evaluate_policy()` | Deny / redact / oblige — semantic-level egress control |
| per-client metrics provenance | `AggregatedResult.node_attribution` + `conflicts` | Which nodes backed each accepted claim; disagreements surfaced |
| Audit log | `log_decision()` per node | Query hashes only; per-decision |
| Client registry | `registry.yaml` + `Registry` (now with `tags`) | Static YAML; no dynamic join/leave |
| Observability | SSE stream (`plan / node_start / node_result / synthesizing / final`) | Strategy name carried on the `synthesizing` event |

---

## Recently closed gaps

These were the three headline gaps in the original version of this document. All are now implemented (see [aggregation-strategy-plan.md](aggregation-strategy-plan.md) for the phased build).

### 1. A real aggregation strategy — DONE

The orchestrator no longer hard-codes "an LLM writes a paragraph." `synthesize_node` delegates to a pluggable `AggregationStrategy`:

```python
class AggregationStrategy(Protocol):
    name: str
    async def aggregate(self, question: str, results: list[NodeResult]) -> AggregatedResult: ...
```

`STRATEGY_REGISTRY` maps names to implementations; `make_strategy()` constructs one; the graph, CLI, web API, and UI all select by name. This is the direct analogue of swapping Flower's `FedAvg` for `FedProx`.

### 2. Typed message protocol / structured node responses — DONE

`InvokeResponse` now carries an optional `StructuredAnswer` alongside the prose:

```python
class Fact(BaseModel):
    claim: str
    value: Any | None
    unit: str | None
    confidence: float
    source_record: str | None

class StructuredAnswer(BaseModel):
    facts: list[Fact]
    summary: str          # the policy-filtered prose
    caveats: list[str]    # policy-imposed limitations
```

This is mycel's `ParameterRecord`/`MetricsRecord` — the machine-readable payload the strategies vote over. Crucially, facts are extracted **post-policy** (from the OPA-filtered `safe_answer`, not the raw agent output), so a structured fact can never carry a value the policy layer blocked. Extraction degrades to `None` on failure, so the orchestrator falls back to prose-only.

### 3. Parallel client execution — DONE

`execute_node` invokes nodes concurrently with `asyncio.gather`; a slow or failing node no longer blocks the rest (each result captures its own error). Results preserve plan order.

---

## Where mycel *diverges* from Flower (by design)

Flower's aggregation is **cardinal numeric averaging**: `aggregate_fit` computes a weighted mean of model-parameter tensors. That presupposes every client reports a comparable numeric update.

Mycel's nodes report **heterogeneous factual claims that may agree, disagree, or be incommensurable** — so it borrows from **computational social choice (COMSOC)** instead of averaging:

- **`judgment` — judgment aggregation.** Per proposition, the nodes that opined vote; the value held by a strict (confidence-weighted) majority wins, and an issue with no majority is reported *contested* rather than averaged into a meaningless middle. Flower has no analogue — you cannot "average" a `true`/`false` claim or three different prose figures.
- **`median` — Majority Judgment (Balinski–Laraki) / median-voter.** For numeric claims, the collective value is the confidence-weighted **median** with the min–max spread surfaced. Robust to a single overconfident node — the median-rule counterpart to Flower's mean-based FedAvg, and the kind of trimmed/robust aggregator FL research reaches for under Byzantine clients.

This is a genuine conceptual contribution, not a gap: **robust social-choice aggregation of contradictory textual facts**, where a parameter mean would be undefined.

To make these strategies meaningful, the demo gained **overlapping-content nodes** (Estates & Facilities, Office of the Bursar) so several departments hold the *same* fact — three carry a 2020–2024 campus-consumption figure, two carry a research-staff headcount. This is the federation analogue of Flower sampling *many clients for the same task* so there is something to aggregate.

---

## What Flower still has that mycel does not ❌

#### 1. Multiple rounds / iterative refinement & convergence

Flower converges over many rounds; later rounds refine on earlier aggregates, and the loop knows when to stop. Mycel is strictly single-shot: `plan → execute → aggregate → done`. There is no mechanism for a strategy to detect a gap (e.g. a *contested* `judgment` issue) and fire a follow-up round of queries. This is the most natural next step — a LangGraph loop that re-plans from `AggregatedResult.conflicts`.

#### 2. Pluggable *sampling* strategy

Flower's `sample()` is swappable (random, power-of-choice, reputation-weighted). Mycel's node selection is the planner LLM, now guided by registry `tags` and a fan-out prompt — better and more demonstrable, but still LLM-decided rather than a formal, swappable, auditable sampler. (Aggregation *is* now pluggable; sampling is not.)

#### 3. Secure Aggregation

Flower's SecAgg lets the server see only the *sum* of client updates. Mycel's OPA filtering governs what *one node* releases, but the orchestrator — and the COMSOC strategies — see each node's individual answer. There is no aggregation-level privacy guarantee.

#### 4. Differential Privacy

No clipping/noise mechanism. OPA deny/redact is access control, not DP.

#### 5. Persistent state / global model

Flower maintains a global model that improves across rounds. Mycel is stateless between requests — no knowledge artifact accumulates across queries.

#### 6. Dynamic node join/leave

Membership is a static `registry.yaml`. No runtime registration, health-gated participation, or churn handling.

---

## Summary scorecard

| Federated principle | Flower | Mycel |
|---|---|---|
| Data stays local | ✅ | ✅ |
| Typed message protocol | ✅ | ✅ `StructuredAnswer` / `Fact` (post-policy) |
| Pluggable aggregation strategy | ✅ | ✅ `llm` / `judgment` / `median`, runtime-selectable |
| Robust / social-choice aggregation | ⚠ via custom strategies | ✅ COMSOC: majority + median rules |
| Confidence / weight-aware aggregation | ✅ `num_examples` | ✅ `confidence`-weighted |
| Provenance of aggregated result | ⚠ metrics only | ✅ `node_attribution` + `conflicts` |
| Parallel client execution | ✅ | ✅ `asyncio.gather`, failure-isolated |
| Policy / access control | ⚠ basic | ✅ OPA-enforced, per-field |
| Observability / streaming | ✅ | ✅ SSE, strategy-tagged |
| Audit log | ⚠ via Mods | ✅ per-decision |
| Configurable client sampling | ✅ pluggable | ⚠ LLM-decided, tag-guided (not a formal sampler) |
| Multiple rounds / convergence | ✅ | ❌ single-shot |
| Secure aggregation | ✅ | ❌ orchestrator sees each answer |
| Differential privacy | ✅ | ❌ |
| Persistent global state | ✅ | ❌ stateless |
| Dynamic node join/leave | ✅ | ❌ static YAML |
