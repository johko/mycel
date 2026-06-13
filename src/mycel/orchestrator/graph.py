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

from mycel.orchestrator.planner import DEFAULT_MODEL, PlannedCall, make_plan
from mycel.orchestrator.registry import Registry
from mycel.orchestrator.strategies import AggregationStrategy, make_strategy
from mycel.schemas import InvokeResponse

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


def build_graph(
    registry: Registry,
    model: str = DEFAULT_MODEL,
    strategy: AggregationStrategy | None = None,
):
    strategy = strategy or make_strategy(model=model)

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
        writer({"type": "synthesizing", "strategy": strategy.name})
        aggregated = await strategy.aggregate(state["question"], state["results"])
        writer({"type": "final", "answer": aggregated.summary})
        return {"final_answer": aggregated.summary}

    graph = StateGraph(OrchestratorState)
    graph.add_node("plan", plan_node)
    graph.add_node("execute", execute_node)
    graph.add_node("synthesize", synthesize_node)
    graph.add_edge(START, "plan")
    graph.add_edge("plan", "execute")
    graph.add_edge("execute", "synthesize")
    graph.add_edge("synthesize", END)
    return graph.compile()
