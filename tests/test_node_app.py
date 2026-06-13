"""Integration test of the /invoke seam: agent mocked, OPA mocked via respx."""

import httpx
import respx
from httpx import Response

from mycel.node.main import create_app


@respx.mock
async def test_invoke_routes_through_policy(node_config, monkeypatch):
    async def fake_agent(query, config, store):
        return {"answer": "the value is 42", "records": {"R1": store.get_record("R1")}}

    monkeypatch.setattr("mycel.node.main.run_agent", fake_agent)
    respx.post("http://opa.test/v1/data/diplomat/result").mock(
        return_value=Response(
            200,
            json={
                "result": {
                    "allow": False,
                    "answer": "",
                    "violations": [{"record": "R1", "field": "value"}],
                    "reason": "blocked",
                }
            },
        )
    )

    app = create_app(node_config)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/invoke", json={"query": "what is R1's value?"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["node_id"] == "test-node"
    assert body["answer"] == ""
    assert body["policy_decision"]["allowed"] is False
    # raw agent output must not appear anywhere in the response
    assert "42" not in resp.text


@respx.mock
async def test_invoke_includes_structured_answer(node_config, monkeypatch):
    async def fake_agent(query, config, store):
        return {"answer": "raw", "records": {"R1": store.get_record("R1")}}

    async def fake_structured(answer, record_ids, caveats, config):
        from mycel.schemas import Fact, StructuredAnswer

        return StructuredAnswer(
            facts=[Fact(claim="R2 is 7", value=7, source_record="R2")],
            summary=answer,
            caveats=caveats,
        )

    monkeypatch.setattr("mycel.node.main.run_agent", fake_agent)
    monkeypatch.setattr("mycel.node.main.build_structured_answer", fake_structured)
    respx.post("http://opa.test/v1/data/diplomat/result").mock(
        return_value=Response(
            200,
            json={
                "result": {
                    "allow": True,
                    "answer": "R2 is 7.",
                    "obligations": ["cite Commons Scholars"],
                }
            },
        )
    )

    app = create_app(node_config)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/invoke", json={"query": "what is R2?"})

    body = resp.json()
    assert body["answer"] == "R2 is 7."
    assert body["structured_answer"]["summary"] == "R2 is 7."
    assert body["structured_answer"]["facts"][0]["value"] == 7
    assert body["structured_answer"]["facts"][0]["source_record"] == "R2"


@respx.mock
async def test_health(node_config):
    app = create_app(node_config)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.json() == {"status": "ok", "node": "test-node"}
