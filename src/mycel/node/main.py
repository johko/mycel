"""
Diplomat node — FastAPI entrypoint.

Every /invoke response passes through the OPA sidecar before leaving;
the agent's raw output never crosses the container boundary.
"""

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from mycel.node.agent import build_structured_answer, run_agent
from mycel.node.config import NodeConfig, load_config
from mycel.node.datastore import DataStore
from mycel.node.mcp_server import build_mcp_server
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
    store = DataStore(config.data_path)
    configure_audit_log(config.audit_log_path)
    mcp = build_mcp_server(config, store)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with mcp.session_manager.run():
            yield

    app = FastAPI(title=f"Diplomat Agent — {config.title}", lifespan=lifespan)
    app.mount("/mcp", mcp.streamable_http_app())

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok", "node": config.id})

    @app.post("/invoke", response_model=InvokeResponse)
    async def invoke(request: InvokeRequest) -> InvokeResponse:
        try:
            raw = await run_agent(request.query, config, store)
        except Exception as exc:
            logging.getLogger("diplomat").exception("agent error")
            raise HTTPException(status_code=500, detail=f"Agent error: {exc}") from exc

        try:
            decision, safe_answer = await evaluate_policy(raw, config)
        except Exception as exc:
            logging.getLogger("diplomat").exception("policy check failed")
            raise HTTPException(
                status_code=502, detail=f"Policy check failed: {exc}"
            ) from exc

        log_decision(request.query, decision)

        structured = await build_structured_answer(
            safe_answer,
            list(raw.get("records", {}).keys()),
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
