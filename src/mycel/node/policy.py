"""
OPA policy client and audit logger.

The policy input is the outgoing answer text plus the agent's observation log
(every tool call and its result). OPA returns a verdict on the *text itself* —
deny, redact, or attach obligations — so sensitive values cannot leak through
prose. Every decision is appended to an audit log; the log records which fields
were involved, never the sensitive values.

For convenience, `records` is also derived from the observation log (the
reference connector's `get_record` results, keyed by id) so a company can write
a policy against either shape: the generic `input.observations` or the
record-oriented `input.records`.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import httpx

from mycel.node.config import NodeConfig
from mycel.schemas import PolicyDecision

_audit_logger = logging.getLogger("diplomat.audit")
_audit_logger.propagate = False


def configure_audit_log(path: str | Path) -> None:
    log_path = Path(path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_path)
    handler.setFormatter(logging.Formatter("%(message)s"))
    _audit_logger.handlers.clear()
    _audit_logger.addHandler(handler)
    _audit_logger.setLevel(logging.INFO)


def _records_from_observations(observations: list[dict]) -> dict[str, dict]:
    """Reconstruct a {id: record} map from `get_record` observations.

    Lets the record-oriented reference policies read `input.records` unchanged,
    while the generic `input.observations` covers any other connector's tools.
    """
    records: dict[str, dict] = {}
    for obs in observations:
        if obs.get("tool") != "get_record":
            continue
        result = obs.get("result")
        rec_id = (obs.get("arguments") or {}).get("id")
        if isinstance(rec_id, str) and isinstance(result, dict) and "error" not in result:
            records[rec_id] = result
    return records


async def evaluate_policy(
    raw: dict, config: NodeConfig
) -> tuple[PolicyDecision, str]:
    """
    Send {'answer', 'observations', 'records'} to OPA, return (decision, safe_answer).

    The safe answer comes from OPA: original text if clean, text with
    sensitive substrings replaced for redaction policies, or empty on deny.
    """
    observations = raw.get("observations", [])
    opa_input = {
        "answer": raw.get("answer", ""),
        "observations": observations,
        "records": _records_from_observations(observations),
    }
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.post(
            f"{config.opa_url}/v1/data/diplomat/result",
            json={"input": opa_input},
        )
        resp.raise_for_status()
        result = resp.json().get("result")

    if result is None:
        raise RuntimeError("OPA returned no result — is the policy loaded?")

    decision = PolicyDecision(
        allowed=result["allow"],
        redactions=result.get("redactions", []),
        violations=result.get("violations", []),
        obligations=result.get("obligations", []),
        reason=result.get("reason"),
    )
    return decision, result.get("answer", "")


def log_decision(query: str, decision: PolicyDecision) -> None:
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "query_hash": hashlib.sha256(query.encode()).hexdigest()[:16],
        "allowed": decision.allowed,
        "violations": [v.model_dump() for v in decision.violations],
        "redactions": [r.model_dump() for r in decision.redactions],
        "obligations": decision.obligations,
        "reason": decision.reason,
    }
    _audit_logger.info(json.dumps(entry))
