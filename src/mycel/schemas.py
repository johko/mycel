"""Shared schemas for nodes and orchestrator."""

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


class InvokeRequest(BaseModel):
    query: str
    context: dict | None = None


class InvokeResponse(BaseModel):
    node_id: str
    answer: str
    policy_decision: PolicyDecision
