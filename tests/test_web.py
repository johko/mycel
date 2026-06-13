"""Web UI backend: registry endpoint, index page, SSE event stream."""

import json

import httpx
import pytest

from mycel.orchestrator import web

REGISTRY_YAML = """\
nodes:
  - id: energy-wizards
    title: Energy Wizards
    description: Energy data, aggregates only.
    endpoint: http://localhost:8001
    policy_mode: deny
"""


class StubGraph:
    async def astream(self, state, stream_mode=None):
        assert stream_mode == "custom"
        yield {"type": "plan", "calls": [{"node_id": "energy-wizards", "query": "q"}]}
        yield {"type": "final", "answer": f"answer to: {state['question']}"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(REGISTRY_YAML)
    monkeypatch.setattr(web, "build_graph", lambda *args, **kwargs: StubGraph())
    app = web.create_app(registry_path=str(registry_path))
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_index_served(client):
    async with client:
        resp = await client.get("/")
    assert resp.status_code == 200
    assert "MICE" in resp.text


async def test_registry_endpoint(client):
    async with client:
        resp = await client.get("/api/registry")
    nodes = resp.json()["nodes"]
    assert nodes[0]["id"] == "energy-wizards"
    assert nodes[0]["policy_mode"] == "deny"


async def test_ask_streams_events(client):
    async with client:
        resp = await client.get("/api/ask", params={"question": "hello"})
    assert resp.headers["content-type"].startswith("text/event-stream")
    events = [
        json.loads(line[len("data: "):])
        for line in resp.text.splitlines()
        if line.startswith("data: ")
    ]
    assert [e["type"] for e in events] == ["plan", "final", "done"]
    assert events[1]["answer"] == "answer to: hello"


async def test_strategies_endpoint_lists_registry(client):
    async with client:
        resp = await client.get("/api/strategies")
    body = resp.json()
    assert body["default"] == "llm"
    names = {s["name"] for s in body["strategies"]}
    assert {"llm", "judgment", "median"} <= names
    # labels/descriptions are surfaced for the UI
    assert all(s["label"] and s["description"] for s in body["strategies"])


async def test_ask_accepts_strategy_param(tmp_path, monkeypatch):
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(REGISTRY_YAML)
    seen = []
    monkeypatch.setattr(
        web,
        "build_graph",
        lambda registry, model, strat: seen.append(strat.name) or StubGraph(),
    )
    app = web.create_app(registry_path=str(registry_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/ask", params={"question": "hi", "strategy": "judgment"})
        assert resp.status_code == 200
        # unknown strategy is rejected before streaming
        bad = await c.get("/api/ask", params={"question": "hi", "strategy": "nope"})
        assert bad.status_code == 400

    assert "judgment" in seen
