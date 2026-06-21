"""
OPA policy client and audit logger.

The policy input is the outgoing answer text plus the agent's observation log
(every tool call and its result). OPA returns a verdict on the *text itself* —
deny, redact, or attach obligations — so sensitive values cannot leak through
prose. Every decision is appended to an audit log; the log records which fields
were involved, never the sensitive values.

`records` is the connector's canonical {id: record} view of what the agent
touched, supplied by the caller (via the connector's `policy_view` tool). It
lets record-oriented policies read `input.records`; it is `{}` for connectors
that don't implement `policy_view`, leaving the generic `input.observations` as
the policy surface.
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


async def evaluate_policy(
    raw: dict, config: NodeConfig, records: dict[str, dict] | None = None
) -> tuple[PolicyDecision, str]:
    """
    Send {'answer', 'observations', 'records'} to OPA, return (decision, safe_answer).

    `records` is the connector's canonical {id: record} view (from `policy_view`);
    pass `{}`/None for connectors that don't supply one. The safe answer comes
    from OPA: original text if clean, text with sensitive substrings replaced for
    redaction policies, or empty on deny.
    """
    opa_input = {
        "answer": raw.get("answer", ""),
        "observations": raw.get("observations", []),
        "records": records or {},
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
