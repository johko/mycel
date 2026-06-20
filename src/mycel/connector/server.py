"""
MCP server for the reference connector.

Exposes a DataStore's records as MCP tools (`list_records` / `get_record`)
over the streamable-HTTP transport at /mcp. These two tools are just the
reference contract — a company's connector may expose any tools it likes; the
agent discovers whatever is offered at runtime.
"""

from mcp.server.fastmcp import FastMCP

from mycel.node.datastore import DataStore


def build_mcp_server(
    name: str, store: DataStore, *, host: str = "0.0.0.0", port: int = 9000
) -> FastMCP:
    mcp = FastMCP(name, host=host, port=port)

    @mcp.tool(description="List all available record IDs with a short label.")
    def list_records() -> list[dict]:
        return store.list_records()

    @mcp.tool(description="Fetch the full contents of a record by ID.")
    def get_record(id: str) -> dict:
        return store.get_record(id)

    return mcp
