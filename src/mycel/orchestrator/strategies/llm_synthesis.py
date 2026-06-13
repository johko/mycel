"""
LLM synthesis strategy.

The original (and default) aggregation behaviour: hand every node's
policy-filtered answer to a synthesizer LLM and let it write one prose
answer, honoring obligations and surfacing what policies blocked. The
structured fields of `AggregatedResult` are left empty — this strategy
operates purely on text.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mycel.llm import DEFAULT_MODEL, chat_with_retry, get_client
from mycel.orchestrator.strategies.base import AggregatedResult, format_results

if TYPE_CHECKING:
    from mycel.orchestrator.graph import NodeResult

_SYSTEM_PROMPT = """\
You are the synthesizer of a federated multi-agent system. You receive
policy-filtered responses from autonomous department nodes and combine
them into one answer to the user's question.

Rules:
- Use only what the nodes returned; do not invent data.
- Honor every attribution obligation: cite the listed sources.
- Where a node blocked or redacted information, say so explicitly —
  the policy enforcement is a feature, not a failure to hide.
- Be concise and structured.\
"""


class LLMSynthesisStrategy:
    name = "llm"

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self.model = model

    async def aggregate(
        self, question: str, results: list[NodeResult]
    ) -> AggregatedResult:
        client = get_client()
        prompt = (
            f"Question: {question}\n\n"
            f"Node responses:\n\n{format_results(results)}"
        )
        response = await chat_with_retry(
            client,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            model=self.model,
            max_tokens=2048,
        )
        answer = response.choices[0].message.content or ""
        return AggregatedResult(summary=answer)
