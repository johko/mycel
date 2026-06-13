"""
JudgmentAggregationStrategy — proposition-wise majority rule.

From judgment aggregation theory: each node's facts are judgments on a set of
propositions (the aligned issues). A proposition is collectively accepted iff a
majority of participating nodes assert it — optionally weighted by the nodes'
confidence. Where the accepted propositions disagree on a value, that
disagreement is surfaced (a pragmatic stand-in for the discursive dilemma,
which we cannot detect in full without an explicit logical-constraint model).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mycel.llm import DEFAULT_MODEL
from mycel.orchestrator.strategies._align import align_claims, participants
from mycel.orchestrator.strategies.base import (
    AggregatedResult,
    format_results,
    synthesize_prose,
)

if TYPE_CHECKING:
    from mycel.orchestrator.graph import NodeResult

_SYSTEM_PROMPT = """\
You are the synthesizer of a federated multi-agent system using a judgment
aggregation rule. You are given the claims the federation collectively accepted
(by majority vote across nodes), any contested claims, the claims that failed to
reach a majority, and the raw node responses for reference.

Rules:
- Ground the answer in the ACCEPTED claims; mention that they are the
  federation's majority position.
- Explicitly surface CONTESTED claims (accepted but with disagreeing values) and
  claims that were REJECTED for lack of majority — do not hide the disagreement.
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

    async def aggregate(
        self, question: str, results: list[NodeResult]
    ) -> AggregatedResult:
        issues = await align_claims(question, results, self.model)
        if not issues:
            # no structured facts to vote on — fall back to prose synthesis
            from mycel.orchestrator.strategies.llm_synthesis import LLMSynthesisStrategy

            return await LLMSynthesisStrategy(self.model).aggregate(question, results)

        electorate = len(participants(issues))
        threshold = electorate / 2

        accepted: list[str] = []
        rejected: list[str] = []
        conflicts: list[dict] = []
        attribution: dict[str, list[str]] = {}

        for issue in issues:
            by_node = issue.by_node()
            support = (
                sum(p.confidence for p in by_node.values())
                if self.confidence_weighted
                else len(by_node)
            )
            if support > threshold:
                accepted.append(issue.label)
                attribution[issue.label] = sorted(by_node)
                values = {
                    _value_key(p.value) for p in by_node.values() if p.value is not None
                }
                if len(values) > 1:
                    conflicts.append(
                        {
                            "issue": issue.label,
                            "values": {p.node_id: p.value for p in by_node.values()},
                        }
                    )
            else:
                rejected.append(issue.label)

        context = self._context(accepted, rejected, conflicts, attribution, results)
        summary = await synthesize_prose(question, context, self.model, _SYSTEM_PROMPT)

        facts = [{"issue": label, "supporters": attribution[label]} for label in accepted]
        return AggregatedResult(
            summary=summary,
            facts=facts,
            conflicts=conflicts,
            node_attribution=attribution,
        )

    @staticmethod
    def _context(
        accepted: list[str],
        rejected: list[str],
        conflicts: list[dict],
        attribution: dict[str, list[str]],
        results: list,
    ) -> str:
        parts = ["ACCEPTED (majority of nodes assert):"]
        parts += (
            [f"- {label} — backed by {', '.join(attribution[label])}" for label in accepted]
            or ["- (none)"]
        )
        if conflicts:
            parts.append("\nCONTESTED (accepted but values disagree):")
            parts += [
                f"- {c['issue']}: "
                + ", ".join(f"{n}={v!r}" for n, v in c["values"].items())
                for c in conflicts
            ]
        parts.append("\nREJECTED (no majority):")
        parts += [f"- {label}" for label in rejected] or ["- (none)"]
        parts.append("\nRaw node responses (for reference):\n" + format_results(results))
        return "\n".join(parts)
