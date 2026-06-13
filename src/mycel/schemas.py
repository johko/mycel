"""Shared schemas for nodes and orchestrator."""

from typing import Any

from pydantic import BaseModel, Field


class PolicyViolation(BaseModel):
    """A sensitive value from a touched record that appeared in the answer."""

    record: str
    field: str


class PolicyDecision(BaseModel):
    allowed: bool
    redactions: list[PolicyViolation] = Field(default_factory=list)
    violations: list[PolicyViolation] = Field(default_factory=list)
    obligations: list[str] = Field(default_factory=list)
    reason: str | None = None


class Fact(BaseModel):
    """A single machine-readable claim extracted from a node's safe answer."""

    claim: str
    value: Any | None = None
    unit: str | None = None
    confidence: float = 1.0
    source_record: str | None = None


class StructuredAnswer(BaseModel):
    """Machine-readable view of a node's answer, for programmatic aggregation.

    `summary` is the policy-filtered prose; `facts` are extracted from that
    same safe text (never from raw records), so they carry no value the
    policy layer would have blocked. `caveats` record policy-imposed limits.
    """

    facts: list[Fact] = Field(default_factory=list)
    summary: str
    caveats: list[str] = Field(default_factory=list)


class InvokeRequest(BaseModel):
    query: str
    context: dict | None = None


class InvokeResponse(BaseModel):
    node_id: str
    answer: str
    structured_answer: StructuredAnswer | None = None
    policy_decision: PolicyDecision
