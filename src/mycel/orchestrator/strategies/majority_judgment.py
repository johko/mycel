"""
MajorityJudgmentStrategy — the median-grade rule.

Balinski & Laraki's Majority Judgment, adapted to numeric facts: for each
aligned issue the collective grade is the median of the nodes' confidences and
the collective value is the confidence-weighted median of their reported
values. The median is strategyproof and robust to a single overconfident or
outlier node, unlike picking the highest-confidence answer. The min–max spread
across nodes is surfaced as an explicit disagreement signal.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mycel.llm import DEFAULT_MODEL
from mycel.orchestrator.strategies._align import align_claims
from mycel.orchestrator.strategies.base import (
    AggregatedResult,
    format_results,
    synthesize_prose,
)

if TYPE_CHECKING:
    from mycel.orchestrator.graph import NodeResult

_SYSTEM_PROMPT = """\
You are the synthesizer of a federated multi-agent system using a median rule
(Majority Judgment). For each issue you are given the collective value (the
confidence-weighted median across nodes), the collective grade (median
confidence), and the min–max spread of the nodes' reported values.

Rules:
- Report the collective (median) value for each issue, not any single node's.
- Where the spread is wide, state the disagreement explicitly.
- Honor every attribution obligation and note where policies blocked data.
- Be concise and structured.\
"""


def _coerce_number(value) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _lower_median(xs: list[float]) -> float | None:
    """Lower median — the Majority Judgment majority-grade convention for ties."""
    s = sorted(xs)
    if not s:
        return None
    return s[(len(s) - 1) // 2]


def _weighted_median(pairs: list[tuple[float, float]]) -> float | None:
    """Confidence-weighted median of (value, weight) pairs (lower median on ties)."""
    items = sorted(pairs, key=lambda x: x[0])
    if not items:
        return None
    total = sum(w for _, w in items)
    if total <= 0:
        return _lower_median([v for v, _ in items])
    cumulative = 0.0
    for value, weight in items:
        cumulative += weight
        if cumulative * 2 >= total:
            return value
    return items[-1][0]


class MajorityJudgmentStrategy:
    name = "median"
    label = "Majority Judgment (median)"
    description = "Confidence-weighted median value per claim; robust to outliers."

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self.model = model

    async def aggregate(
        self, question: str, results: list[NodeResult]
    ) -> AggregatedResult:
        issues = await align_claims(question, results, self.model)
        if not issues:
            from mycel.orchestrator.strategies.llm_synthesis import LLMSynthesisStrategy

            return await LLMSynthesisStrategy(self.model).aggregate(question, results)

        facts: list[dict] = []
        attribution: dict[str, list[str]] = {}

        for issue in issues:
            by_node = issue.by_node()
            grade = _lower_median([p.confidence for p in by_node.values()])
            numeric = [
                (n, p.confidence)
                for p in by_node.values()
                if (n := _coerce_number(p.value)) is not None
            ]
            value = _weighted_median(numeric) if numeric else None
            spread = (
                [min(n for n, _ in numeric), max(n for n, _ in numeric)]
                if numeric
                else None
            )
            attribution[issue.label] = sorted(by_node)
            facts.append(
                {
                    "issue": issue.label,
                    "value": value,
                    "grade": grade,
                    "spread": spread,
                    "voters": sorted(by_node),
                }
            )

        context = self._context(facts) + "\n\nRaw node responses (for reference):\n" + format_results(results)
        summary = await synthesize_prose(question, context, self.model, _SYSTEM_PROMPT)

        return AggregatedResult(
            summary=summary, facts=facts, node_attribution=attribution
        )

    @staticmethod
    def _context(facts: list[dict]) -> str:
        lines = ["COLLECTIVE VALUES (confidence-weighted median per issue):"]
        for f in facts:
            spread = (
                f", spread {f['spread'][0]}–{f['spread'][1]}" if f["spread"] else ""
            )
            value = f["value"] if f["value"] is not None else "(no numeric value)"
            lines.append(
                f"- {f['issue']}: value={value}, grade={f['grade']}{spread} "
                f"(voters: {', '.join(f['voters'])})"
            )
        return "\n".join(lines)
