"""
Diplomat Agent — LLM tool-calling loop, generic over a department DataStore.

Inference runs on Hugging Face Inference Providers (OpenAI-style chat
completions). Returns the answer text plus every record the agent touched,
so the policy layer can judge the outgoing answer against the sensitive
data it was derived from. This module knows nothing about OPA.
"""

import json

from mycel.llm import chat_with_retry, get_client, parse_tool_arguments
from mycel.node.config import NodeConfig
from mycel.node.datastore import DataStore

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_records",
            "description": "List all available record IDs with a short label.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_record",
            "description": "Fetch the full contents of a record by ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Record identifier"}
                },
                "required": ["id"],
            },
        },
    },
]

_MAX_TURNS = 10


def _dispatch_tool(
    name: str, args: dict, store: DataStore, touched: dict[str, dict]
) -> object:
    if name == "list_records":
        return store.list_records()
    if name == "get_record":
        record_id = args.get("id")
        if not record_id:
            return {"error": "missing required argument 'id'"}
        record = store.get_record(record_id)
        if "error" not in record:
            touched[record_id] = record
        return record
    return {"error": f"unknown tool {name!r}"}


async def run_agent(query: str, config: NodeConfig, store: DataStore) -> dict:
    client = get_client()
    messages: list[dict] = [
        {"role": "system", "content": config.system_prompt},
        {"role": "user", "content": query},
    ]
    touched_records: dict[str, dict] = {}

    for _ in range(_MAX_TURNS):
        response = await chat_with_retry(
            client,
            messages=messages,
            model=config.model,
            tools=_TOOLS,
            max_tokens=1024,
        )
        msg = response.choices[0].message

        if not msg.tool_calls:
            return {"answer": msg.content or "", "records": touched_records}

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
            try:
                args = parse_tool_arguments(tc.function.arguments)
            except json.JSONDecodeError as exc:
                # malformed arguments go back to the model instead of crashing
                result: object = {"error": f"invalid tool arguments: {exc}"}
            else:
                result = _dispatch_tool(tc.function.name, args, store, touched_records)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tc.function.name,
                    "content": json.dumps(result),
                }
            )

    return {"answer": "", "records": touched_records}
