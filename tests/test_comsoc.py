"""Computational-social-choice strategies: alignment, judgment, median."""

from types import SimpleNamespace

import pytest

from mycel.orchestrator.planner import PlannedCall
import json

from mycel.orchestrator.strategies import _align, judgment, majority_judgment
from mycel.orchestrator.strategies._align import (
    Issue,
    Position,
    _align_by_string,
    _build_issues,
    _collect_positions,
    align_claims,
    participants,
)
from mycel.orchestrator.strategies.judgment import JudgmentAggregationStrategy
from mycel.orchestrator.strategies.majority_judgment import (
    MajorityJudgmentStrategy,
    _coerce_number,
    _lower_median,
    _weighted_median,
)
from mycel.schemas import Fact, InvokeResponse, PolicyDecision, StructuredAnswer


def _result(node_id, facts):
    return {
        "call": PlannedCall(node_id=node_id, query="q"),
        "response": InvokeResponse(
            node_id=node_id,
            answer="prose",
            structured_answer=StructuredAnswer(facts=facts, summary="prose"),
            policy_decision=PolicyDecision(allowed=True),
        ),
        "error": None,
    }


def _pos(node_id, claim, value=None, confidence=1.0):
    return Position(node_id=node_id, claim=claim, value=value, confidence=confidence)


# ---- alignment helpers -------------------------------------------------------


def test_collect_positions_skips_unstructured():
    results = [
        _result("a", [Fact(claim="x", value=1)]),
        {"call": PlannedCall(node_id="b", query="q"), "response": None, "error": "down"},
    ]
    positions = _collect_positions(results)
    assert [p.node_id for p in positions] == ["a"]


def test_align_by_string_groups_identical_claims():
    positions = [
        _pos("a", "Energy use rose"),
        _pos("b", "energy use rose"),  # same after normalization
        _pos("c", "Papers increased"),
    ]
    issues = _align_by_string(positions)
    assert len(issues) == 2
    rose = next(i for i in issues if "rose" in i.label.lower())
    assert {p.node_id for p in rose.positions} == {"a", "b"}


def test_build_issues_keeps_unassigned_as_singletons():
    positions = [_pos("a", "c0"), _pos("b", "c1"), _pos("c", "c2")]
    raw = [{"label": "grouped", "fact_indices": [0, 1]}]  # index 2 left out
    issues = _build_issues(raw, positions)
    assert len(issues) == 2
    singleton = next(i for i in issues if i.label == "c2")
    assert singleton.positions[0].node_id == "c"


def test_by_node_keeps_highest_confidence():
    issue = Issue(
        label="i",
        positions=[_pos("a", "c", value=1, confidence=0.3), _pos("a", "c", value=2, confidence=0.8)],
    )
    by = issue.by_node()
    assert set(by) == {"a"}
    assert by["a"].confidence == 0.8


def test_participants_counts_distinct_nodes():
    issues = [
        Issue(label="i1", positions=[_pos("a", "c"), _pos("b", "c")]),
        Issue(label="i2", positions=[_pos("b", "c"), _pos("c", "c")]),
    ]
    assert participants(issues) == {"a", "b", "c"}


# ---- align_claims LLM path + fallback ---------------------------------------


def _alignment_response(arguments):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            id="c1",
                            function=SimpleNamespace(
                                name="submit_alignment", arguments=arguments
                            ),
                        )
                    ],
                )
            )
        ]
    )


class _FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)

    async def chat_completion(self, **kwargs):
        resp = self._responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp


async def test_align_claims_uses_llm_clustering(monkeypatch):
    results = [
        _result("a", [Fact(claim="energy rose")]),
        _result("b", [Fact(claim="energy went up")]),
    ]
    client = _FakeClient(
        [_alignment_response(json.dumps({"issues": [{"label": "energy rose", "fact_indices": [0, 1]}]}))]
    )
    monkeypatch.setattr(_align, "get_client", lambda: client)

    issues = await align_claims("q", results, "m")

    assert len(issues) == 1
    assert {p.node_id for p in issues[0].positions} == {"a", "b"}


async def test_align_claims_falls_back_to_string_on_error(monkeypatch):
    results = [_result("a", [Fact(claim="X")]), _result("b", [Fact(claim="x")])]

    async def boom(*args, **kwargs):
        raise RuntimeError("inference down")

    monkeypatch.setattr(_align, "get_client", lambda: object())
    monkeypatch.setattr(_align, "chat_with_retry", boom)

    issues = await align_claims("q", results, "m")

    # string fallback groups the two identical claims into one issue
    assert len(issues) == 1
    assert {p.node_id for p in issues[0].positions} == {"a", "b"}


async def test_align_claims_empty_without_facts():
    results = [
        {"call": PlannedCall(node_id="a", query="q"), "response": None, "error": "down"}
    ]
    assert await align_claims("q", results, "m") == []


# ---- median helpers ----------------------------------------------------------


def test_lower_median():
    assert _lower_median([3, 1, 2]) == 2
    assert _lower_median([1, 2, 3, 4]) == 2  # lower of the two middle
    assert _lower_median([]) is None


def test_weighted_median_respects_weight():
    # the heavy value wins even though it is the largest
    assert _weighted_median([(10, 0.1), (20, 0.1), (100, 0.9)]) == 100
    # equal weights -> lower median
    assert _weighted_median([(10, 1), (20, 1)]) == 10


def test_coerce_number():
    assert _coerce_number("12.5") == 12.5
    assert _coerce_number(7) == 7.0
    assert _coerce_number(True) is None
    assert _coerce_number("up") is None


# ---- strategies (alignment + prose mocked) -----------------------------------


@pytest.fixture
def no_prose(monkeypatch):
    async def fake_prose(question, context, model, system_prompt):
        fake_prose.context = context
        return "PROSE"

    monkeypatch.setattr(judgment, "synthesize_prose", fake_prose)
    monkeypatch.setattr(majority_judgment, "synthesize_prose", fake_prose)
    return fake_prose


def _patch_align(monkeypatch, module, issues):
    async def fake_align(question, results, model):
        return issues

    monkeypatch.setattr(module, "align_claims", fake_align)


async def test_judgment_accepts_majority_value_and_flags_dissent(monkeypatch, no_prose):
    # 3 voters on one issue: two agree on "12%", one dissents with "20%"
    issues = [
        Issue(
            label="energy rose",
            positions=[
                _pos("a", "rose", value="12%", confidence=1.0),
                _pos("b", "rose", value="12%", confidence=1.0),
                _pos("c", "rose", value="20%", confidence=1.0),
            ],
        )
    ]
    _patch_align(monkeypatch, judgment, issues)

    result = await JudgmentAggregationStrategy("m").aggregate("q", [])

    assert result.summary == "PROSE"
    assert result.facts == [
        {"issue": "energy rose", "value": "12%", "supporters": ["a", "b"]}
    ]
    assert result.node_attribution["energy rose"] == ["a", "b", "c"]
    # majority won but the dissent is recorded
    assert len(result.conflicts) == 1
    assert result.conflicts[0]["decided"] == "12%"
    assert result.conflicts[0]["positions"] == {"a": "12%", "b": "12%", "c": "20%"}


async def test_judgment_contested_when_no_majority_value(monkeypatch, no_prose):
    # 3 voters, 3 distinct values -> no majority -> contested, nothing accepted
    issues = [
        Issue(
            label="consumption",
            positions=[
                _pos("a", "c", value=100, confidence=1.0),
                _pos("b", "c", value=200, confidence=1.0),
                _pos("c", "c", value=300, confidence=1.0),
            ],
        )
    ]
    _patch_align(monkeypatch, judgment, issues)

    result = await JudgmentAggregationStrategy("m").aggregate("q", [])

    assert result.facts == []
    assert len(result.conflicts) == 1
    assert result.conflicts[0]["decided"] is None
    assert result.conflicts[0]["positions"] == {"a": 100, "b": 200, "c": 300}


async def test_judgment_lone_voter_is_accepted(monkeypatch, no_prose):
    # only the nodes that opined vote: a single uncontested voter carries it
    issues = [Issue(label="solo", positions=[_pos("a", "solo", value=7, confidence=1.0)])]
    _patch_align(monkeypatch, judgment, issues)

    result = await JudgmentAggregationStrategy("m").aggregate("q", [])

    assert result.facts == [{"issue": "solo", "value": 7, "supporters": ["a"]}]
    assert result.conflicts == []


async def test_judgment_confidence_weight_breaks_tie(monkeypatch, no_prose):
    # two distinct values, equal count, but one voter is more confident -> wins
    issues = [
        Issue(
            label="staff",
            positions=[
                _pos("archives", "staff", value=67, confidence=0.9),
                _pos("bursar", "staff", value=64, confidence=0.5),
            ],
        )
    ]
    _patch_align(monkeypatch, judgment, issues)

    result = await JudgmentAggregationStrategy("m").aggregate("q", [])

    assert result.facts == [
        {"issue": "staff", "value": 67, "supporters": ["archives"]}
    ]
    # unweighted, the same split is a tie -> contested
    unweighted = await JudgmentAggregationStrategy(
        "m", confidence_weighted=False
    ).aggregate("q", [])
    assert unweighted.facts == []


async def test_median_computes_weighted_median_and_spread(monkeypatch, no_prose):
    issues = [
        Issue(
            label="tower A kWh",
            positions=[
                _pos("a", "kWh", value=100, confidence=0.2),
                _pos("b", "kWh", value=900, confidence=0.9),
                _pos("c", "kWh", value=120, confidence=0.3),
            ],
        )
    ]
    _patch_align(monkeypatch, majority_judgment, issues)

    result = await MajorityJudgmentStrategy("m").aggregate("q", [])

    fact = result.facts[0]
    assert fact["issue"] == "tower A kWh"
    assert fact["spread"] == [100, 900]
    assert fact["voters"] == ["a", "b", "c"]
    # weighted median: total weight 1.4, half 0.7; sorted 100(.2),120(.3),900(.9)
    # cumulative crosses 0.7 at 900
    assert fact["value"] == 900
    assert fact["grade"] == _lower_median([0.2, 0.9, 0.3])


async def test_median_handles_non_numeric_values(monkeypatch, no_prose):
    issues = [
        Issue(
            label="trend",
            positions=[_pos("a", "trend", value="up", confidence=0.5), _pos("b", "trend", value="up", confidence=0.7)],
        )
    ]
    _patch_align(monkeypatch, majority_judgment, issues)

    result = await MajorityJudgmentStrategy("m").aggregate("q", [])

    fact = result.facts[0]
    assert fact["value"] is None
    assert fact["spread"] is None
    assert fact["grade"] == 0.5  # lower median of [0.5, 0.7]


async def test_strategies_fall_back_to_prose_when_no_issues(monkeypatch):
    _patch_align(monkeypatch, judgment, [])

    async def fake_llm_aggregate(self, question, results):
        from mycel.orchestrator.strategies.base import AggregatedResult

        return AggregatedResult(summary="LLM FALLBACK")

    monkeypatch.setattr(
        "mycel.orchestrator.strategies.llm_synthesis.LLMSynthesisStrategy.aggregate",
        fake_llm_aggregate,
    )

    result = await JudgmentAggregationStrategy("m").aggregate("q", [])
    assert result.summary == "LLM FALLBACK"
