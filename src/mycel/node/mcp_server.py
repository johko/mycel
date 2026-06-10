"""
MCP server for the Diplomat node.

Exposes the node's record tools via the Model Context Protocol
(streamable-HTTP transport), mounted into the FastAPI app at /mcp.
"""

from mcp.server.fastmcp import FastMCP

from mycel.node.config import NodeConfig
from mycel.node.datastore import DataStore


def build_mcp_server(config: NodeConfig, store: DataStore) -> FastMCP:
    # streamable_http_path="/" so the endpoint is exactly /mcp once the
    # app is mounted there (instead of /mcp/mcp)
    mcp = FastMCP(config.id, stateless_http=True, streamable_http_path="/")

    @mcp.tool(description="List all available record IDs with a short label.")
    def list_records() -> list[dict]:
        return store.list_records()

    @mcp.tool(description="Fetch the full contents of a record by ID.")
    def get_record(id: str) -> dict:
        return store.get_record(id)

    return mcp
