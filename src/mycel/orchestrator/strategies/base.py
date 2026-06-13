"""
Aggregation strategy protocol.

Inspired by Flower's `Strategy`: the orchestrator hands a strategy the
full set of policy-filtered node results and gets back an
`AggregatedResult`. Swapping the strategy changes how node responses are
combined (LLM synthesis, structured union, conflict-aware, …) without
touching the graph.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from pydantic import BaseModel, Field

from mycel.schemas import PolicyDecision

if TYPE_CHECKING:
    from mycel.orchestrator.graph import NodeResult


class AggregatedResult(BaseModel):
    """The combined output of an aggregation strategy.

    `summary` is the prose the user sees. The remaining fields carry
    machine-readable structure that later strategies (Phases 3+) populate;
    `LLMSynthesisStrategy` leaves them empty.
    """

    summary: str
    facts: list[dict] = Field(default_factory=list)
    conflicts: list[dict] = Field(default_factory=list)
    # node_id -> list of fact keys it contributed
    node_attribution: dict[str, list[str]] = Field(default_factory=dict)


class AggregationStrategy(Protocol):
    name: str

    async def aggregate(
        self, question: str, results: list[NodeResult]
    ) -> AggregatedResult: ...


def describe_decision(decision: PolicyDecision) -> str:
    parts = [f"allowed={decision.allowed}"]
    if decision.reason:
        parts.append(f"reason: {decision.reason}")
    if decision.redactions:
        fields = ", ".join(f"{r.record}.{r.field}" for r in decision.redactions)
        parts.append(f"redacted: {fields}")
    if decision.obligations:
        parts.append("obligations: " + "; ".join(decision.obligations))
    return ", ".join(parts)


def format_results(results: list[Any]) -> str:
    """Render node results as the labelled sections fed to a synthesis LLM."""
    sections = []
    for result in results:
        call = result["call"]
        if result["error"] is not None:
            sections.append(f"## {call.node_id}\nNode unreachable: {result['error']}")
            continue
        response = result["response"]
        sections.append(
            f"## {call.node_id}\n"
            f"Query: {call.query}\n"
            f"Policy decision: {describe_decision(response.policy_decision)}\n"
            f"Answer: {response.answer or '(blocked by policy)'}"
        )
    return "\n\n".join(sections)
