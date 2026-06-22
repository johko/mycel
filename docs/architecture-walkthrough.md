# Mycel Architecture — Walkthrough

A narrative companion to [architecture.md](architecture.md) (which holds the
diagram + how-a-company-integrates view). This file records the component-level
clarifications: what each part is, what it is *not*, and where the LLM calls and
network boundaries actually sit.

One-line mental model:

> **registry (routing) → planner → executor → [per-node: agent loop → OPA egress
> → fact extraction] → claim alignment → pluggable aggregation (LLM | majority |
> median) → SSE to UI**, with a swappable inference backend under every LLM call.

---

## 1. The orchestrator is a 3-stage LangGraph

`plan → execute → synthesize`, compiled in
[graph.py](../src/mycel/orchestrator/graph.py).

- **Planner** — *an LLM*. [planner.py](../src/mycel/orchestrator/planner.py).
  Takes the question + `registry.describe()` (a curated capability projection,
  **not** the raw `registry.yaml`) and emits a structured `list[PlannedCall]`
  (`{node_id, query, rationale}`) via a **forced `submit_plan` tool call**.
  - Forwards the user's need **verbatim** — explicitly told *not* to
    pre-sanitize a query to fit a node's policy. Egress decisions belong to the
    nodes.
  - Deliberately **fans the same query out to multiple departments** when they
    may hold corroborating data, so the aggregation layer can cross-check.

- **Executor** — *not* an agent; it's plumbing, **no LLM**.
  [graph.py:85-98](../src/mycel/orchestrator/graph.py#L85-L98).
  - Runs the plan over HTTP (`POST {endpoint}/invoke`), 3 retries per node for
    transient failures.
  - Runs all calls **concurrently** via `asyncio.gather` — despite the planner
    prompt mentioning "order," there is no sequential/dependent execution; nodes
    never see each other's responses.
  - Emits `node_start` / `node_result` stream events for the live UI.

- **Synthesizer** — *an LLM, but pluggable* (see §3). Delegates to an
  `AggregationStrategy.aggregate(...)`. Honors policy obligations and surfaces
  what each node's policy blocked.

> Better framing than "three sub-agents": **two LLM agents (planner,
> synthesizer) bracketing a mechanical executor.** The real autonomous agent is
> the node being queried.

---

## 2. The Diplomat node

A node *is* an LLM tool-calling loop + MCP client + (optional) OPA rego — cleanly
separated layers.

### The agent loop — [agent.py:39-105](../src/mycel/node/agent.py#L39-L105)
`run_agent` runs up to `_MAX_TURNS = 10`:
- Sends `messages` + MCP tool schemas to the LLM.
- If the model returns `tool_calls`, **the Python loop executes them** against
  `toolset.call(...)`, appends results as `role: "tool"` messages, loops.
- No tool calls → that's the final answer.
- Accumulates an **observation log** — every `{tool, arguments, result}` — the
  raw material the egress policy later judges against. This module "knows nothing
  about OPA" by design.

### MCP client — [mcp_client.py](../src/mycel/node/mcp_client.py)
The node is an MCP **client** connecting *out* to the company's MCP server. Tools
are **discovered at runtime** (`list_tools()`), translated to OpenAI tool schema,
dispatched over the **MCP streamable-HTTP transport**. The reserved `policy_view`
tool is hidden from the model and called only by the node afterward to give OPA a
canonical `{id: record}` view.

### OPA egress — [policy.py:42-76](../src/mycel/node/policy.py#L42-L76)
After the loop, `/invoke` posts `{answer, observations, records}` to
`POST {opa_url}/v1/data/diplomat/result`. OPA returns allow/redact/obligations
**and the safe answer text** (rego decides; the node doesn't redact). No
`opa_url` → answer leaves as-is.

### Correction: the LLM does **not** do the communication
Three distinct HTTP channels; the model is a passive responder on one. It never
opens a socket — it only names a tool + arguments.

| Channel | Who drives it | Transport |
|---|---|---|
| Orchestrator → node | FastAPI `/invoke` | plain HTTP (executor) |
| Node → MCP server (data) | `RemoteToolset` / `ClientSession` | **MCP streamable-HTTP** |
| Node → LLM inference | `chat_with_retry` / `get_client` | OpenAI-style chat completions over HTTP |

Flow: **inference HTTP returns a tool-call request → the Python agent loop
performs the MCP HTTP call → feeds the result back to the model.** "Streaming"
in this codebase = LangGraph stream-writer events for the UI + the MCP transport
name — *not* the inference calls, which are plain request/response.

### Two LLM passes per node
1. The agent loop (above).
2. **`extract_facts`** ([agent.py:168-205](../src/mycel/node/agent.py#L168-L205))
   — runs *after* the policy filter, on the already-safe answer, producing the
   `StructuredAnswer` the voting strategies consume.

---

## 3. The synthesizer is a pluggable social-choice layer

Not one thing. Three strategies ([strategies/](../src/mycel/orchestrator/strategies/)),
selectable per-request (`?strategy=` / `--strategy` / `MYCEL_STRATEGY`):

- **`llm_synthesis`** (default) — prose synthesis over the node answers.
- **`judgment`** — proposition-wise **majority rule** (COMSOC).
  [judgment.py](../src/mycel/orchestrator/strategies/judgment.py). Per-issue
  electorate: only nodes that opined vote. A strict (optionally
  confidence-weighted) majority → ACCEPTED; otherwise CONTESTED and surfaced, not
  resolved.
- **`median`** — Balinski–Laraki **Majority Judgment**.
  [majority_judgment.py](../src/mycel/orchestrator/strategies/majority_judgment.py).
  Confidence-weighted median value per issue + min–max spread as a disagreement
  signal; robust to one outlier node.

### Claim alignment is a distinct pre-voting LLM pass
`align_claims` (`_align.py`) maps each node's heterogeneous facts onto shared
**issues/propositions** (`Position{node_id, value, confidence}`) *before* any
vote. Both voting strategies fall back to `llm_synthesis` if alignment yields no
issues.

### Dual output path per node — [schemas.py](../src/mycel/schemas.py)
Every node returns **two** representations: the prose `answer` *and* a
`StructuredAnswer` of `Fact{claim, value, unit, confidence, source_record}`. The
LLM strategy uses the prose; the voting strategies operate on the facts.

---

## 4. Other components worth naming

- **Registry as a routing layer** —
  [registry.py](../src/mycel/orchestrator/registry.py). `tags` are the data
  keywords; **shared tags across nodes are the corroboration signal** that drives
  the planner's fan-out. `describe()` is the exact text the planner sees;
  `policy_mode`/`icon` are display-only.

- **Egress is richer than "an OPA rego"** — OPA returns the safe text itself
  (clean / substring-redacted / empty) plus `redactions`, `violations`,
  `obligations`, `reason`. Obligations propagate to the synthesizer. An
  append-only **audit log** ([policy.py:79-89](../src/mycel/node/policy.py#L79-L89))
  records a query *hash* and field names, **never the sensitive values**.

- **Serving / streaming layer** — [web.py](../src/mycel/orchestrator/web.py). SSE
  dashboard streaming `plan → node verdicts → final` from the LangGraph custom
  channel. `/api/direct` bypasses the planner to interrogate a single node (shows
  raw policy enforcement). All branding comes from the registry — the framework
  ships no scenario of its own.

- **Inference-backend abstraction** — [llm.py](../src/mycel/llm.py)
  `BackendConfig` + node `DEVICE_PROFILE`. Each node picks its own backend (HF
  router default, or local OpenAI-compatible / Ollama) over the *same*
  chat-completion path — the seam the local-inference work lives in.
