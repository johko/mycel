"""
MCP server for the reference connector (JSON backend).

Exposes a DataStore's records as MCP tools (`list_records` / `get_record`)
over the streamable-HTTP transport at /mcp. These two tools are just the
reference contract — a company's connector may expose any tools it likes; the
agent discovers whatever is offered at runtime.

It also implements `policy_view` (see `policy_view_tool`), the well-known tool
the node calls to turn the agent's observation log into the canonical
`{id: record}` map the OPA egress policies read.
"""

from mcp.server.fastmcp import FastMCP

from mycel.demo.connector.datastore import DataStore
from mycel.demo.connector.policy import policy_view_tool


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

    def to_records(observations: list[dict]) -> dict[str, dict]:
        """Map this connector's `get_record` results to {id: record}."""
        records: dict[str, dict] = {}
        for obs in observations:
            if obs.get("tool") != "get_record":
                continue
            result = obs.get("result")
            rec_id = (obs.get("arguments") or {}).get("id")
            if isinstance(rec_id, str) and isinstance(result, dict) and "error" not in result:
                records[rec_id] = result
        return records

    policy_view_tool(mcp, to_records)
    return mcp
