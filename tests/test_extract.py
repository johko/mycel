"""Structured-fact extraction from the policy-filtered answer."""

import json
from types import SimpleNamespace

from mycel.node.agent import build_structured_answer, extract_facts


def _facts_response(arguments) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            id="call_1",
                            function=SimpleNamespace(
                                name="submit_facts", arguments=arguments
                            ),
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


async def test_extract_facts_parses_tool_call(node_config, monkeypatch):
    client = FakeClient(
        [
            _facts_response(
                json.dumps(
                    {
                        "facts": [
                            {
                                "claim": "Tower A consumption rose",
                                "value": 12,
                                "unit": "%",
                                "confidence": 0.9,
                                "source_record": "AGG-1",
                            }
                        ]
                    }
                )
            )
        ]
    )
    monkeypatch.setattr("mycel.node.agent.get_client", lambda: client)

    facts = await extract_facts(
        "Tower A consumption rose 12% last year.", ["AGG-1"], node_config
    )

    assert len(facts) == 1
    assert facts[0].value == 12
    assert facts[0].unit == "%"
    assert facts[0].source_record == "AGG-1"
    # extraction must be a forced submit_facts tool call
    assert client.requests[0]["tool_choice"]["function"]["name"] == "submit_facts"


async def test_extract_facts_empty_answer_skips_llm(node_config, monkeypatch):
    client = FakeClient([])  # would IndexError if the LLM were called
    monkeypatch.setattr("mycel.node.agent.get_client", lambda: client)

    facts = await extract_facts("   ", ["R1"], node_config)

    assert facts == []
    assert client.requests == []


async def test_extract_facts_returns_empty_when_no_tool_call(node_config, monkeypatch):
    client = FakeClient([_text_response("no tools"), _text_response("still none")])
    monkeypatch.setattr("mycel.node.agent.get_client", lambda: client)

    facts = await extract_facts("some answer", ["R1"], node_config)

    assert facts == []


async def test_build_structured_answer_wraps_caveats(node_config, monkeypatch):
    client = FakeClient([_facts_response(json.dumps({"facts": []}))])
    monkeypatch.setattr("mycel.node.agent.get_client", lambda: client)

    structured = await build_structured_answer(
        "aggregates only", ["AGG-1"], ["aggregates only — raw values blocked"], node_config
    )

    assert structured is not None
    assert structured.summary == "aggregates only"
    assert structured.caveats == ["aggregates only — raw values blocked"]


async def test_build_structured_answer_none_on_failure(node_config, monkeypatch):
    async def boom():
        raise RuntimeError("inference down")

    def get_client():
        raise RuntimeError("inference down")

    monkeypatch.setattr("mycel.node.agent.get_client", get_client)

    structured = await build_structured_answer(
        "non-empty answer", ["R1"], [], node_config
    )

    assert structured is None
