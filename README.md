# Mycel — Federated Multi-Agent System

A framework for multi-agent AI systems inspired by federated principles:
autonomous **Diplomat Agents** operate inside isolated environments and share
only **policy-filtered** outputs with a central orchestrator. Sensitive data
never leaves its environment; only governed responses do.

```
            ORCHESTRATOR  (registry → planner LLM → aggregation strategy)
                       │
   ┌───────────┬───────┼───────────┬───────────┐
   ▼           ▼       ▼           ▼           ▼
 Energy     Commons  Archivists  Estates     Bursar
 Wizards    Scholars             & Facilities Office
 [DENY]     [OBLIGE] [REDACT]    [OBLIGE]     [OBLIGE]
 raw vals   attrib.  names/DOBs  meter kWh    payroll/spend
 never      required never leave (overlaps    (overlaps
 leave                            Energy)      Energy+Archives)
```

The orchestrator's aggregation strategy is pluggable (`llm` synthesis by
default, or the `judgment` / `median` computational-social-choice strategies
that vote across the overlapping nodes).

Each Diplomat node is the same codebase configured by a YAML file. Its agent is
an **MCP client**: it fetches data over the Model Context Protocol from a data
connector (the company's own MCP server, or the bundled reference connector),
and an OPA sidecar enforces the node's egress policy. The policy judges the
**outgoing answer text** against every record the agent touched — so a value the
LLM read can't slip out through prose.

The framework (`pip install mycel`) ships **no scenario of its own**. The MICE
demo below is optional content under `mycel.demo`, installed with the `[demo]`
extra and laid down on disk with the `mycel-demo` command.

## Demo scenario: MICE

The *Magical Institute for Commons and Energy* has five departments, each run
by a Jealous Wizard with their own policy:

| Department | Data (connector backend) | Policy mode |
|---|---|---|
| Energy Wizards | consumption records (JSON) | **deny** — raw values blocked, aggregates only |
| Commons Scholars | papers, datasets (JSON) | **oblige** — open, but attribution required |
| Archivists | history, personnel files (**Qdrant RAG** — semantic search) | **redact** — names & birth dates replaced |
| Estates & Facilities | building meters, floorspace (JSON) | **oblige** — *overlaps Energy's consumption figures* |
| Office of the Bursar | payroll, budgets (**SQLite** — SQL query) | **oblige** — *overlaps Energy & Archivists' figures* |

The reference connector fronts three interchangeable backends — a flat JSON
store, an in-memory SQLite database, and an in-memory Qdrant RAG index — selected
per node via `CONNECTOR_KIND`. Each exposes its own MCP tool surface (records,
SQL, or semantic search), yet the **same** egress policy governs every one: a
connector opts into field-level OPA governance by implementing the well-known
`policy_view` tool, which maps what the agent touched to a canonical record view.

The last two departments deliberately hold **overlapping** facts: three
departments carry a campus-consumption figure for 2020–2024 and two carry a
research-staff headcount. When the planner fans a question to several of them,
the `judgment` and `median` aggregation strategies have something to actually
vote on (see [docs/comsoc-overlap-prerequisite.md](docs/comsoc-overlap-prerequisite.md)).

## Quickstart

All LLM inference runs on [Hugging Face Inference Providers](https://huggingface.co/docs/inference-providers)
through the HF router — any tool-calling open-weights model works
(default: `moonshotai/Kimi-K2-Instruct`; override with `MYCEL_MODEL`,
`NODE_MODEL`, `PLANNER_MODEL`; pin a provider with `HF_PROVIDER` or a
`model:provider` suffix like `moonshotai/Kimi-K2-Instruct:groq`).

```bash
docker build -t mycel:latest .       # framework image — bundles the [demo] extra
                                      #   (qdrant + fastembed for the RAG connector)
pip install mycel[demo]              # or, from a checkout: uv sync --extra demo
mycel-demo init mice                 # scaffold the demo assets on disk
cd mice
cp .env.example .env                  # add your HF_TOKEN
docker compose up                     # 5 nodes + connectors + OPA sidecars
mycel-ui                              # demo dashboard → http://localhost:7860
```

> **First run:** the Archivists' RAG connector downloads its embedding model
> (~50 MB, `BAAI/bge-small-en-v1.5`) on first start, so `archives-connector`
> takes a little longer to become ready and needs network that first time. Ask
> the archivists too early and you'll get a "not ready" error — give it a minute.
> Upgrading from an earlier checkout? **Rebuild** `mycel:latest` — the image now
> installs the `[demo]` extra, and the RAG connector won't start on a stale image.

`mycel-demo init <dir>` copies the demo's docker-compose stack, node configs,
data files, OPA policies, and registry into `<dir>` (docker-compose needs real
files on disk). The containers run the `mycel:latest` framework image and mount
all of that content; override the image with `MYCEL_IMAGE`.

The web UI shows the federation live: the planner's call plan, queries
flowing to the department nodes, policy verdicts stamped on each card
(⛔ blocked / ✏ redacted / ⚖ attribution), and the synthesized answer.
Each card also has an **"interrogate directly"** button that bypasses the
planner and sends your question straight to one node — the most reliable
way to watch OPA block a raw-value request.

The dropdown next to the question picks the **aggregation strategy** — how the
orchestrator combines node responses (`llm` synthesis by default, plus two
computational-social-choice strategies, `judgment` and `median`). See
[docs/aggregation-strategy-plan.md](docs/aggregation-strategy-plan.md) and the
[overlap prerequisite](docs/comsoc-overlap-prerequisite.md) the COMSOC
strategies need.

The same flow is available on the command line:

The same flow is available on the command line (run from the scaffolded `mice/`
directory, where `registry.yaml` lives):

```bash
mycel-ask "What is the relationship between energy consumption patterns and research output at MICE over the last decade?"
mycel-ask "What exactly did Tower A consume in 2024?"   # → blocked
mycel-ask "Who runs the Alchemy Lab?"                   # → name redacted
mycel-ask "..." --strategy judgment                     # COMSOC aggregation
./demo.sh                                               # all demo queries
```

## Node API

| Endpoint | Description |
|---|---|
| `POST /invoke` | `{"query": ...}` → policy-filtered answer + decision |
| `GET /health` | liveness |

The agent is an MCP *client*; the MCP server (streamable HTTP) is the separate
data **connector** the node connects out to, not an endpoint on the node itself.
Every policy decision is appended to an audit log (`/var/log/diplomat/audit.log`
in the container) — query hashes only, never content.

## Development

```bash
uv sync --extra demo                             # install (with dev + demo deps)
uv run pytest                                    # Python tests (RAG tests skip if qdrant absent)
ASSETS=src/mycel/demo/assets                     # demo content lives here now
opa test $ASSETS/opa/energy $ASSETS/opa/commons  # policy tests (per node dir)

# run a connector standalone — backend chosen by CONNECTOR_KIND (json | sql | rag)
CONNECTOR_KIND=sql CONNECTOR_DATA=$ASSETS/data/bursar.sql uv run connector
CONNECTOR_KIND=rag CONNECTOR_DATA=$ASSETS/data/archives.json uv run connector

NODE_CONFIG=$ASSETS/nodes/energy.yaml MCP_URL=http://localhost:9000/mcp uv run diplomat
```

The reference connector (`mycel.demo.connector`) lives under the demo, not the
core framework — a real deployment replaces it with the company's own MCP server.

See [.claude/PROJECT.md](.claude/PROJECT.md) for architecture decisions and roadmap.
