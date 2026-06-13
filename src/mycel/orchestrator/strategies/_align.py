"""
Claim alignment — shared preprocessing for the COMSOC strategies.

Groups facts from different nodes that address the same underlying
proposition into *issues*, producing the node × issue matrix that
`JudgmentAggregationStrategy` and `MajorityJudgmentStrategy` both vote over.
An LLM clusters the pooled facts; normalized-string grouping is the fallback
when inference is unavailable or returns nothing usable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from mycel.llm import chat_with_retry, get_client, parse_tool_arguments

if TYPE_CHECKING:
    from mycel.orchestrator.graph import NodeResult


class Position(BaseModel):
    """One node's stance on an issue (derived from a single Fact)."""

    node_id: str
    claim: str
    value: Any | None = None
    unit: str | None = None
    confidence: float = 1.0


class Issue(BaseModel):
    """A proposition several nodes may opine on, with their positions."""

    label: str
    positions: list[Position] = Field(default_factory=list)

    def by_node(self) -> dict[str, Position]:
        """One position per node — the highest-confidence fact if a node
        contributed several to this issue."""
        best: dict[str, Position] = {}
        for p in self.positions:
            cur = best.get(p.node_id)
            if cur is None or p.confidence > cur.confidence:
                best[p.node_id] = p
        return best


def participants(issues: list[Issue]) -> set[str]:
    """Nodes that contributed at least one fact — the electorate."""
    return {p.node_id for issue in issues for p in issue.positions}


_ALIGN_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_alignment",
        "description": "Group the provided facts into issues (shared propositions).",
        "parameters": {
            "type": "object",
            "properties": {
                "issues": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {
                                "type": "string",
                                "description": "Canonical one-line proposition the grouped facts address.",
                            },
                            "fact_indices": {
                                "type": "array",
                                "items": {"type": "integer"},
                                "description": "Indices of facts (from the numbered list) addressing this issue.",
                            },
                        },
                        "required": ["label", "fact_indices"],
                    },
                }
            },
            "required": ["issues"],
        },
    },
}

_ALIGN_SYSTEM_PROMPT = """\
You align facts reported by different department nodes of a federated system.
Group facts that address the SAME underlying proposition into one issue, even
when worded differently; give each issue a short canonical label. Facts about
different propositions go in different issues. Every fact index must appear in
exactly one issue. Respond with a submit_alignment tool call and nothing else.\
"""

_ALIGN_ATTEMPTS = 2


def _collect_positions(results: list) -> list[Position]:
    positions: list[Position] = []
    for result in results:
        response = result["response"]
        if response is None or response.structured_answer is None:
            continue
        for fact in response.structured_answer.facts:
            positions.append(
                Position(
                    node_id=response.node_id,
                    claim=fact.claim,
                    value=fact.value,
                    unit=fact.unit,
                    confidence=fact.confidence,
                )
            )
    return positions


def _build_issues(raw_issues: list, positions: list[Position]) -> list[Issue]:
    issues: list[Issue] = []
    assigned: set[int] = set()
    for item in raw_issues:
        label = item.get("label")
        members = []
        for i in item.get("fact_indices") or []:
            if isinstance(i, int) and 0 <= i < len(positions) and i not in assigned:
                members.append(positions[i])
                assigned.add(i)
        if label and members:
            issues.append(Issue(label=label, positions=members))
    # any fact the model failed to place becomes its own single-voter issue,
    # so nothing is silently dropped from the aggregation
    for i, position in enumerate(positions):
        if i not in assigned:
            issues.append(Issue(label=position.claim, positions=[position]))
    return issues


def _align_by_string(positions: list[Position]) -> list[Issue]:
    groups: dict[str, Issue] = {}
    for position in positions:
        key = " ".join(position.claim.lower().split())
        issue = groups.get(key)
        if issue is None:
            issue = Issue(label=position.claim, positions=[])
            groups[key] = issue
        issue.positions.append(position)
    return list(groups.values())


async def _align_llm(
    question: str, positions: list[Position], model: str
) -> list[Issue]:
    client = get_client()
    listing = "\n".join(
        f"[{i}] node={p.node_id} claim={p.claim!r} value={p.value!r} unit={p.unit!r}"
        for i, p in enumerate(positions)
    )
    messages = [
        {"role": "system", "content": _ALIGN_SYSTEM_PROMPT},
        {"role": "user", "content": f"Question: {question}\n\nFacts:\n{listing}"},
    ]
    for _ in range(_ALIGN_ATTEMPTS):
        response = await chat_with_retry(
            client,
            messages=messages,
            model=model,
            tools=[_ALIGN_TOOL],
            tool_choice={"type": "function", "function": {"name": "submit_alignment"}},
            max_tokens=1024,
        )
        msg = response.choices[0].message
        if not msg.tool_calls:
            continue
        args = parse_tool_arguments(msg.tool_calls[0].function.arguments)
        issues = _build_issues(args.get("issues", []), positions)
        if issues:
            return issues
    raise ValueError("alignment produced no issues")


async def align_claims(
    question: str, results: list, model: str
) -> list[Issue]:
    """Cluster every node's facts into issues. Empty list if no node returned
    structured facts."""
    positions = _collect_positions(results)
    if not positions:
        return []
    try:
        return await _align_llm(question, positions, model)
    except Exception:
        return _align_by_string(positions)
