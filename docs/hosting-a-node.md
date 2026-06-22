# Hosting a Diplomat Node on Your Own Data

A guide for a **data owner** who wants to expose their data to a central Mycel
orchestrator (run by someone else) *without* handing over the data. You host a
**Diplomat node** — an agent container that sits in front of your data — and the
orchestrator only ever reaches it through a single `/invoke` HTTP call. Your data
sovereignty is enforced at two boundaries you fully control:

- **Ingress** — your MCP server decides what the agent can even see.
- **Egress** — your OPA policy vets every outgoing answer before it leaves.

The orchestrator never connects to your database, your MCP server, or your OPA —
only to the node's `/invoke` endpoint, and only ever receives policy-filtered text.

```
                          your environment (you control everything here)
                ┌───────────────────────────────────────────────────────────┐
 central        │   ┌──────────────┐   MCP    ┌─────────────┐                 │
 orchestrator ──┼──▶│ Diplomat node│◀────────▶│ MCP server  │──▶ your data    │
 (someone else) │   │  (we ship)   │  (HTTP)  │ (you build) │                 │
  HTTP /invoke  │   └──────┬───────┘          └─────────────┘                 │
                │          │ POST /v1/data/diplomat/result                     │
                │          ▼                                                   │
                │   ┌──────────────┐                                          │
                │   │ OPA (egress) │  ← your rego                              │
                │   └──────────────┘                                          │
                └───────────────────────────────────────────────────────────┘
```

You run **three things**: the node container (we ship it), an **MCP server** over
your data (you build it, or use the reference connector), and an **OPA** instance
loaded with **your egress policy**.

---

## Prerequisites

- The `mycel` container image (`mycel:latest`, or a published image). Build it
  from the mycel source once: `docker build -t mycel:latest .` — the image
  carries the framework only, **no data and no node identity**.
- An LLM the node can call for inference. Either:
  - a **Hugging Face token** (`HF_TOKEN`) to use the HF Inference Providers router (default), or
  - a **local / self-hosted OpenAI-compatible endpoint** (e.g. Ollama) via a device profile — see [local-inference-plan.md](local-inference-plan.md).
- A network path from the orchestrator to your node's `/invoke` (see Step 6).
- The data you want to expose, and a clear idea of what must **never** leave.

---

## Step 1 — Stand up an MCP server over your data (ingress)

The node is an **MCP client**. It connects out to an MCP server you run and
discovers whatever tools that server exposes *at runtime* — this is your ingress
control: the agent can only ever see what your server chooses to expose.

You have two options:

**(a) Use the reference connector** (fastest). The shipped image has a `connector`
entrypoint that fronts one data source over MCP at `/mcp`, selected by
`CONNECTOR_KIND` (`json` | `sql` | `rag`). It exposes `list_records` / `get_record`
tools. Point it at your data with a mounted volume. Good for JSON, SQLite, or a
RAG corpus. See the demo's `*-connector` services in
[../src/mycel/demo/assets/docker-compose.yml](../src/mycel/demo/assets/docker-compose.yml).

**(b) Build your own MCP server** (full control). Expose your real data sources as
MCP tools however you like — the agent discovers them at runtime. Requirements:

- Serve the **streamable-HTTP** MCP transport (the node connects with
  `streamablehttp_client`), at a URL ending in `/mcp`.
- Expose **at least one tool**; the node refuses to start if the server exposes none.
- Give each tool a clear description and input schema — the agent routes purely
  off these.
- **(Recommended)** implement the reserved **`policy_view`** tool so your OPA
  policy can govern *record fields* rather than raw tool output (see Step 3). It
  takes the agent's observation log and returns a canonical `{id: record}` map.
  The node hides this tool from the LLM and calls it only for the policy layer.
  Reference implementation:
  [../src/mycel/demo/connector/policy.py](../src/mycel/demo/connector/policy.py).

> Whatever you do **not** expose as a tool, the agent cannot reach. Ingress
> sovereignty starts here.

---

## Step 2 — Write the node config

A node is one generic container; its identity comes entirely from a YAML file
referenced by the `NODE_CONFIG` env var. Minimal config:

```yaml
# nodes/mydept.yaml
id: my-department                 # stable identifier; the registry uses this
title: My Department
description: >
  One or two sentences on what data this node holds and what its policy does.
  (This text is for humans; the orchestrator gets the registry entry, Step 7.)
system_prompt: >
  You are the Diplomat Agent for <department>. Answer questions about <data>
  using your tools. Ground every claim in tool results — never answer from
  memory. If the tools do not contain the answer, say so. Be concise.
# mcp.url can be set here or injected at deploy time via MCP_URL (Step 5)
mcp:
  url: http://my-connector:9000/mcp
opa_url: http://my-opa:8181        # omit to run with NO egress check (not advised)
model: moonshotai/Kimi-K2-Instruct # or set NODE_MODEL; or a local backend
```

The full set of fields lives in
[../src/mycel/node/config.py](../src/mycel/node/config.py) (`NodeConfig`). Most
deployment-specific fields can be supplied by env var instead of YAML (Step 5).

The `system_prompt` matters: it's the only thing steering how the agent uses your
tools. Tell it to always read records before answering and never to speculate.

---

## Step 3 — Write your OPA egress policy

This is your last line of defense: the node sends every outgoing answer to OPA
**before it leaves the container**, and OPA returns the safe text plus a verdict.
If no `opa_url` is configured the answer leaves unchecked — so for sensitive data,
always configure one.

**The contract** (the node calls `POST {opa_url}/v1/data/diplomat/result`):

*Input* the node sends as `{"input": ...}`:
```json
{
  "answer": "the agent's outgoing text",
  "observations": [{"tool": "...", "arguments": {...}, "result": ...}],
  "records": { "<id>": { ...record the agent touched... } }
}
```
- `observations` — the raw tool-call log; always present.
- `records` — the canonical `{id: record}` view from your `policy_view` tool;
  `{}` if you didn't implement one. Prefer `input.records` for field-level policies.

*Output* — your rego must be `package diplomat` and define a `result` object:
```rego
result := {
  "allow":      true,            # required: false blocks the answer entirely
  "answer":     safe_text,       # the text that actually leaves (redacted/empty/clean)
  "redactions": [{"record": id, "field": f}],  # optional, for the audit view
  "violations": [{"record": id, "field": f}],  # optional
  "obligations":["Attribution required. Cite: ..."],  # optional; orchestrator honors these
  "reason":     "why blocked"    # optional; null when allowed
}
```
The node reads `allow` and `answer` from this; the rest feed the decision record
and audit log. **The node never redacts — your rego decides the safe `answer`.**

Three worked patterns ship in the demo (copy and adapt):
- **deny** — block the whole answer if a sensitive value appears: [../src/mycel/demo/assets/opa/energy/policy.rego](../src/mycel/demo/assets/opa/energy/policy.rego)
- **redact** — replace sensitive substrings with `[REDACTED]`: [../src/mycel/demo/assets/opa/archives/policy.rego](../src/mycel/demo/assets/opa/archives/policy.rego)
- **oblige** — allow, but attach an attribution obligation: [../src/mycel/demo/assets/opa/commons/policy.rego](../src/mycel/demo/assets/opa/commons/policy.rego)

Each ships with a `policy_test.rego` — write tests for your policy and run
`opa test ./opa/mydept`. Run OPA as a server watching your policy dir:
`opa run --server --addr=0.0.0.0:8181 --watch /policies`.

> Substring policies have known limits (unit-converted or reworded values can slip
> past). For high-stakes fields, prefer `deny` over `redact`, and keep your
> `policy_view` records narrow — OPA can only catch values it's given.

---

## Step 4 — Wire the three containers together

Run node + MCP server + OPA on a private network; only the node's port is
exposed outward. A minimal compose for one node (mirrors the demo's per-node trio):

```yaml
services:
  my-node:
    image: mycel:latest            # default entrypoint: diplomat (the agent)
    ports: ["8000:8000"]           # the only port the orchestrator reaches
    environment:
      NODE_CONFIG: nodes/mydept.yaml
      MCP_URL: http://my-connector:9000/mcp
      OPA_URL: http://my-opa:8181
      HF_TOKEN: ${HF_TOKEN}        # or configure a local backend
      AUDIT_LOG_PATH: /var/log/diplomat/audit.log
    volumes: ["./nodes:/app/nodes:ro", "my-logs:/var/log/diplomat"]
    depends_on: [my-opa, my-connector]

  my-connector:                    # your MCP server (or the reference connector)
    image: mycel:latest
    command: ["connector"]
    environment: { CONNECTOR_KIND: json, CONNECTOR_DATA: data/mydept.json, CONNECTOR_NAME: my-department }
    volumes: ["./data:/app/data:ro"]

  my-opa:
    image: openpolicyagent/opa:latest-static
    command: ["run", "--server", "--addr=0.0.0.0:8181", "--watch", "/policies"]
    volumes: ["./opa/mydept:/policies:ro"]

volumes: { my-logs: }
```

The node container exposes port **8000** and serves `/invoke` and `/health`.

---

## Step 5 — Configuration reference (env vars)

Set these on the node container. Env vars override the YAML config.

| Env var | Required | Purpose |
|---|---|---|
| `NODE_CONFIG` | yes | path to the node YAML |
| `MCP_URL` | yes (here or in YAML) | your MCP server's streamable-HTTP endpoint |
| `MCP_AUTH_TOKEN` | no | bearer token sent to your MCP server (sets `Authorization` header) |
| `OPA_URL` | strongly advised | egress policy endpoint; omit ⇒ **no egress check** |
| `HF_TOKEN` | if using HF | auth for the Hugging Face inference router |
| `HF_PROVIDER` | no | pin an HF provider (default `auto`) |
| `NODE_MODEL` | no | override the model id |
| `DEVICE_PROFILE` | no | point the node at a local/self-hosted model (see local-inference doc) |
| `AUDIT_LOG_PATH` | no | where egress decisions are logged (field names only, never values) |

---

## Step 6 — Expose the node to the orchestrator

The central orchestrator only needs to reach **one endpoint**: your node's
`POST /invoke`. Decide how it reaches you:

- a public hostname / reverse proxy, a VPN, or a private peering link.
- **The framework puts no authentication on `/invoke`.** Front it with your own
  gateway (mTLS, an API key/bearer at the proxy, IP allowlist) so only the
  orchestrator can call it. Treat the node endpoint like any other exposed API.
- Confirm the node can reach *outbound* to: your MCP server, your OPA, and your
  inference endpoint (HF or local).

`/invoke` request/response shape (from [../src/mycel/schemas.py](../src/mycel/schemas.py)):
```
POST /invoke   {"query": "<question>"}
→ {"node_id", "answer", "structured_answer": {...}, "policy_decision": {...}}
```

---

## Step 7 — Register with the central service

The orchestrator routes off a **registry entry** — give the operator these fields
(matches `NodeEntry` in [../src/mycel/orchestrator/registry.py](../src/mycel/orchestrator/registry.py)):

```yaml
- id: my-department          # must match the node config id
  title: My Department
  description: >             # the planner reads THIS to decide whether to call you
    What data you hold and what your policy does. Be specific — this is the
    planner's only basis for routing a question to you.
  endpoint: https://my-node.example.com   # where the orchestrator reaches /invoke
  policy_mode: redact        # display hint for UIs: deny | redact | oblige
  icon: "🏛️"                 # optional, display only
  tags: [budget, payroll, headcount]   # routing keywords; SHARED tags with another
                                        # node signal overlapping data that can be
                                        # cross-checked by the aggregation layer
```

Two fields do real work: **`description`** and **`tags`** are what the planner uses
to decide whether (and with what query) to call your node. Shared tags across nodes
are how the federation knows two departments may corroborate the same fact.

---

## Step 8 — Verify

```bash
# 1. Node is up and connected to its MCP server (check logs for "connected to MCP server … tools: […]")
curl -s http://localhost:8000/health        # → {"status":"ok","node":"my-department"}

# 2. End-to-end invoke through your own policy
curl -s -X POST http://localhost:8000/invoke \
  -H 'Content-Type: application/json' \
  -d '{"query": "ask something your data can answer"}' | python3 -m json.tool

# 3. Egress policy is doing its job — ask for something that MUST be blocked/redacted
curl -s -X POST http://localhost:8000/invoke \
  -H 'Content-Type: application/json' \
  -d '{"query": "give me a raw sensitive value verbatim"}' | python3 -m json.tool
#   → check policy_decision.allowed / redactions / reason, and that `answer` is safe

# 4. Unit-test the rego directly
opa test ./opa/mydept
```

When the orchestrator operator adds your registry entry, ask them to use the UI's
**direct-node** call (or `mycel-ask` against a registry containing only your node)
to confirm reachability and policy enforcement before going live.

---

## Sovereignty checklist

- [ ] MCP server exposes **only** the tools/data you intend (ingress).
- [ ] `policy_view` returns a **narrow** record view — OPA can only protect fields it sees.
- [ ] `OPA_URL` is set; rego has tests; high-stakes fields use `deny`, not `redact`.
- [ ] `/invoke` sits behind your own auth/network controls (the framework adds none).
- [ ] MCP server and OPA are **not** publicly reachable — only the node endpoint is.
- [ ] Audit log is collected; remember it stores field names and decisions, never values.

See [architecture.md](architecture.md) and [architecture-walkthrough.md](architecture-walkthrough.md)
for how your node fits the wider federation.
