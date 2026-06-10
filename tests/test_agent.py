"""Agent tool loop against a fake HF Inference client."""

import json
from types import SimpleNamespace

from mycel.node.agent import run_agent
from mycel.node.datastore import DataStore


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


async def test_run_agent_tool_loop(node_config, monkeypatch):
    client = FakeClient(
        [
            _tool_call_response("get_record", json.dumps({"id": "R1"})),
            _text_response("R1 has value 42."),
        ]
    )
    monkeypatch.setattr("mycel.node.agent.get_client", lambda: client)

    store = DataStore(node_config.data_path)
    result = await run_agent("what is R1?", node_config, store)

    assert result["answer"] == "R1 has value 42."
    # the touched record is surfaced for the policy layer
    assert result["records"] == {"R1": store.get_record("R1")}

    # second request must carry the assistant tool call and the tool result
    followup = client.requests[1]["messages"]
    assert followup[-2]["role"] == "assistant"
    assert followup[-2]["tool_calls"][0]["function"]["name"] == "get_record"
    assert followup[-1]["role"] == "tool"
    assert json.loads(followup[-1]["content"])["value"] == 42


async def test_run_agent_missing_record_not_touched(node_config, monkeypatch):
    client = FakeClient(
        [
            _tool_call_response("get_record", {"id": "NOPE"}),
            _text_response("No such record."),
        ]
    )
    monkeypatch.setattr("mycel.node.agent.get_client", lambda: client)

    store = DataStore(node_config.data_path)
    result = await run_agent("what is NOPE?", node_config, store)

    assert result["answer"] == "No such record."
    assert result["records"] == {}
