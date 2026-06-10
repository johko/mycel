import json
from types import SimpleNamespace

import pytest

from mycel.orchestrator.planner import parse_plan
from mycel.orchestrator.registry import NodeEntry, Registry

registry = Registry(
    nodes=[
        NodeEntry(
            id="energy-wizards",
            title="Energy Wizards",
            description="Energy data.",
            endpoint="http://localhost:8001",
        )
    ]
)


def _fake_response(arguments) -> SimpleNamespace:
    """HF/OpenAI-style chat completion response with one submit_plan tool call."""
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            id="call_1",
                            function=SimpleNamespace(
                                name="submit_plan", arguments=arguments
                            ),
                        )
                    ],
                )
            )
        ]
    )


def test_parse_plan_string_arguments():
    response = _fake_response(
        json.dumps(
            {
                "calls": [
                    {
                        "node_id": "energy-wizards",
                        "query": "trends?",
                        "rationale": "need data",
                    }
                ]
            }
        )
    )
    plan = parse_plan(response, registry)
    assert len(plan) == 1
    assert plan[0].node_id == "energy-wizards"
    assert plan[0].query == "trends?"


def test_parse_plan_dict_arguments():
    # some providers return arguments already deserialized
    response = _fake_response(
        {"calls": [{"node_id": "energy-wizards", "query": "trends?"}]}
    )
    plan = parse_plan(response, registry)
    assert [c.node_id for c in plan] == ["energy-wizards"]


def test_parse_plan_drops_unknown_nodes():
    response = _fake_response(
        json.dumps(
            {
                "calls": [
                    {"node_id": "energy-wizards", "query": "trends?"},
                    {"node_id": "hallucinated-node", "query": "anything?"},
                ]
            }
        )
    )
    plan = parse_plan(response, registry)
    assert [c.node_id for c in plan] == ["energy-wizards"]


def test_parse_plan_without_tool_call_raises():
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="hi", tool_calls=None))]
    )
    with pytest.raises(ValueError, match="submit_plan"):
        parse_plan(response, registry)


def test_parse_plan_falls_back_to_inline_json():
    # provider ignored tool_choice but emitted the plan JSON in the content
    text = (
        "Here is my plan:\n"
        '{"calls": [{"node_id": "energy-wizards", "query": "trends?"}]}\n'
        "Let me know if that works."
    )
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text, tool_calls=None))]
    )
    plan = parse_plan(response, registry)
    assert [c.node_id for c in plan] == ["energy-wizards"]
