"""
Reference connector entrypoint.

Serves a JSON data file as an MCP server over streamable-HTTP. Configure with:

  CONNECTOR_DATA  path to the JSON record file   (required)
  CONNECTOR_NAME  MCP server name                (default: data file stem)
  CONNECTOR_HOST  bind host                       (default: 0.0.0.0)
  CONNECTOR_PORT  bind port                       (default: 9000)

The MCP endpoint is then served at http://<host>:<port>/mcp.
"""

import os
from pathlib import Path

from mycel.connector.server import build_mcp_server
from mycel.node.datastore import DataStore


def run() -> None:
    from dotenv import load_dotenv

    load_dotenv()  # for running the connector outside docker

    data_path = os.environ.get("CONNECTOR_DATA")
    if not data_path:
        raise RuntimeError("CONNECTOR_DATA must point at a JSON record file")

    name = os.environ.get("CONNECTOR_NAME") or Path(data_path).stem
    host = os.environ.get("CONNECTOR_HOST", "0.0.0.0")
    port = int(os.environ.get("CONNECTOR_PORT", "9000"))

    store = DataStore(data_path)
    mcp = build_mcp_server(name, store, host=host, port=port)
    mcp.run(transport="streamable-http")
