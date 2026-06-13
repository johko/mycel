"""
JudgmentAggregationStrategy — proposition-wise majority rule.

From judgment aggregation theory: each node's facts are judgments on a set of
propositions (the aligned issues). The vote is scoped **per issue** — only the
nodes that actually opined on a proposition form its electorate, so a node
staying silent on a topic does not count against it.

Within an issue the nodes may report different values. The collective position
is the value held by a **strict majority** of that issue's electorate
(optionally confidence-weighted). If no value reaches a majority — e.g. three
nodes give three different figures — the issue is *contested* and surfaced as
such rather than resolved (the median strategy is the tool for picking a
central value; judgment's job is to report what the federation does and does
not collectively affirm).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mycel.llm import DEFAULT_MODEL
from mycel.orchestrator.strategies._align import Position, align_claims
from mycel.orchestrator.strategies.base import (
    AggregatedResult,
    format_results,
    synthesize_prose,
)

if TYPE_CHECKING:
    from mycel.orchestrator.graph import NodeResult

_SYSTEM_PROMPT = """\
You are the synthesizer of a federated multi-agent system using a judgment
aggregation rule. For each proposition, only the nodes that opined on it voted.
You are given the claims a majority of those voters affirmed (ACCEPTED), the
claims where the voters split with no majority value (CONTESTED), and the raw
node responses for reference.

Rules:
- Ground the answer in the ACCEPTED claims; state that each is the majority
  position of the nodes that addressed it, and note any dissenting value.
- Explicitly surface CONTESTED claims — report the competing values and that no
  majority emerged; do not pick one or hide the disagreement.
- Honor every attribution obligation and note where policies blocked data.
- Be concise and structured.\
"""


def _value_key(value) -> str:
    return str(value).strip().lower()


class JudgmentAggregationStrategy:
    name = "judgment"
    label = "Judgment Aggregation"
    description = "Proposition-wise majority vote across nodes; flags contested claims."

    def __init__(self, model: str = DEFAULT_MODEL, confidence_weighted: bool = True) -> None:
        self.model = model
        self.confidence_weighted = confidence_weighted

    def _weight(self, positions: list[Position]) -> float:
        return (
            sum(p.confidence for p in positions)
            if self.confidence_weighted
            else len(positions)
        )

    async def aggregate(
        self, question: str, results: list[NodeResult]
    ) -> AggregatedResult:
        issues = await align_claims(question, results, self.model)
        if not issues:
            # no structured facts to vote on — fall back to prose synthesis
            from mycel.orchestrator.strategies.llm_synthesis import LLMSynthesisStrategy

            return await LLMSynthesisStrategy(self.model).aggregate(question, results)

        accepted: list[dict] = []
        contested: list[dict] = []
        conflicts: list[dict] = []
        attribution: dict[str, list[str]] = {}

        for issue in issues:
            voters = list(issue.by_node().values())
            attribution[issue.label] = sorted(p.node_id for p in voters)
            positions = {p.node_id: p.value for p in voters}

            # group this issue's voters by the value they reported
            groups: dict[str, list[Position]] = {}
            for p in voters:
                groups.setdefault(_value_key(p.value), []).append(p)
            winner = max(groups.values(), key=self._weight)

            if self._weight(winner) > self._weight(voters) / 2:
                accepted.append(
                    {
                        "issue": issue.label,
                        "value": winner[0].value,
                        "supporters": sorted(p.node_id for p in winner),
                    }
                )
                if len(groups) > 1:  # majority value won, but someone dissented
                    conflicts.append(
                        {
                            "issue": issue.label,
                            "decided": winner[0].value,
                            "positions": positions,
                        }
                    )
            else:  # no value commands a majority of this issue's voters
                contested.append({"issue": issue.label, "positions": positions})
                conflicts.append(
                    {"issue": issue.label, "decided": None, "positions": positions}
                )

        context = self._context(accepted, contested, results)
        summary = await synthesize_prose(question, context, self.model, _SYSTEM_PROMPT)

        return AggregatedResult(
            summary=summary,
            facts=accepted,
            conflicts=conflicts,
            node_attribution=attribution,
        )

    @staticmethod
    def _context(
        accepted: list[dict], contested: list[dict], results: list
    ) -> str:
        parts = ["ACCEPTED (majority of the nodes that opined agree):"]
        parts += [
            f"- {a['issue']}: {a['value']!r} — backed by {', '.join(a['supporters'])}"
            for a in accepted
        ] or ["- (none)"]
        parts.append("\nCONTESTED (no majority value among the nodes that opined):")
        parts += [
            f"- {c['issue']}: "
            + ", ".join(f"{n}={v!r}" for n, v in c["positions"].items())
            for c in contested
        ] or ["- (none)"]
        parts.append("\nRaw node responses (for reference):\n" + format_results(results))
        return "\n".join(parts)
