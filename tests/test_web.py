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
    monkeypatch.setattr(web, "build_graph", lambda registry, model: StubGraph())
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
