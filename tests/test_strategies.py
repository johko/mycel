from types import SimpleNamespace

import pytest

from mycel.orchestrator import strategies
from mycel.orchestrator.planner import PlannedCall
from mycel.orchestrator.strategies import (
    DEFAULT_STRATEGY,
    LLMSynthesisStrategy,
    make_strategy,
)
from mycel.orchestrator.strategies.base import format_results
from mycel.schemas import InvokeResponse, PolicyDecision, PolicyViolation


def _result(node_id, answer, *, decision=None, error=None):
    response = None
    if error is None:
        response = InvokeResponse(
            node_id=node_id,
            answer=answer,
            policy_decision=decision or PolicyDecision(allowed=True),
        )
    return {
        "call": PlannedCall(node_id=node_id, query="q"),
        "response": response,
        "error": error,
    }


def test_make_strategy_default():
    strat = make_strategy()
    assert isinstance(strat, LLMSynthesisStrategy)
    assert strat.name == DEFAULT_STRATEGY == "llm"


def test_make_strategy_unknown_rejected():
    with pytest.raises(ValueError, match="unknown strategy"):
        make_strategy("nope")


def test_format_results_renders_policy_and_errors():
    results = [
        _result(
            "energy-wizards",
            "Trend is up.",
            decision=PolicyDecision(
                allowed=True,
                redactions=[PolicyViolation(record="AGG-1", field="raw")],
                obligations=["cite Commons Scholars"],
                reason="aggregates only",
            ),
        ),
        _result("archivists", "", error="connection refused"),
    ]
    text = format_results(results)
    assert "## energy-wizards" in text
    assert "Trend is up." in text
    assert "redacted: AGG-1.raw" in text
    assert "obligations: cite Commons Scholars" in text
    assert "Node unreachable: connection refused" in text


async def test_llm_synthesis_aggregate(monkeypatch):
    captured = {}

    async def fake_chat(client, *, messages, model, max_tokens):
        captured["messages"] = messages
        captured["model"] = model
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="combined answer"))]
        )

    monkeypatch.setattr(strategies.llm_synthesis, "get_client", lambda: object())
    monkeypatch.setattr(strategies.llm_synthesis, "chat_with_retry", fake_chat)

    strat = make_strategy("llm", model="test-model")
    result = await strat.aggregate("what happened?", [_result("energy-wizards", "up")])

    assert result.summary == "combined answer"
    assert result.facts == []
    assert captured["model"] == "test-model"
    assert "what happened?" in captured["messages"][1]["content"]
