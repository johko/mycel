# Mycel — Federated Multi-Agent System

A framework for multi-agent AI systems inspired by federated principles:
autonomous **Diplomat Agents** operate inside isolated environments and share
only **policy-filtered** outputs with a central orchestrator. Sensitive data
never leaves its environment; only governed responses do.

```
                 ORCHESTRATOR  (registry → planner LLM → synthesizer)
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
  Energy Wizards  Commons Scholars  Archivists
  [OPA: DENY]     [OPA: OBLIGE]     [OPA: REDACT]
  raw values      attribution       names & DOBs
  never leave     required          never leave
```

Each Diplomat node is the same codebase configured by a YAML file
([nodes/](nodes/)), backed by its own data store ([data/](data/)) and an OPA
sidecar enforcing its department's egress policy ([opa/](opa/)). The policy
judges the **outgoing answer text** against every record the agent touched —
so a value the LLM read can't slip out through prose.

## Demo scenario: MICE

The *Magical Institute for Commons and Energy* has three departments, each run
by a Jealous Wizard with their own policy:

| Department | Data | Policy mode |
|---|---|---|
| Energy Wizards | consumption records | **deny** — raw values blocked, aggregates only |
| Commons Scholars | papers, datasets | **oblige** — open, but attribution required |
| Archivists | history, personnel files | **redact** — names & birth dates replaced |

## Quickstart

All LLM inference runs on [Hugging Face Inference Providers](https://huggingface.co/docs/inference-providers)
through the HF router — any tool-calling open-weights model works
(default: `moonshotai/Kimi-K2-Instruct`; override with `MYCEL_MODEL`,
`NODE_MODEL`, `PLANNER_MODEL`; pin a provider with `HF_PROVIDER` or a
`model:provider` suffix like `moonshotai/Kimi-K2-Instruct:groq`).

```bash
cp .env.example .env          # add your HF_TOKEN
docker compose up --build     # 3 nodes (:8001-:8003) + 3 OPA sidecars
uv run mycel-ui               # demo dashboard → http://localhost:7860
```

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

```bash
uv run mycel-ask "What is the relationship between energy consumption patterns and research output at MICE over the last decade?"
uv run mycel-ask "What exactly did Tower A consume in 2024?"   # → blocked
uv run mycel-ask "Who runs the Alchemy Lab?"                   # → name redacted
uv run mycel-ask "..." --strategy judgment                     # COMSOC aggregation
./scripts/demo.sh                                              # all demo queries
```

## Node API

| Endpoint | Description |
|---|---|
| `POST /invoke` | `{"query": ...}` → policy-filtered answer + decision |
| `/mcp` | MCP (streamable HTTP) exposing the node's record tools |
| `GET /health` | liveness |

Every policy decision is appended to an audit log (`/var/log/diplomat/audit.log`
in the container) — query hashes only, never content.

## Development

```bash
uv sync                                  # install
uv run pytest                            # Python tests
opa test opa/energy opa/commons opa/archives   # policy tests
NODE_CONFIG=nodes/energy.yaml uv run diplomat  # run one node locally
```

See [.claude/PROJECT.md](.claude/PROJECT.md) for architecture decisions and roadmap.
