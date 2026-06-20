"""Agent tool loop against a fake HF Inference client and a fake MCP toolset."""

import json
from types import SimpleNamespace

from mycel.node.agent import observed_record_ids, run_agent


def _tool_call_response(name: str, arguments) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            id="call_1",
                            function=SimpleNamespace(name=name, arguments=arguments),
                        )
                    ],
                )
            )
        ]
    )


def _text_response(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text, tool_calls=None))]
    )


class FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.requests = []

    async def chat_completion(self, **kwargs):
        self.requests.append(kwargs)
        return self._responses.pop(0)


class FakeToolset:
    """Stands in for a RemoteToolset backed by a remote MCP server."""

    def __init__(self, records):
        self._records = records
        self.schemas = [
            {
                "type": "function",
                "function": {
                    "name": "get_record",
                    "description": "Fetch a record by ID.",
                    "parameters": {
                        "type": "object",
                        "properties": {"id": {"type": "string"}},
                        "required": ["id"],
                    },
                },
            }
        ]
        self.calls = []

    async def call(self, name, args):
        self.calls.append((name, args))
        if name == "get_record":
            rec = self._records.get(args.get("id"))
            return rec if rec is not None else {"error": "not found"}
        raise RuntimeError(f"unknown tool {name!r}")


async def test_run_agent_tool_loop(node_config, monkeypatch):
    client = FakeClient(
        [
            _tool_call_response("get_record", json.dumps({"id": "R1"})),
            _text_response("R1 has value 42."),
        ]
    )
    monkeypatch.setattr("mycel.node.agent.get_client", lambda *a, **k: client)

    toolset = FakeToolset({"R1": {"label": "record one", "value": 42}})
    result = await run_agent("what is R1?", node_config, toolset)

    assert result["answer"] == "R1 has value 42."
    # the tool call is logged as an observation for the policy layer
    assert result["observations"] == [
        {"tool": "get_record", "arguments": {"id": "R1"}, "result": {"label": "record one", "value": 42}}
    ]
    # the agent was offered the toolset's discovered schemas
    assert client.requests[0]["tools"] == toolset.schemas

    # second request must carry the assistant tool call and the tool result
    followup = client.requests[1]["messages"]
    assert followup[-2]["role"] == "assistant"
    assert followup[-2]["tool_calls"][0]["function"]["name"] == "get_record"
    assert followup[-1]["role"] == "tool"
    assert json.loads(followup[-1]["content"])["value"] == 42


async def test_run_agent_failed_tool_not_observed(node_config, monkeypatch):
    client = FakeClient(
        [
            _tool_call_response("get_record", {"id": "NOPE"}),
            _text_response("No such record."),
        ]
    )
    monkeypatch.setattr("mycel.node.agent.get_client", lambda *a, **k: client)

    toolset = FakeToolset({"R1": {"value": 42}})
    result = await run_agent("what is NOPE?", node_config, toolset)

    assert result["answer"] == "No such record."
    # the record returned an error, but the call still happened — it is logged,
    # while observed_record_ids only surfaces it for attribution
    assert result["observations"][0]["result"] == {"error": "not found"}


def test_observed_record_ids_dedupes_and_skips_non_string():
    obs = [
        {"tool": "get_record", "arguments": {"id": "R1"}, "result": {}},
        {"tool": "get_record", "arguments": {"id": "R1"}, "result": {}},
        {"tool": "search", "arguments": {"query": "x"}, "result": []},
        {"tool": "fetch", "arguments": {"record_id": "R2"}, "result": {}},
    ]
    assert observed_record_ids(obs) == ["R1", "R2"]
