"""
MCP client — the Diplomat agent as an MCP *client*.

The agent connects out to a remote MCP server (the company's data connector),
discovers whatever tools that server exposes, and dispatches the model's tool
calls to it over the Model Context Protocol (streamable-HTTP transport). The
container ships no data of its own: what the agent can see is exactly what the
remote server chooses to expose. Data sovereignty starts at this boundary
(ingress) and is backed up by the egress policy layer.
"""

import asyncio
import json
from contextlib import asynccontextmanager

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from mycel.node.config import McpClientConfig

# Reserved tool a connector may implement to feed the OPA egress layer a
# canonical {id: record} view (see mycel.demo.connector.policy). It is hidden
# from the agent's tool list and called only by the node after the agent loop.
POLICY_VIEW_TOOL = "policy_view"


def _to_openai_tool(tool) -> dict:
    """Translate an MCP Tool into the OpenAI chat-completion tool schema."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.inputSchema or {"type": "object", "properties": {}},
        },
    }


def _partition_tools(tools) -> tuple[list[dict], bool]:
    """Split discovered tools into agent-facing schemas and the reserved one.

    `policy_view` is excluded from the agent's schemas (so the model never sees
    it) but its presence is reported so the node can call it for the OPA layer.
    """
    has_policy_view = any(t.name == POLICY_VIEW_TOOL for t in tools)
    schemas = [_to_openai_tool(t) for t in tools if t.name != POLICY_VIEW_TOOL]
    return schemas, has_policy_view


def _reduce_result(result) -> object:
    """Reduce a CallToolResult to a JSON-serializable value.

    Prefer structured content when present (FastMCP wraps a non-dict return
    under a `result` key — unwrap it). Otherwise parse the text content blocks:
    a tool that returns a list arrives as one block per element, so parse each
    block on its own and return a single value or a list accordingly.
    """
    sc = result.structuredContent
    if isinstance(sc, dict) and list(sc.keys()) == ["result"]:
        return sc["result"]
    if sc is not None:
        return sc

    parsed: list[object] = []
    for block in result.content or []:
        text = getattr(block, "text", None)
        if text is None:
            continue
        try:
            parsed.append(json.loads(text))
        except (json.JSONDecodeError, ValueError):
            parsed.append(text)
    if not parsed:
        return ""
    return parsed[0] if len(parsed) == 1 else parsed


class RemoteToolset:
    """The discovered tools of a remote MCP server, plus a call dispatcher.

    `schemas` are the agent-facing tools, ready to hand to
    `chat_completion(tools=...)` — the reserved `policy_view` tool is excluded
    so the model never sees it. `call` is serialized by a lock because a single
    MCP session is shared across all concurrent /invoke requests in this process.
    """

    def __init__(
        self, session: ClientSession, schemas: list[dict], *, has_policy_view: bool = False
    ):
        self._session = session
        self._lock = asyncio.Lock()
        self.schemas = schemas
        self.has_policy_view = has_policy_view

    @property
    def tool_names(self) -> list[str]:
        return [s["function"]["name"] for s in self.schemas]

    async def call(self, name: str, args: dict) -> object:
        async with self._lock:
            result = await self._session.call_tool(name, args)
        return _reduce_result(result)

    async def policy_view(self, observations: list[dict]) -> dict:
        """Canonical {id: record} view for OPA, or {} if unsupported/failed."""
        if not self.has_policy_view:
            return {}
        try:
            result = await self.call(POLICY_VIEW_TOOL, {"observations": observations})
        except Exception:
            return {}
        return result if isinstance(result, dict) else {}


@asynccontextmanager
async def connect_toolset(mcp_cfg: McpClientConfig, *, attempts: int = 3):
    """Open a session to the remote MCP server and discover its tools.

    Stays open for the caller's lifetime (managed by the app lifespan).
    Connection/discovery is retried with backoff — like `chat_with_retry` —
    so a connector that is slow to come up does not kill the node.
    """
    last_error: Exception | None = None
    yielded = False
    for attempt in range(attempts):
        try:
            async with streamablehttp_client(
                mcp_cfg.url, headers=mcp_cfg.headers or None
            ) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    listed = await session.list_tools()
                    # Reserve policy_view: keep it callable but hide it from the agent.
                    schemas, has_policy_view = _partition_tools(listed.tools)
                    if not schemas:
                        raise RuntimeError(
                            f"MCP server at {mcp_cfg.url} exposed no tools"
                        )
                    yielded = True
                    yield RemoteToolset(
                        session, schemas, has_policy_view=has_policy_view
                    )
                    return
        except Exception as exc:
            if yielded:
                raise  # error came from the caller's body, not from setup
            last_error = exc
            await asyncio.sleep(1 + attempt)
    raise RuntimeError(
        f"could not connect to MCP server at {mcp_cfg.url}: {last_error}"
    ) from last_error
