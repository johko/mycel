"""
Diplomat Agent — LLM tool-calling loop, driven by a remote MCP server.

The agent is an MCP *client*: it reasons over whatever tools the configured
MCP server (`RemoteToolset`) exposes, discovered at runtime. Inference runs on
Hugging Face Inference Providers (OpenAI-style chat completions).

Returns the answer text plus an observation log — every tool call and its
result — so the egress policy layer can judge the outgoing answer against the
data it was derived from. This module knows nothing about OPA.
"""

import json

from mycel.llm import chat_with_retry, get_client, parse_tool_arguments
from mycel.node.config import NodeConfig
from mycel.node.mcp_client import RemoteToolset
from mycel.schemas import Fact, StructuredAnswer

_MAX_TURNS = 10


def observed_record_ids(observations: list[dict]) -> list[str]:
    """Source identifiers the agent fetched, for fact attribution.

    Generic over tools: any string `id`/`record_id` argument passed to a
    successful tool call. Empty for connectors that don't address data by ID.
    """
    ids: list[str] = []
    for obs in observations:
        args = obs.get("arguments") or {}
        for key in ("id", "record_id"):
            val = args.get(key)
            if isinstance(val, str) and val not in ids:
                ids.append(val)
    return ids


async def run_agent(query: str, config: NodeConfig, toolset: RemoteToolset) -> dict:
    client = get_client(config.backend)
    messages: list[dict] = [
        {"role": "system", "content": config.system_prompt},
        {"role": "user", "content": query},
    ]
    observations: list[dict] = []

    for _ in range(_MAX_TURNS):
        response = await chat_with_retry(
            client,
            messages=messages,
            model=config.model,
            tools=toolset.schemas,
            max_tokens=1024,
        )
        msg = response.choices[0].message

        if not msg.tool_calls:
            return {"answer": msg.content or "", "observations": observations}

        messages.append(
            {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                            if isinstance(tc.function.arguments, str)
                            else json.dumps(tc.function.arguments),
                        },
                    }
                    for tc in msg.tool_calls
                ],
            }
        )
        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = parse_tool_arguments(tc.function.arguments)
            except json.JSONDecodeError as exc:
                # malformed arguments go back to the model instead of crashing
                result: object = {"error": f"invalid tool arguments: {exc}"}
            else:
                try:
                    result = await toolset.call(name, args)
                except Exception as exc:
                    # a failed tool call goes back to the model, not the policy log
                    result = {"error": f"tool call failed: {exc}"}
                else:
                    observations.append(
                        {"tool": name, "arguments": args, "result": result}
                    )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": name,
                    "content": json.dumps(result),
                }
            )

    return {"answer": "", "observations": observations}


_EXTRACT_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_facts",
        "description": "Submit the structured facts stated in the answer.",
        "parameters": {
            "type": "object",
            "properties": {
                "facts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "claim": {
                                "type": "string",
                                "description": "The factual statement in natural language.",
                            },
                            "value": {
                                "type": ["string", "number", "boolean", "null"],
                                "description": "The scalar the claim asserts, if any.",
                            },
                            "unit": {
                                "type": "string",
                                "description": "Unit of the value, e.g. 'kWh', '%'.",
                            },
                            "confidence": {
                                "type": "number",
                                "description": "0.0–1.0; lower if the answer hedges or approximates.",
                            },
                            "source_record": {
                                "type": "string",
                                "description": "Record ID the claim came from, chosen from the provided list.",
                            },
                        },
                        "required": ["claim"],
                    },
                }
            },
            "required": ["facts"],
        },
    },
}

_EXTRACT_SYSTEM_PROMPT = """\
You convert a department node's already-published answer into structured facts.
The answer text has ALREADY passed the node's egress policy — extract only what
is stated in it, and never add data that is not present in the answer.

For each distinct factual claim, emit one fact with: the claim in natural
language; the scalar value it asserts if any; the unit of that value if any; a
confidence in 0.0–1.0 (lower when the answer hedges or approximates); and the
source record ID if it can be identified from the provided list.

If the answer is empty or only states that information was blocked, return no
facts. Respond with a submit_facts tool call and nothing else.\
"""

_EXTRACT_ATTEMPTS = 2


async def extract_facts(
    answer: str, record_ids: list[str], config: NodeConfig
) -> list[Fact]:
    """Extract structured facts from the policy-filtered answer text.

    Operates on the safe answer only, so no value the policy layer blocked can
    re-enter through a fact. Returns [] if the answer is empty or extraction
    fails — the caller degrades to prose-only.
    """
    if not answer.strip():
        return []

    client = get_client(config.backend)
    messages = [
        {"role": "system", "content": _EXTRACT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Available record IDs: {record_ids}\n\nAnswer:\n{answer}",
        },
    ]
    for _ in range(_EXTRACT_ATTEMPTS):
        response = await chat_with_retry(
            client,
            messages=messages,
            model=config.model,
            tools=[_EXTRACT_TOOL],
            tool_choice={"type": "function", "function": {"name": "submit_facts"}},
            max_tokens=1024,
        )
        msg = response.choices[0].message
        if not msg.tool_calls:
            continue
        try:
            args = parse_tool_arguments(msg.tool_calls[0].function.arguments)
            return [Fact(**f) for f in args.get("facts", [])]
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
    return []


async def build_structured_answer(
    answer: str, record_ids: list[str], caveats: list[str], config: NodeConfig
) -> StructuredAnswer | None:
    """Wrap the safe answer as a StructuredAnswer; None on extraction failure."""
    try:
        facts = await extract_facts(answer, record_ids, config)
    except Exception:
        return None
    return StructuredAnswer(facts=facts, summary=answer, caveats=caveats)
