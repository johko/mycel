"""
Reference connector entrypoint.

Serves a data source as an MCP server over streamable-HTTP. The backend is
selected by CONNECTOR_KIND; each reads its seed from CONNECTOR_DATA:

  CONNECTOR_KIND  json | sql | rag                 (default: json)
  CONNECTOR_DATA  path to the seed file            (required)
                    json -> JSON record file
                    sql  -> SQLite .sql seed script
                    rag  -> JSON document file
  CONNECTOR_NAME  MCP server name                  (default: data file stem)
  CONNECTOR_HOST  bind host                         (default: 0.0.0.0)
  CONNECTOR_PORT  bind port                         (default: 9000)

The MCP endpoint is then served at http://<host>:<port>/mcp.
"""

import os
from pathlib import Path


def _build(kind: str, name: str, data_path: str, host: str, port: int):
    """Build the MCP server for `kind`, importing the backend lazily.

    Lazy import keeps the json/sql connectors free of the qdrant/fastembed
    dependency, which only the rag backend needs.
    """
    if kind == "json":
        from mycel.demo.connector.datastore import DataStore
        from mycel.demo.connector.server import build_mcp_server

        return build_mcp_server(name, DataStore(data_path), host=host, port=port)
    if kind == "sql":
        from mycel.demo.connector.sql import SqlStore, build_sql_server

        return build_sql_server(name, SqlStore(data_path), host=host, port=port)
    if kind == "rag":
        from mycel.demo.connector.rag import RagStore, build_rag_server

        return build_rag_server(name, RagStore(data_path), host=host, port=port)
    raise RuntimeError(
        f"unknown CONNECTOR_KIND {kind!r} (expected one of: json, sql, rag)"
    )


def run() -> None:
    from dotenv import load_dotenv

    load_dotenv()  # for running the connector outside docker

    data_path = os.environ.get("CONNECTOR_DATA")
    if not data_path:
        raise RuntimeError("CONNECTOR_DATA must point at a seed file")

    kind = os.environ.get("CONNECTOR_KIND", "json")
    name = os.environ.get("CONNECTOR_NAME") or Path(data_path).stem
    host = os.environ.get("CONNECTOR_HOST", "0.0.0.0")
    port = int(os.environ.get("CONNECTOR_PORT", "9000"))

    mcp = _build(kind, name, data_path, host, port)
    mcp.run(transport="streamable-http")
