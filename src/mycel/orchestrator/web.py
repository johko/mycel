"""
Web UI for the MICE demo.

Serves the single-page federation dashboard and streams orchestration
progress over SSE: plan → per-node policy verdicts → synthesized answer.
The events come from the graph's custom stream channel (see graph.py).
"""

import json
import os
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from mycel.orchestrator.graph import NODE_TIMEOUT, _invoke_node, _result_event, build_graph
from mycel.orchestrator.planner import DEFAULT_MODEL, PlannedCall
from mycel.orchestrator.registry import load_registry
from mycel.orchestrator.strategies import (
    DEFAULT_STRATEGY,
    STRATEGY_REGISTRY,
    make_strategy,
)

_STATIC_DIR = Path(__file__).parent / "static"


def create_app(
    registry_path: str | None = None,
    model: str = DEFAULT_MODEL,
    strategy: str | None = None,
) -> FastAPI:
    registry = load_registry(
        registry_path or os.environ.get("REGISTRY_PATH", "registry.yaml")
    )
    default_strategy = strategy or os.environ.get("MYCEL_STRATEGY", DEFAULT_STRATEGY)

    # one compiled graph per strategy, built lazily and reused across requests
    graphs: dict[str, object] = {}

    def graph_for(name: str | None):
        name = name or default_strategy
        if name not in STRATEGY_REGISTRY:
            raise HTTPException(status_code=400, detail=f"unknown strategy {name!r}")
        if name not in graphs:
            graphs[name] = build_graph(registry, model, make_strategy(name, model))
        return graphs[name]

    app = FastAPI(title="Mycel — MICE Federation UI")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(_STATIC_DIR / "index.html")

    @app.get("/api/registry")
    async def get_registry() -> dict:
        return registry.model_dump()

    @app.get("/api/strategies")
    async def get_strategies() -> dict:
        return {
            "default": default_strategy,
            "strategies": [
                {
                    "name": name,
                    "label": getattr(cls, "label", name),
                    "description": getattr(cls, "description", ""),
                }
                for name, cls in STRATEGY_REGISTRY.items()
            ],
        }

    @app.get("/api/ask")
    async def ask(question: str, strategy: str | None = None) -> StreamingResponse:
        graph = graph_for(strategy)

        async def stream():
            try:
                async for event in graph.astream(
                    {"question": question}, stream_mode="custom"
                ):
                    yield f"data: {json.dumps(event)}\n\n"
            except Exception as exc:
                yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
            yield 'data: {"type": "done"}\n\n'

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/direct")
    async def direct(node_id: str, question: str) -> StreamingResponse:
        """Bypass the planner and interrogate a single node — shows raw policy enforcement."""
        entry = registry.get(node_id)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"unknown node {node_id!r}")

        async def stream():
            call = PlannedCall(node_id=node_id, query=question)
            yield f"data: {json.dumps({'type': 'node_start', 'node_id': node_id, 'query': question})}\n\n"
            async with httpx.AsyncClient(timeout=NODE_TIMEOUT) as client:
                result = await _invoke_node(client, entry.endpoint, call)
            yield f"data: {json.dumps(_result_event(result))}\n\n"
            yield 'data: {"type": "done"}\n\n'

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


def run() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    uvicorn.run(
        "mycel.orchestrator.web:create_app",
        factory=True,
        host="0.0.0.0",
        # 7860 — the Hugging Face Spaces default, in keeping with the showcase
        port=int(os.environ.get("UI_PORT", "7860")),
    )
