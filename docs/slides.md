---
marp: true
theme: gaia
class: lead
paginate: true
backgroundColor: #0f1117
color: #e6e6e6
style: |
  section {
    font-size: 26px;
    background: #0f1117;
    color: #e6e6e6;
  }
  h1, h2 { color: #b794f6; }
  h3 { color: #90cdf4; }
  strong { color: #f6e05e; }
  code { color: #68d391; background: #1a1d29; }
  pre { background: #1a1d29; border-radius: 8px; font-size: 18px; }
  table { font-size: 20px; }
  a { color: #90cdf4; }
  blockquote { border-left: 4px solid #b794f6; color: #b8b8c0; font-style: italic; }
  section.lead h1 { font-size: 48px; }
  .small { font-size: 18px; color: #9aa0aa; }
---

<!--
============================================================
THE JEALOUS WIZARD'S GUIDE TO FMAS
Target: 40 min talk + 5 min Q&A. ~28 content slides.
Audience: Data Scientists, AI & ML Engineers. Level: Advanced.
Timing cues live in the speaker notes (these HTML comments).
Three demo beats are marked [DEMO]; have the web UI + CLI ready,
and a pre-recorded fallback per the PROJECT.md talk-risk note.
============================================================
-->

# The Jealous Wizard's Guide to **FMAS**

### Federated Multi-Agent Systems

#### Letting agents use data that can never leave the room

<br>

<span class="small">Magical Institute for Commons and Energy · a live walk-through</span>

<!--
0:00–1:00 — Hook. "Every one of you has a dataset you'd love to point an LLM at,
and a lawyer/security team who will never let that data leave the building.
This talk is about building agentic systems for exactly that world."
Set the frame: this is "inspired by" federated principles, not federated learning.
-->

---

## What you'll leave with

- A concrete pattern: **autonomous agents on private data + policy-governed egress**
- Why the **trust anchor is the outgoing text**, not field-level filtering
- How to **aggregate contradictory facts** from many sources without averaging
- An honest scorecard vs. **Flower** (federated learning) — what carries over, what doesn't
- The privacy endgame: **on-device inference**, no data leaves the machine

<br>

> Running example throughout: **MICE** — a research institute whose
> departments will not share their raw data with anyone. Including each other.

<!--
1:00–2:30 — Roadmap slide. Promise both theory and a working system. Tell them
there will be three live demos. Name the honesty up front: "I'll show you the
gaps too — this is a research prototype, not a product."
-->

---

## The problem

You want an agent that can answer:

> *"What's the relationship between energy use and research output here
> over the last decade?"*

…but the answer lives in **five departments**, and every one of them has a
reason their raw data must not leave their walls:

- Energy grid readings → **security / competitive**
- Personnel files → **PII / legal**
- Payroll & budgets → **confidential**

The usual answers — *"centralize it all in a lake"* or *"don't use AI here"* —
are the two options nobody is happy with.

<!--
2:30–4:30 — Establish the pain. These are real enterprise constraints, not
hypotheticals. The dichotomy (centralize everything vs. forego AI) is exactly
what federated approaches reject. Plant the question we'll answer live later.
-->

---

## Borrowed intuition: federated learning

Flower (`flwr`) and friends solved a version of this for **model training**:

```
ServerApp
  └─ Strategy (FedAvg, …)
       sample clients → send model → clients train LOCALLY
       → return parameter deltas → aggregate → repeat
```

The data **never moves**. Only **gradients/parameters** move, and the server
aggregates them.

**Key idea we steal:** keep data local; move only a *governed, aggregable
summary* to the center.

<!--
4:30–6:30 — FL primer for the room (they're ML engineers, keep it brisk).
Emphasize the ONE transferable idea: locality + aggregation. Flag explicitly:
"We are NOT doing federated learning. No training, no gradients. We federate
KNOWLEDGE ACCESS." This pre-empts the inevitable pedantic challenge.
-->

---

## The reframe: federate *knowledge access*

| Federated learning (Flower) | **Mycel / FMAS** |
|---|---|
| Distributes **training** | Distributes **knowledge access** |
| Clients return **parameter deltas** | Nodes return **policy-filtered answers** |
| Aggregate = weighted **mean of tensors** | Aggregate = **social choice over facts** |
| Privacy via secure agg / DP | Privacy via **local inference + egress policy** |

<br>

Same skeleton — **local compute, central aggregation** — different payload:
instead of gradients, **natural-language claims under a policy contract**.

<!--
6:30–8:00 — The pivot slide. This is the conceptual heart of the talk's framing.
The payload changes everything downstream: you can't average prose claims, which
is what forces the COMSOC detour later. Foreshadow it: "hold that last row."
-->

---

# Meet **MICE**

### Magical Institute for Commons and Energy

Five departments. Five **Jealous Wizards**. One question that needs all of them.

<!--
8:00–8:30 — Section divider. Lighten the tone — the "jealous wizard" framing is
the spoonful of sugar. Each wizard guards their data with a policy.
-->

---

## Five wizards, five policies

| Department | Data | Policy mode |
|---|---|---|
| **Energy Wizards** | consumption records | 🚫 **deny** — raw values blocked, aggregates only |
| **Commons Scholars** | papers, datasets | ⚖ **oblige** — open, but attribution required |
| **Archivists** | history, personnel | ✏ **redact** — names & DOBs replaced |
| **Estates & Facilities** | building meters | ⚖ **oblige** — *overlaps Energy* |
| **Office of the Bursar** | payroll, budgets | ⚖ **oblige** — *overlaps Energy + Archives* |

<span class="small">The last two deliberately hold <strong>overlapping facts</strong> — three departments carry a 2020–2024 campus-consumption figure. We'll need that later.</span>

<!--
8:30–10:30 — Walk the table. Three distinct policy MODES is the point: deny,
redact, oblige. The overlap (bottom two) is a deliberate setup for the
aggregation demo — call it out now so the payoff lands later.
-->

---

## Architecture at a glance

```
            ORCHESTRATOR  (registry → planner LLM → aggregation strategy)
                       │
   ┌───────────┬───────┼───────────┬───────────┐
   ▼           ▼       ▼           ▼           ▼
 Energy     Commons  Archivists  Estates     Bursar
 Wizards    Scholars             & Facilities Office
 [DENY]     [OBLIGE] [REDACT]    [OBLIGE]     [OBLIGE]
   │           │       │           │           │
 [OPA]       [OPA]   [OPA]       [OPA]       [OPA]   ← egress policy sidecar
   ↕ MCP       ↕       ↕           ↕           ↕
 [connector] [conn]  [conn]      [conn]      [conn]  ← owner's data, behind MCP
```

- One **codebase**, configured per node by a YAML file
- Each node = **LLM agent (MCP client) + the owner's data connector (MCP server) + OPA sidecar**
- The owner controls **both ends**: what the agent can even *see* (the connector)
  and what may *leave* (OPA). Orchestrator sees only what policy lets out.

<!--
10:30–12:30 — The map. Stress: every node is the SAME image, differentiated by
config (department YAML + data + Rego policy). That's the "one framework, many
deployments" story. The OPA sidecar is the trust boundary — next slide.
-->

---

## The Diplomat Agent (a node)

Not "node agent" — a **Diplomat**: it negotiates on behalf of its data owner.

- **FastAPI** `/invoke` endpoint; the agent is an **MCP client** that connects
  *out* to the owner's data connector (their MCP server)
- A tool-calling **agent loop**: it **discovers** the connector's tools at runtime
  (`list_records` / `get_record` in the demo) → composes an answer
- The agent is **naive** — it just answers the question well
- **OPA is the guarantee**, not the agent's good manners

<br>

> Two owner-controlled boundaries: the **connector** governs what the agent can
> *see* (ingress), **OPA** governs what may *leave* (egress). The agent tries to
> be helpful; the owner's policy decides — at both ends.

<!--
12:30–14:00 — Why separate the agent from the policy? Because an LLM told to
"be careful" is not a security control. Separation of concerns: helpful agent,
strict gatekeeper. This is a hard-won lesson (the planner-refusing bug) — preview.
-->

---

## The trust anchor: judge the **answer text**

Naïve egress filtering redacts **fields** in a side-channel dict.
That leaves a hole: a value the LLM *read* can leak through **prose**.

Mycel's OPA policy input is:

```json
{ "answer": "<the outgoing text>",
  "observations": [ <every tool call the agent made + its result> ],
  "records": [ <records derived from those observations> ] }
```

OPA judges the **text itself** against what was touched. A value the model saw
can't slip out reworded.

<!--
14:00–16:00 — THE key design decision. Originally field-level redaction; that
left exactly the hole described. Switched policy input to judge the answer text
against the agent's observation log ({answer, observations, records}).
This is the slide ML engineers will remember: "filter the output, not the schema."
-->

---

## …but text filtering is a floor, not a ceiling

Real bugs from the **first live runs** — great material, all true:

- 🧮 Model wrote **`42,317 kWh`** (comma) and **`14 March 1971`** (reworded date) →
  evaded exact-match on `42317` / `1971-03-14`.
  **Fix:** digit-normalized matching; DOBs expanded to year + month name.
- 🕳 An agent answered **without calling `get_record`** → no records touched →
  no attribution obligation fired. **Egress filtering can only judge what the
  agent actually touched.**
- ⚠ Residual gap: **unit-converted / rounded** values (`~42.3 MWh`).

<br>

> Substring policies are a **floor**. Production needs semantic filtering or
> structured-output contracts. Naming this honestly buys credibility.

<!--
16:00–18:30 — The honesty slot. Engineers trust a speaker who shows the failure
modes. Each of these is a real audit-log finding. The takeaway: egress filtering
is necessary but not sufficient; know its limits. Don't oversell.
-->

---

## The orchestrator

```
plan → execute → aggregate
```

- **Registry** (`registry.yaml`): who exists, what they answer, overlap **tags**
- **Planner LLM**: emits a structured call plan (which nodes, what sub-query)
  - *forced tool call; unknown nodes dropped; never pre-sanitizes*
- **Execute**: nodes invoked **concurrently** (`asyncio.gather`), failures isolated
- **Aggregate**: a **pluggable strategy** combines the answers

<br>

<span class="small">Built on LangGraph; HTTP to nodes via httpx; SSE streams every step to the UI.</span>

<!--
18:30–20:00 — Map orchestrator stages to Flower: registry+planner ≈ sample_clients,
per-node query ≈ configure_fit, parallel execute ≈ parallel client training,
aggregate ≈ aggregate_fit. Mention the planner bug fix: it must NEVER refuse or
pre-sanitize — policy decisions belong to the nodes (that's the whole point).
-->

---

# DEMO 1 — the federation, live

<br>

1. Cross-node question → watch the **plan** fan out
2. *"What exactly did Tower A consume in 2024?"* → 🚫 **BLOCKED**
3. *"Who runs the Alchemy Lab?"* → ✏ **name redacted**

<span class="small">Setup: <code>mycel-demo init mice && cd mice && docker compose up</code>, then <code>mycel-ui</code> → :7860 · per-card verdict stamps · "interrogate directly" bypasses the planner for a reliable BLOCKED.</span>

<!--
20:00–25:00 — LIVE DEMO (budget 5 min, have pre-recorded fallback ready).
Run the cross-node query first (the payoff). Then the blocked + redacted via the
per-node "interrogate directly" button (deterministic — the planner path can
self-censor, which is also fine, but the button reliably shows OPA blocking).
Show the audit log if time: query hashes only, never content.
If anything is flaky: cut to recording. Do not debug live in front of engineers.
-->

---

## Aggregation is **pluggable** (the Flower analogue)

Swap the aggregator the way Flower swaps `FedAvg` → `FedProx`:

```python
class AggregationStrategy(Protocol):
    name: str
    async def aggregate(self, question, results) -> AggregatedResult: ...
```

| Strategy | What it does |
|---|---|
| `llm` *(default)* | an LLM synthesizes a prose answer |
| `judgment` | proposition-wise **majority** vote across nodes |
| `median` | **Majority Judgment** — confidence-weighted median value |

<span class="small">Selectable via <code>--strategy</code>, <code>?strategy=</code>, or <code>MYCEL_STRATEGY</code>.</span>

<!--
25:00–26:30 — Strategy is the direct Flower analogue. The default is just "LLM
writes a paragraph" — fine, but not aggregation. The interesting two are next.
-->

---

## Why you can't just **average**

Flower aggregates **commensurable numeric tensors** → weighted mean works.

Mycel's nodes return **heterogeneous factual claims** that may
**agree, disagree, or be incommensurable**:

- You cannot average a `true` / `false` claim.
- You cannot average three differently-worded prose figures.
- One overconfident node shouldn't drag the "mean" anywhere.

<br>

So we borrow from **computational social choice (COMSOC)** instead.

<!--
26:30–28:00 — This is the genuine conceptual contribution. Make the audience feel
why FedAvg's mean is undefined here. Set up COMSOC as the right tool: aggregating
contradictory ballots is a SOLVED problem in social choice — voting theory.
-->

---

## COMSOC: voting over facts

**`judgment` — judgment aggregation**
Per proposition, nodes that opined vote. Strict (confidence-weighted)
**majority** wins; no majority → reported **contested**, not averaged into mush.

**`median` — Majority Judgment (Balinski–Laraki)**
Collective numeric value = confidence-weighted **median**, with the
**min–max spread** surfaced. Robust to a single overconfident node.

<br>

> The median rule is the social-choice cousin of FedAvg's mean — exactly the
> **robust aggregator** FL reaches for under Byzantine clients.

<!--
28:00–30:00 — Two strategies, two ballot types (boolean propositions vs numeric).
"Contested" instead of a fake average is the headline — surfacing disagreement is
a feature. Tie median back to robust FL aggregation so the ML crowd has an anchor.
-->

---

## You need something to vote on

A vote needs **multiple voters per issue**. With disjoint departments, the
planner sends each a *different* sub-query → mostly single-voter issues →
strategies degrade to passthrough.

**Fix:** overlapping-data nodes. Three departments carry the same
2020–2024 campus-consumption figure:

| Node | Figure (kWh) |
|---|---|
| Energy | 3.14 M |
| Estates | 3.05 M |
| Bursar | 3.20 M |

→ `median` returns **3.14 M** with the spread surfaced. A real vote.

<!--
30:00–31:30 — This is the analogue of Flower sampling MANY clients for the SAME
task. Registry tags advertise the overlap so the planner fans out. Without it,
COMSOC looks identical to passthrough — a subtle correctness point worth making.
-->

---

# DEMO 2 — aggregation, live

<br>

```bash
mycel-ask "total campus energy consumption 2020–2024" \
  --strategy median
```

Watch it **fan out to all three** overlapping nodes →
median **3.14 M kWh**, spread **3.05–3.20 M**, with **per-node attribution**.

<!--
31:30–34:00 — LIVE DEMO 2 (budget ~2.5 min). Run the median query. Point at the
attribution + spread in the output — "the system tells you WHO backed the number
and how much they disagreed." Contrast with the llm strategy's smooth paragraph
that hides the disagreement. Fallback to recording if needed.
-->

---

## Honest scorecard vs. Flower

| Principle | Flower | Mycel |
|---|---|---|
| Data stays local | ✅ | ✅ |
| Typed message protocol | ✅ | ✅ `StructuredAnswer`/`Fact` (post-policy) |
| Pluggable aggregation | ✅ | ✅ `llm`/`judgment`/`median` |
| Robust / social-choice agg | ⚠ custom | ✅ COMSOC majority + median |
| Parallel execution | ✅ | ✅ failure-isolated |
| Access-control / policy | ⚠ basic | ✅ OPA egress, per-answer |
| **Multiple rounds / convergence** | ✅ | ❌ single-shot |
| **Secure aggregation** | ✅ | ❌ orchestrator sees each answer |
| **Differential privacy** | ✅ | ❌ |
| **Dynamic join/leave** | ✅ | ❌ static YAML |

<!--
34:00–36:00 — Lead with what's DONE, end with what's missing — don't hide the ❌s.
The four gaps are the honest research roadmap. Multiple rounds (re-plan from
contested issues) is the most natural next step. SecAgg/DP are real privacy gaps:
OPA governs what ONE node releases; the orchestrator still sees each answer.
-->

---

## The privacy endgame: **on-device inference**

OPA controls what *leaves a node*. But the node still called a **hosted LLM**.
For truly sensitive data, the **inference itself** should stay local.

```
 local-node ──▶ ollama (container, CPU) · qwen2.5:3b-instruct
   └─ OPA sidecar          privacy = local inference + local egress
```

- Backend is **config-driven** (`devices/*.yaml`): `kind: ollama | hf | …`
- Same node code, swap the brain. **No data leaves the machine.**
- Measured on this laptop (CPU-only WSL2): **≈ 94 s/query** — functional, slow.

<!--
36:00–38:00 — The branch in progress (local-llm). This closes the loop on the
privacy promise: data never leaves AND inference never leaves. Ollama, OpenAI-
compatible /v1 with tool calling, reuses the existing client path. Be honest about
CPU latency — iGPU/NPU aren't passed through to WSL; that's the next speedup.
-->

---

## One codebase, many deployments

The config-driven backend becomes a set of Docker **templates**:

| Template | Backend | For |
|---|---|---|
| **cloud** | HF router / hosted API | managed, no local GPU |
| **on-prem** | self-hosted GPU (vLLM) | data-center, owns hardware |
| **edge / OSS** | Ollama, local CPU/GPU | laptops, air-gapped |

<br>

A genuinely **heterogeneous federation**: different departments, different
hardware, different models — surfaced in the registry, same contract.

<!--
38:00–39:00 — The deployment story ties device profiles back to the federation
framing: heterogeneous clients on heterogeneous hardware is the FL "different
devices" story, realized as compose overlays. Each template = compose file +
device profile; node code identical.
-->

---

## Takeaways

1. **Filter the output, not the schema.** Judge the outgoing text against
   everything the agent touched.
2. **The agent is naive; the policy is the guarantee.** Separate helpfulness
   from enforcement.
3. **You can't average contradictory facts** — reach for **social choice**
   (majority + median), and **surface disagreement** instead of hiding it.
4. **Locality is a spectrum**: egress policy → local inference → fully on-device.
5. It's a **prototype with honest gaps** — rounds, secure agg, DP are open.

<!--
39:00–40:00 — Land the five things you want them to remember. #1 and #3 are the
transferable engineering ideas even if they never touch this repo. Invite the
challenge in Q&A — especially the FL-analogy purists and the "honor-system policy"
trust question (the orchestrator is a central trust anchor — who audits it?).
-->

---

# Thank you

### The Jealous Wizard's Guide to **FMAS**

<br>

**Questions?**

<span class="small">
Likely Q&A: "is this really federated?" (no — inspired by; we federate access) ·
"what stops a node lying about its policy?" (nothing yet — honor-system; TEE
attestation is future work) · "who audits the orchestrator?" (open trust
question) · "latency?" (sequential CPU local ≈ 94s; HF much faster).
</span>

<!--
40:00–45:00 — Q&A. Anticipated questions are noted above. For anything you can't
answer: "open question, here's my current thinking" beats hand-waving with this
audience. Have the repo/README open in case someone wants to see code.
-->
