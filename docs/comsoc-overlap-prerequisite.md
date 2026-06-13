# Known limitation — COMSOC strategies need overlapping node queries

**Status:** addressed via overlapping-data nodes (option 3) · planner fan-out still optional
**Affects:** the `judgment` and `median` aggregation strategies (Phase 3)

> **Update.** Two overlapping-content nodes were added — **Estates & Facilities**
> and **Office of the Bursar** (both `oblige`, so their figures actually leave
> the node and can be aggregated). Three departments now carry a 2020–2024
> campus-consumption figure (Energy 3.14M kWh, Estates 3.05M, Bursar 3.20M) and
> two carry a research-staff headcount (Archivists 67, Bursar 64), plus a shared
> boolean claim ("lab expansion drove the growth"). Their registry descriptions
> advertise the overlap so the planner routes cross-cutting questions to several
> of them — no planner code change required. The `median` and `judgment`
> strategies are now demonstrable on the live demo (see `scripts/demo.sh` steps
> 5–6). The fan-out options below remain valid if you later want to *force*
> overlap rather than rely on the planner choosing it.

## The issue

The two computational-social-choice strategies aggregate *votes* across nodes:

- `judgment` — a claim is accepted iff a **majority of nodes** assert it
- `median` — the collective value is the **median across nodes** that report it

Both are only meaningful when **several nodes answer the same question**, so that
an aligned issue has more than one voter. With a single voter per issue:

- `judgment` accepts every claim (1 supporter > ½ of an electorate of 1) — no real vote
- `median` returns that one node's value unchanged — no real aggregation

In both cases the strategies degrade to passthrough and look no different from
plain synthesis.

## Why it happens today

The MICE demo has three **heterogeneous, disjoint-domain** nodes:

| Node | Domain |
|---|---|
| Energy Wizards | power/consumption |
| Commons Scholars | papers/datasets |
| Archivists | history/personnel |

The planner sends each its own tailored sub-query, so the facts that come back
rarely describe the *same* proposition. `align_claims` therefore produces mostly
**single-voter issues**, and there is nothing to vote on.

## The fix (separate task)

Give the planner a way to **fan one sub-question to multiple nodes** when the
question is cross-cutting — the direct analogue of Flower sampling *many clients
for the same task*. Concretely, one of:

1. **Planner fan-out flag** — let `make_plan` emit several `PlannedCall`s with
   the same `query` to different `node_id`s when it judges the question common
   to multiple departments.
2. **Redundant-routing mode** — an orchestrator option that broadcasts the
   user's question (or a shared sub-question) to all capable nodes, then lets
   the strategy aggregate the overlapping answers.
3. **A demo scenario with genuinely overlapping data** — e.g. two nodes that
   both hold a figure for the same quantity, so they can agree or disagree.

Option 1 keeps the planner in charge and is the smallest change; option 2 makes
the social-choice behaviour easy to demonstrate on demand.

## Until then

The strategies are correct and unit-tested, but on the current three-node demo
they will mostly behave like passthrough. The `llm` strategy remains the
sensible default. Pick `judgment` / `median` to exercise the COMSOC paths once
overlapping queries exist (or in tests, where overlap is constructed directly —
see `tests/test_comsoc.py`).
