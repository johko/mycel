"""Translation between MCP types and the agent's tool-calling contract."""

from types import SimpleNamespace

from mcp.types import CallToolResult, TextContent

from mycel.node.mcp_client import _reduce_result, _to_openai_tool


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
