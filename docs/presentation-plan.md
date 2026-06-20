# Presentation plan — The Jealous Wizard's Guide to FMAS

**Slot:** 45 min (≈40 min talk + 5 min Q&A)
**Audience:** Data Scientists, AI & ML Engineers · level: advanced
**Frame:** MICE — Magical Institute for Commons and Energy
**Deliverable:** [slides.md](slides.md) (Marp)

---

## The binding narrative: MICE and its wizards

The **MICE story is the spine of the entire talk**, not a running example
introduced mid-way. We *open cold* inside the story — the Archchancellor of the
Magical Institute for Commons and Energy wants to know something that spans the
whole institute, but every department is run by a **Jealous Wizard** who guards
their own data and will not hand it over. The protective-data-owner problem is
**dramatized through the wizards first**, before any abstraction or jargon.

Only once the audience is hooked on the story do we **break frame for a proper
self-introduction** (who I am, why I care about this). Then we go to federated
learning for the borrowed intuition, reframe it, and from there the wizards
return as the live system — the same characters, now running real nodes. The
story opened the problem; the system is its resolution; the wizards are the
through-line that binds motivation → architecture → demo.

---

## Core thesis: the data owner stays in charge

The emotional and technical spine of the first half is **data sovereignty**.
The world is full of **data silos** because owners are — rightly — protective:
PII, security, competitive, regulatory. The status quo asks them to *give up
control* (ship raw data to a central lake) to get any value from AI. They say no.

**The whole pitch is: you never have to give up control.** Your data stays on
your machine. *You* write the policy. *You* decide, per answer, what is allowed
to leave. The architecture's job is to make that promise **enforceable and
auditable**, not honor-system. A Jealous Wizard participates because
participation costs them nothing they didn't explicitly authorize.

So Act 0 and Act 1 are framed as a **security argument**, not an architecture
tour: *here is why it is safe to say yes.* Every core component is introduced as
an answer to "but what stops my data from leaking?":

- **MCP data connector** → the agent is a *client* of the owner's MCP server, so
  *you* decide what it can even see (ingress control), without shipping data.
- **OPA egress policy** → *you* own the rules; nothing leaves unjudged.
- **Judge the answer text, not the schema** → no leak through reworded prose.
- **The agent is naive; OPA is the guarantee** → safety doesn't depend on an LLM
  behaving.
- **Audit log** → you can prove what left and what didn't (hashes, not content).
- **On-device inference (Act 3)** → the endgame: the data is never even *read*
  off your hardware.

---

## Guiding principle: progressive disclosure

Don't put all five departments on the table at once. The talk **escalates the
world to match the concept being taught**:

1. **Start small — three *disjoint* departments.** Energy (deny), Commons
   (oblige), Archivists (redact). This is enough to teach the *whole core*:
   data locality, the Diplomat agent, the OPA egress trust anchor, the
   orchestrator loop, and a satisfying first demo. Three policy *modes*, three
   *domains* — clean and easy to hold in your head.
2. **Hit the wall.** With disjoint nodes, "aggregation" is just *an LLM writes a
   paragraph*. There's nothing to vote on. Make the audience feel the limitation.
3. **Grow the world to fix it.** *Now* introduce the two overlapping departments
   (Estates, Bursar) so multiple nodes hold the *same* fact — which is precisely
   what unlocks the sophisticated COMSOC aggregation (judgment / median).
4. **Zoom out.** Scorecard vs. Flower, the on-device privacy endgame, honest gaps.

This mirrors how the system was actually built (three nodes first; overlapping
nodes added later specifically to make COMSOC meaningful) — so the narrative is
also the true story.

---

## Act structure

### Act 0 — The story, the speaker, the intuition (≈0:00–8:00, ~8 min)
Open *inside* the MICE story; let it carry the whole problem statement. Step out
to introduce myself, then borrow the federated-learning intuition.

- **Title** — set the storybook tone; "A guide for jealous wizards."
- **The story of MICE (cold open)** — the Archchancellor of the Magical
  Institute for Commons and Energy needs an answer that spans the whole
  institute. Introduce a couple of **Jealous Wizards** and what they hoard
  (energy readings, personnel records). Establish the tension *narratively*: the
  wizards will not hand over their data — and they're *right* not to.
- **The Archchancellor's dilemma** — the bad dichotomy, told in-story: command
  every wizard to surrender their grimoires to a central vault (they refuse,
  rightly) or give up on the question entirely. Neither respects the wizards'
  need for **control**. *"What if no wizard ever had to give up their secrets?"*
  — the wish that sets up everything.
- **Who I am** — break frame. Proper self-introduction: name, role, why this
  problem (data sovereignty + agents) is the one I care about. Brief.
- **What you'll leave with** — the five takeaways, promise of 3 live demos, honesty.
- **Federated learning primer** — Flower's loop; the *one* idea we steal:
  local compute + central aggregation, data never moves.
- **The reframe** — we federate *knowledge access*, not training. Payload is
  NL claims under a policy contract, not gradients. (Explicitly "inspired by.")
  Bridge back: *the wizards are about to become real nodes.*

### Act 1 — Why it's safe to say yes (≈8:00–25:00, ~17 min)
The core of the system, taught on a clean 3-node world, as a *security argument*.
Every component answers "but what stops my data from leaking?"

- **Back to the wizards — now as a system** — section divider: the characters
  from the cold open return as real nodes. *"Let's grant the Archchancellor's
  wish."* (Bring back only three of the five departments for now.)
- **Three wizards, three policies** — Energy **deny**, Commons **oblige**,
  Archivists **redact**. Frame as: *each owner sets their own rules*. Three
  *modes*, three *disjoint domains*. (No Estates / Bursar yet — keep it simple.)
- **Architecture at a glance** — orchestrator + 3 nodes. Each node's agent is an
  **MCP client** to the owner's data connector, with **its own** OPA sidecar. The
  owner's data **never leaves**; only governed answers do. One codebase, per-node
  YAML — but the *connector* and the *policy* are the owner's.
- **The Diplomat Agent** — naive helpful agent; **OPA is the guarantee, not the
  agent's manners**. Safety must not depend on an LLM choosing to behave.
- **The trust anchor** — policy input `{answer, observations, records}`: judge the
  outgoing *text* against everything touched, so nothing leaks through reworded prose.
  *This is the slide that earns the "you stay in charge" promise.*
- **It's auditable** — every decision is logged (hashes, not content). The owner
  can prove what left and what was blocked. Control you can verify, not trust.
- **Floor, not ceiling** — the real live-run failures (comma/date reformatting,
  untouched-records hole, unit conversion gap). The honesty slot — name the
  limits of egress filtering so the security claim stays credible.
- **The orchestrator** — `plan → execute → aggregate`; registry, planner (never
  refuses / pre-sanitizes — *policy decisions belong to the owner's node, not a
  central gatekeeper*), parallel execute. Map stages to Flower.
- **DEMO 1** — cross-node query fans out; BLOCKED (Energy raw value); redacted
  (Archivist name). The owner's policy visibly stopping data at the door.
  ~5 min, recorded fallback ready.

### Act 2 — Hit the wall, then grow the world (≈25:00–34:00, ~9 min)
The limitation that motivates everything sophisticated.

- **Aggregation is pluggable** — the Strategy protocol; `llm` default = "LLM
  writes a paragraph." Flower analogue.
- **Why you can't average** — heterogeneous, contradictory, incommensurable
  claims. Mean is undefined.
- **The wall** — with our three *disjoint* nodes, every issue has ONE voter →
  `judgment`/`median` degrade to passthrough. There's nothing to vote on.
- **Grow the world** — *introduce Estates & Facilities + Office of the Bursar.*
  Now three departments carry the same 2020–2024 consumption figure (3.14 / 3.05
  / 3.20 M kWh). Registry tags advertise overlap; planner fans out. This is the
  Flower "sample many clients for the same task" move.
- **COMSOC** — `judgment` (majority, contested ≠ averaged) and `median`
  (Balinski–Laraki, confidence-weighted median + spread; robust-FL cousin).
- **DEMO 2** — `--strategy median` fans to all three, returns 3.14 M with spread
  + per-node attribution. Contrast with the `llm` paragraph that hides the
  disagreement. ~2.5 min.

### Act 3 — Zoom out (≈34:00–40:00, ~6 min)
Where it sits and where it's going.

- **Scorecard vs. Flower** — lead with ✅, end with ❌ (rounds, secure agg, DP,
  dynamic membership). Honest roadmap.
- **On-device inference** — `local-llm` branch; Ollama, config-driven backend;
  privacy = local inference + local egress; CPU latency honesty (~94 s/query).
- **One codebase, many deployments** — cloud / on-prem / edge templates;
  heterogeneous federation.
- **Takeaways** — the five things to remember.

### Q&A (≈40:00–45:00)
Pre-loaded: "is this really federated?", "what stops a node lying about its
policy?", "who audits the orchestrator?", latency.

---

## Slide-by-slide map (target ~28 slides)

| # | Slide | Act | ~min |
|---|---|---|---|
| 1 | Title | 0 | 0:00 |
| 2 | The story of MICE (cold open: Archchancellor + wizards) | 0 | 0:30 |
| 3 | The Archchancellor's dilemma (bad dichotomy, in-story) | 0 | 2:30 |
| 4 | Who I am (break frame, self-intro) | 0 | 4:00 |
| 5 | What you'll leave with | 0 | 5:00 |
| 6 | Federated learning primer | 0 | 6:00 |
| 7 | The reframe: federate knowledge access | 0 | 7:00 |
| 8 | Back to the wizards — now a system (divider) | 1 | 8:00 |
| 9 | **Three** wizards, three policies (owner sets rules) | 1 | 8:30 |
| 10 | Architecture at a glance (3 nodes, data never leaves) | 1 | 10:30 |
| 11 | The Diplomat Agent (OPA is the guarantee) | 1 | 12:30 |
| 12 | Trust anchor: judge the answer text | 1 | 14:00 |
| 13 | It's auditable — prove what left | 1 | 15:30 |
| 14 | Floor, not ceiling (live-run failures) | 1 | 16:30 |
| 15 | The orchestrator (policy stays with the owner) | 1 | 18:30 |
| 16 | **DEMO 1** — your policy stops data at the door | 1 | 20:00 |
| 17 | Aggregation is pluggable | 2 | 25:00 |
| 18 | Why you can't average | 2 | 26:30 |
| 19 | The wall: nothing to vote on | 2 | 28:00 |
| 20 | Grow the world: overlapping nodes | 2 | 29:30 |
| 21 | COMSOC: voting over facts | 2 | 31:00 |
| 22 | **DEMO 2** — aggregation, live | 2 | 32:30 |
| 23 | Scorecard vs. Flower | 3 | 34:00 |
| 24 | On-device inference (data never even read off-box) | 3 | 36:00 |
| 25 | One codebase, many deployments | 3 | 38:00 |
| 26 | Takeaways | 3 | 39:00 |
| 27 | Thank you / Q&A | — | 40:00 |

---

## Changes from the current draft of `slides.md`

The existing deck front-loads **all five** departments and frames the opening as
an architecture tour. To adopt this plan:

1. **Open cold inside the MICE story.** Replace the abstract "The problem" slide
   with a story arc: *the story of MICE* (Archchancellor + wizards) → *the
   Archchancellor's dilemma* (the bad dichotomy, told in-story) → break frame for
   a *self-introduction* → roadmap. The protective-owner problem is dramatized
   through the wizards, not stated as bullets. The wizards then return in Act 1
   as real nodes — the binding through-line.
2. **Split the departments table.** The wizards slide shows only Energy / Commons
   / Archivists (three disjoint domains, three modes), framed as *each owner sets
   their own rules*. Drop Estates & Bursar here.
3. **Slim the architecture diagram** to three nodes; caption it "data never
   leaves; only governed answers do."
4. **Add an "it's auditable" slide** after the trust anchor — control you can
   verify (decision log, hashes not content). Reinforces the security thesis.
5. **Add a new "the wall" slide** between "why you can't average" and COMSOC —
   the explicit single-voter passthrough problem.
6. **Promote "grow the world"** to a proper reveal of Estates & Bursar with the
   overlapping-figure table — now a *story beat*, not a footnote.
7. **Thread the control language** through Act 1's existing slides (Diplomat,
   trust anchor, orchestrator, Demo 1) — each phrased as "what stops my data
   from leaking?". Everything after Act 1 is largely as-is.

---

## Open decisions (need your call)

- **Live vs. recorded demos.** Plan assumes live with recorded fallback. Your own
  notes warn against a flaky live distributed demo. Recommend recording all three
  beats regardless.
- **Depth of the FL primer.** This is an ML audience — is slide 4 too basic, or
  the right level of shared vocabulary before the reframe?
- **Cut candidates if running long:** the deployment-templates slide (22) and
  some of the floor/ceiling failure detail (11) are the most compressible.
