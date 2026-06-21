"""
Diplomat node — FastAPI entrypoint.

The agent connects out to a remote MCP server (the company's data connector)
for data, then — when an OPA endpoint is configured — every /invoke response
passes through the policy layer before leaving, so the agent's raw output
never crosses the container boundary.
"""

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from mycel.node.agent import build_structured_answer, observed_record_ids, run_agent
from mycel.node.config import NodeConfig, load_config
from mycel.node.mcp_client import connect_toolset
from mycel.node.policy import configure_audit_log, evaluate_policy, log_decision
from mycel.schemas import InvokeRequest, InvokeResponse, PolicyDecision


def _policy_caveats(decision: PolicyDecision) -> list[str]:
    """Policy-imposed limitations on the answer, for the structured view."""
    caveats: list[str] = []
    if not decision.allowed:
        caveats.append(
            f"answer blocked by policy{f': {decision.reason}' if decision.reason else ''}"
        )
    for r in decision.redactions:
        caveats.append(f"redacted by policy: {r.record}.{r.field}")
    if decision.allowed and decision.reason:
        caveats.append(decision.reason)
    return caveats


def create_app(config: NodeConfig | None = None) -> FastAPI:
    config = config or load_config()
    configure_audit_log(config.audit_log_path)
    state: dict[str, object] = {}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if config.mcp is None:
            raise RuntimeError(
                "no MCP server configured for this node (set mcp.url or MCP_URL)"
            )
        async with connect_toolset(config.mcp) as toolset:
            state["toolset"] = toolset
            logging.getLogger("diplomat").info(
                "connected to MCP server %s, tools: %s",
                config.mcp.url,
                toolset.tool_names,
            )
            yield

    app = FastAPI(title=f"Diplomat Agent — {config.title}", lifespan=lifespan)

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok", "node": config.id})

    @app.post("/invoke", response_model=InvokeResponse)
    async def invoke(request: InvokeRequest) -> InvokeResponse:
        try:
            raw = await run_agent(request.query, config, state.get("toolset"))
        except Exception as exc:
            logging.getLogger("diplomat").exception("agent error")
            raise HTTPException(status_code=500, detail=f"Agent error: {exc}") from exc

        if config.opa_url:
            try:
                toolset = state.get("toolset")
                records = (
                    await toolset.policy_view(raw.get("observations", []))
                    if toolset is not None
                    else {}
                )
                decision, safe_answer = await evaluate_policy(raw, config, records)
            except Exception as exc:
                logging.getLogger("diplomat").exception("policy check failed")
                raise HTTPException(
                    status_code=502, detail=f"Policy check failed: {exc}"
                ) from exc
            log_decision(request.query, decision)
        else:
            # no egress safety net configured — answer leaves as-is
            decision = PolicyDecision(allowed=True)
            safe_answer = raw.get("answer", "")

        structured = await build_structured_answer(
            safe_answer,
            observed_record_ids(raw.get("observations", [])),
            _policy_caveats(decision),
            config,
        )

        return InvokeResponse(
            node_id=config.id,
            answer=safe_answer,
            structured_answer=structured,
            policy_decision=decision,
        )

    return app


def run() -> None:
    from dotenv import load_dotenv

    load_dotenv()  # for running a node outside docker
    uvicorn.run(
        "mycel.node.main:create_app",
        factory=True,
        host="0.0.0.0",
        port=8000,
        reload=False,
    )
