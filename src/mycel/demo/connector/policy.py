"""
The `policy_view` tool — a connector's opt-in hook into the node's OPA layer.

A connector that wants the egress policy to govern *record fields* (rather than
raw tool observations) registers this well-known tool. After the agent loop the
node calls it with the observation log and hands the returned `{id: record}` map
to OPA as `input.records`. Because the connector owns its data shapes, it — not
the node — decides what a "record" looks like, so the rego author controls the
policy input from their own connector code.

The tool is reserved: the node hides it from the LLM's tool list (see
`mycel.node.mcp_client.POLICY_VIEW_TOOL`), so it never appears as an agent tool.
"""

from collections.abc import Callable

from mcp.server.fastmcp import FastMCP

# Must match mycel.node.mcp_client.POLICY_VIEW_TOOL — a protocol convention.
POLICY_VIEW_TOOL = "policy_view"


def policy_view_tool(
    mcp: FastMCP, to_records: Callable[[list[dict]], dict[str, dict]]
) -> None:
    """Register `policy_view`, delegating the mapping to `to_records`."""

    @mcp.tool(
        name=POLICY_VIEW_TOOL,
        description=(
            "Reserved for the egress policy layer: maps an observation log to the "
            "canonical {id: record} view the policy evaluates. Not for agent use."
        ),
    )
    def policy_view(observations: list[dict]) -> dict[str, dict]:
        return to_records(observations or [])
