import json

import pytest
import respx
from httpx import Response

from mycel.node.policy import configure_audit_log, evaluate_policy, log_decision
from mycel.schemas import PolicyDecision, PolicyViolation


@respx.mock
async def test_evaluate_policy_allow(node_config):
    respx.post("http://opa.test/v1/data/diplomat/result").mock(
        return_value=Response(
            200,
            json={
                "result": {
                    "allow": True,
                    "answer": "all fine",
                    "obligations": ["cite sources"],
                }
            },
        )
    )
    decision, answer = await evaluate_policy(
        {"answer": "all fine", "records": {}}, node_config
    )
    assert decision.allowed
    assert answer == "all fine"
    assert decision.obligations == ["cite sources"]


@respx.mock
async def test_evaluate_policy_deny(node_config):
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
    decision, answer = await evaluate_policy(
        {"answer": "the value is 42", "records": {}}, node_config
    )
    assert not decision.allowed
    assert answer == ""
    assert decision.violations[0].record == "R1"
    assert decision.reason == "blocked"


@respx.mock
async def test_evaluate_policy_missing_result_raises(node_config):
    respx.post("http://opa.test/v1/data/diplomat/result").mock(
        return_value=Response(200, json={})
    )
    with pytest.raises(RuntimeError, match="no result"):
        await evaluate_policy({"answer": "x", "records": {}}, node_config)


def test_audit_log_written(node_config):
    configure_audit_log(node_config.audit_log_path)
    decision = PolicyDecision(
        allowed=False,
        violations=[PolicyViolation(record="R1", field="value")],
        reason="blocked",
    )
    log_decision("what is the value of R1?", decision)

    entry = json.loads(node_config.audit_log_path.read_text().strip())
    assert entry["allowed"] is False
    assert entry["violations"] == [{"record": "R1", "field": "value"}]
    # the audit log must never contain the query text itself
    assert "value of R1" not in node_config.audit_log_path.read_text()
