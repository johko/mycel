"""
Planner LLM.

Given the question and the registry's capability overview, emits a
structured call plan (which Diplomat nodes to ask, with what query, in
what order) via a forced tool call on Hugging Face Inference Providers.
"""

import json
import os

from pydantic import BaseModel

from mycel.llm import DEFAULT_MODEL as _SHARED_DEFAULT
from mycel.llm import chat_with_retry, get_client, parse_tool_arguments
from mycel.orchestrator.registry import Registry

DEFAULT_MODEL = os.environ.get("PLANNER_MODEL", _SHARED_DEFAULT)


class PlannedCall(BaseModel):
    node_id: str
    query: str
    rationale: str | None = None


_PLAN_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_plan",
        "description": "Submit the plan of Diplomat node calls needed to answer the question.",
        "parameters": {
            "type": "object",
            "properties": {
                "calls": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "node_id": {
                                "type": "string",
                                "description": "ID of the node to call, exactly as listed in the registry.",
                            },
                            "query": {
                                "type": "string",
                                "description": "The question to send to that node, phrased to respect its policy constraints.",
                            },
                            "rationale": {
                                "type": "string",
                                "description": "Why this call is needed.",
                            },
                        },
                        "required": ["node_id", "query"],
                    },
                }
            },
            "required": ["calls"],
        },
    },
}

_SYSTEM_PROMPT = """\
You are the planner of a federated multi-agent system. Autonomous Diplomat
nodes hold department data behind egress policies; you can only reach them
through queries, and each node decides what leaves its environment.

Available nodes:
{registry}

Plan the node calls needed to answer the user's question. Prefer a minimal
plan, with one exception: when several departments may hold the same or
corroborating data for a factual or quantitative claim, query EACH of them
with the same question. Their answers are cross-checked and aggregated
downstream, so overlapping coverage on a shared fact is valuable, not
wasteful — e.g. a campus-wide figure that more than one department measures
or estimates should be asked of every such department.
Forward the user's actual information need verbatim where possible — do
NOT pre-sanitize, soften, or rephrase a query to fit a node's policies.
Policy decisions belong to the nodes, not to you: never refuse, never
answer the question yourself, and never skip or water down a call because
you expect a node's policy to block it — send the real question and let
the node's policy engine decide what leaves its environment. Order calls so later queries can be answered
independently — nodes do not see each other's responses. You must always
respond with a submit_plan tool call and nothing else.\
"""


_MAX_ATTEMPTS = 3


async def make_plan(
    question: str, registry: Registry, model: str = DEFAULT_MODEL
) -> list[PlannedCall]:
    # Forced tool_choice is occasionally ignored depending on which provider
    # the HF router picks, so retry on a malformed plan.
    client = get_client()
    messages = [
        {
            "role": "system",
            "content": _SYSTEM_PROMPT.format(registry=registry.describe()),
        },
        {"role": "user", "content": question},
    ]
    last_error: ValueError | None = None
    for _ in range(_MAX_ATTEMPTS):
        response = await chat_with_retry(
            client,
            messages=messages,
            model=model,
            max_tokens=2048,
            tools=[_PLAN_TOOL],
            tool_choice={"type": "function", "function": {"name": "submit_plan"}},
        )
        try:
            return parse_plan(response, registry)
        except ValueError as exc:
            last_error = exc
    raise last_error


def parse_plan(response, registry: Registry) -> list[PlannedCall]:
    """Extract the plan from the submit_plan tool call, dropping unknown nodes."""
    msg = response.choices[0].message
    if msg.tool_calls:
        args = parse_tool_arguments(msg.tool_calls[0].function.arguments)
    else:
        # fallback: some provider/model combos answer in text with the JSON inline
        args = _extract_plan_from_text(msg.content or "")
        if args is None:
            raise ValueError("planner did not return a submit_plan tool call")
    calls = [PlannedCall(**call) for call in args.get("calls", [])]
    return [call for call in calls if registry.get(call.node_id) is not None]


def _extract_plan_from_text(text: str) -> dict | None:
    """Find the first JSON object containing a "calls" list anywhere in the text."""
    decoder = json.JSONDecoder()
    for start, char in enumerate(text):
        if char != "{":
            continue
        try:
            candidate, _ = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict) and isinstance(candidate.get("calls"), list):
            return candidate
    return None
