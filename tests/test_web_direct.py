"""Direct node interrogation endpoint (planner bypass)."""

import json

import httpx
import pytest
import respx
from httpx import Response

from mycel.orchestrator import web

REGISTRY_YAML = """\
nodes:
  - id: energy-wizards
    title: Energy Wizards
    description: Energy data.
    endpoint: http://node.test
    policy_mode: deny
"""


@pytest.fixture
def client(tmp_path, monkeypatch):
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(REGISTRY_YAML)
    monkeypatch.setattr(web, "build_graph", lambda registry, model: None)
    app = web.create_app(registry_path=str(registry_path))
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@respx.mock
async def test_direct_streams_node_result(client):
    respx.post("http://node.test/invoke").mock(
        return_value=Response(
            200,
            json={
                "node_id": "energy-wizards",
                "answer": "",
                "policy_decision": {
                    "allowed": False,
                    "violations": [{"record": "E1", "field": "kwh"}],
                    "redactions": [],
                    "obligations": [],
                    "reason": "blocked",
                },
            },
        )
    )
    async with client:
        resp = await client.get(
            "/api/direct",
            params={"node_id": "energy-wizards", "question": "exact kWh?"},
        )
    events = [
        json.loads(line[len("data: "):])
        for line in resp.text.splitlines()
        if line.startswith("data: ")
    ]
    assert [e["type"] for e in events] == ["node_start", "node_result", "done"]
    assert events[1]["decision"]["allowed"] is False


async def test_direct_unknown_node(client):
    async with client:
        resp = await client.get(
            "/api/direct", params={"node_id": "nope", "question": "x"}
        )
    assert resp.status_code == 404
