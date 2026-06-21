```mermaid
graph TD
    CLI["mycel-ask CLI"]
    UI["mycel-ui Web UI"]

    subgraph Orch["ORCHESTRATOR"]
        Registry["Node Registry (registry.yaml)"]
        Planner["LLM Planner · PlannedCall list"]
        Graph["LangGraph Workflow\nPlan → Execute → Synthesize"]
        Strat["Aggregation Strategies\nllm | median | judgment"]
    end

    subgraph NodeA["DIPLOMAT NODE A — shipped container (no data)"]
        InvokeA["/invoke  (FastAPI)"]
        AgentA["LLM Agent\nMCP client · tool-calling loop"]
        ExtractA["Fact Extractor"]
    end

    subgraph CoA["COMPANY A ENVIRONMENT"]
        MCPA["MCP Server /mcp\n(reference connector or company's own)"]
        DSA["Data sources\nreference: JSON · SQLite · Qdrant RAG"]
        PolicyA["OPA Policy (company-owned rego)\nallow / redact / deny — egress safety net"]
    end

    subgraph Ext["SHARED SERVICES"]
        LLM["LLM Inference\nHuggingFace / Ollama"]
        Cfg["Node Config (YAML)\nDeviceProfile · BackendConfig · MCP url"]
    end

    CLI --> Orch
    UI --> Orch
    Registry --> Planner
    Planner --> Graph
    Graph --> Strat
    Graph -->|"HTTP POST /invoke · asyncio.gather()"| NodeA

    InvokeA --> AgentA
    AgentA -->|"MCP: list_tools / call_tool"| MCPA
    MCPA -->|"company controls what is exposed"| DSA
    AgentA -->|"answer + observation log"| InvokeA
    InvokeA -->|"POST /v1/data/diplomat/result"| PolicyA
    PolicyA -->|"safe answer"| ExtractA
    ExtractA --> InvokeA
    AgentA --> LLM

    Cfg -.->|"BackendConfig · mcp.url"| AgentA
```

## How a company integrates a node

1. **Run the agent container** we ship. It contains the LLM agent, the `/invoke`
   API, and the fact extractor — **no company data**.
2. **Point it at an MCP server** via `MCP_URL` (+ optional `MCP_AUTH_TOKEN`). That
   server is the company's data connector: either the bundled *reference connector*
   (`connector` entrypoint, with a `CONNECTOR_KIND` of `json`, `sql`, or `rag`) or
   the company's own MCP server exposing their real data sources. The agent discovers
   whatever tools it offers at runtime — different backends expose different tool
   surfaces (record fetch, SQL query, semantic search), and the company decides exactly
   what the agent can and cannot see.
3. **(Optional) configure an egress policy** via `OPA_URL`, mounting their own rego.
   The agent's outgoing answer is judged against its observation log before it leaves
   the container — a safety net for highly sensitive data on top of the connector's
   ingress control. Policies can read the generic `input.observations` (the raw tool
   call log), or `input.records` — a canonical `{id: record}` view the connector
   supplies by implementing the well-known **`policy_view`** tool. Because the
   connector owns its data shapes, `policy_view` lets one rego govern any backend
   (the reference JSON/SQL/RAG connectors each map their results to the same record
   shape, so the demo's deny/redact/oblige policies are identical across all three).
   If no `OPA_URL` is set, the node runs without an egress check.

Data sovereignty is therefore enforced twice: at **ingress** (the company's MCP server
only exposes what it chooses) and, optionally, at **egress** (the company's OPA rego
vets the outgoing text).
