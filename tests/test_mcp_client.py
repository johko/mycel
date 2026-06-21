"""Translation between MCP types and the agent's tool-calling contract."""

from types import SimpleNamespace

from mcp.types import CallToolResult, TextContent

from mycel.node.mcp_client import (
    POLICY_VIEW_TOOL,
    RemoteToolset,
    _partition_tools,
    _reduce_result,
    _to_openai_tool,
)


def test_to_openai_tool_translates_schema():
    tool = SimpleNamespace(
        name="get_record",
        description="Fetch a record by ID.",
        inputSchema={
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
    )
    schema = _to_openai_tool(tool)
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "get_record"
    assert schema["function"]["description"] == "Fetch a record by ID."
    assert schema["function"]["parameters"]["required"] == ["id"]


def test_to_openai_tool_defaults_missing_fields():
    tool = SimpleNamespace(name="ping", description=None, inputSchema=None)
    schema = _to_openai_tool(tool)
    assert schema["function"]["description"] == ""
    assert schema["function"]["parameters"] == {"type": "object", "properties": {}}


def test_reduce_result_decodes_json_text():
    result = CallToolResult(
        content=[TextContent(type="text", text='{"value": 42, "unit": "kWh"}')]
    )
    assert _reduce_result(result) == {"value": 42, "unit": "kWh"}


def test_reduce_result_keeps_plain_text():
    result = CallToolResult(content=[TextContent(type="text", text="hello world")])
    assert _reduce_result(result) == "hello world"


def test_reduce_result_parses_multiple_blocks_as_list():
    # a tool returning a list arrives as one content block per element
    result = CallToolResult(
        content=[
            TextContent(type="text", text='{"id": "R1"}'),
            TextContent(type="text", text='{"id": "R2"}'),
        ]
    )
    assert _reduce_result(result) == [{"id": "R1"}, {"id": "R2"}]


def test_reduce_result_unwraps_structured_result_envelope():
    # FastMCP wraps a non-dict return (e.g. a list) under a "result" key
    result = CallToolResult(
        content=[TextContent(type="text", text="ignored")],
        structuredContent={"result": [{"id": "R1"}, {"id": "R2"}]},
    )
    assert _reduce_result(result) == [{"id": "R1"}, {"id": "R2"}]


def test_reduce_result_uses_structured_content():
    result = CallToolResult(content=[], structuredContent={"value": 7})
    assert _reduce_result(result) == {"value": 7}


def _tool(name):
    return SimpleNamespace(name=name, description="", inputSchema=None)


def test_partition_hides_policy_view_from_agent_schemas():
    schemas, has_policy_view = _partition_tools(
        [_tool("get_record"), _tool(POLICY_VIEW_TOOL), _tool("search")]
    )
    assert has_policy_view is True
    names = [s["function"]["name"] for s in schemas]
    assert names == ["get_record", "search"]
    assert POLICY_VIEW_TOOL not in names


def test_partition_without_policy_view():
    schemas, has_policy_view = _partition_tools([_tool("get_record")])
    assert has_policy_view is False
    assert len(schemas) == 1


class _FakeSession:
    def __init__(self, structured):
        self._structured = structured
        self.calls = []

    async def call_tool(self, name, args):
        self.calls.append((name, args))
        return CallToolResult(content=[], structuredContent=self._structured)


async def test_policy_view_returns_empty_when_unsupported():
    toolset = RemoteToolset(_FakeSession(None), schemas=[], has_policy_view=False)
    assert await toolset.policy_view([{"tool": "get_record"}]) == {}


async def test_policy_view_calls_reserved_tool_when_supported():
    session = _FakeSession({"R1": {"value": 42}})
    toolset = RemoteToolset(session, schemas=[], has_policy_view=True)
    records = await toolset.policy_view([{"tool": "get_record", "arguments": {"id": "R1"}}])
    assert records == {"R1": {"value": 42}}
    assert session.calls[0][0] == POLICY_VIEW_TOOL


async def test_policy_view_swallows_errors():
    class _Boom:
        async def call_tool(self, name, args):
            raise RuntimeError("boom")

    toolset = RemoteToolset(_Boom(), schemas=[], has_policy_view=True)
    assert await toolset.policy_view([]) == {}
