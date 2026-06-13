"""
Orchestrator graph: plan -> execute -> synthesize.

The planner LLM decides which Diplomat nodes to consult, the executor
calls them over HTTP, and the synthesizer LLM combines the
policy-filtered responses — honoring obligations and surfacing what
the policies blocked.
"""

import asyncio
import os
from typing import TypedDict

import httpx
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from mycel.llm import chat_with_retry, get_client
from mycel.orchestrator.planner import DEFAULT_MODEL, PlannedCall, make_plan
from mycel.orchestrator.registry import Registry
from mycel.schemas import InvokeResponse, PolicyDecision

NODE_TIMEOUT = float(os.environ.get("NODE_TIMEOUT", "120"))


class NodeResult(TypedDict):
    call: PlannedCall
    response: InvokeResponse | None
    error: str | None


class OrchestratorState(TypedDict, total=False):
    question: str
    plan: list[PlannedCall]
    results: list[NodeResult]
    final_answer: str


_SYNTH_SYSTEM_PROMPT = """\
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


_NODE_ATTEMPTS = 3


async def _invoke_node(
    client: httpx.AsyncClient, endpoint: str, call: PlannedCall
) -> NodeResult:
    # node agents depend on remote inference; retry transient failures
    error = "unknown error"
    for _ in range(_NODE_ATTEMPTS):
        try:
            resp = await client.post(f"{endpoint}/invoke", json={"query": call.query})
            resp.raise_for_status()
            return {"call": call, "response": InvokeResponse(**resp.json()), "error": None}
        except httpx.HTTPStatusError as exc:
            error = f"{exc} — {exc.response.text[:300]}"
        except Exception as exc:
            error = str(exc)
    return {"call": call, "response": None, "error": error}


def _result_event(result: NodeResult) -> dict:
    """Serializable per-node event for live UIs (custom stream channel)."""
    response = result["response"]
    return {
        "type": "node_result",
        "node_id": result["call"].node_id,
        "query": result["call"].query,
        "error": result["error"],
        "answer": response.answer if response else None,
        "decision": response.policy_decision.model_dump() if response else None,
    }


def _describe_decision(decision: PolicyDecision) -> str:
    parts = [f"allowed={decision.allowed}"]
    if decision.reason:
        parts.append(f"reason: {decision.reason}")
    if decision.redactions:
        fields = ", ".join(f"{r.record}.{r.field}" for r in decision.redactions)
        parts.append(f"redacted: {fields}")
    if decision.obligations:
        parts.append("obligations: " + "; ".join(decision.obligations))
    return ", ".join(parts)


def _format_results(results: list[NodeResult]) -> str:
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
            f"Policy decision: {_describe_decision(response.policy_decision)}\n"
            f"Answer: {response.answer or '(blocked by policy)'}"
        )
    return "\n\n".join(sections)


def build_graph(registry: Registry, model: str = DEFAULT_MODEL):
    async def plan_node(state: OrchestratorState) -> OrchestratorState:
        plan = await make_plan(state["question"], registry, model)
        writer = get_stream_writer()
        writer({"type": "plan", "calls": [c.model_dump() for c in plan]})
        return {"plan": plan}

    async def execute_node(state: OrchestratorState) -> OrchestratorState:
        writer = get_stream_writer()
        for call in state["plan"]:
            writer({"type": "node_start", "node_id": call.node_id, "query": call.query})

        async def invoke_and_emit(call: PlannedCall) -> NodeResult:
            entry = registry.get(call.node_id)
            async with httpx.AsyncClient(timeout=NODE_TIMEOUT) as client:
                result = await _invoke_node(client, entry.endpoint, call)
            writer(_result_event(result))
            return result

        results = await asyncio.gather(*[invoke_and_emit(call) for call in state["plan"]])
        return {"results": list(results)}

    async def synthesize_node(state: OrchestratorState) -> OrchestratorState:
        writer = get_stream_writer()
        writer({"type": "synthesizing"})
        client = get_client()
        prompt = (
            f"Question: {state['question']}\n\n"
            f"Node responses:\n\n{_format_results(state['results'])}"
        )
        response = await chat_with_retry(
            client,
            messages=[
                {"role": "system", "content": _SYNTH_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            model=model,
            max_tokens=2048,
        )
        answer = response.choices[0].message.content or ""
        writer({"type": "final", "answer": answer})
        return {"final_answer": answer}

    graph = StateGraph(OrchestratorState)
    graph.add_node("plan", plan_node)
    graph.add_node("execute", execute_node)
    graph.add_node("synthesize", synthesize_node)
    graph.add_edge(START, "plan")
    graph.add_edge("plan", "execute")
    graph.add_edge("execute", "synthesize")
    graph.add_edge("synthesize", END)
    return graph.compile()
