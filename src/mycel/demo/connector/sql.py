"""
SQLite connector backend.

Loads a `.sql` seed script into an in-memory, read-only SQLite database and
exposes it over MCP as a small relational tool surface: `list_tables`,
`describe_table`, and a read-only `query`. It demonstrates a connector whose
data source is a database rather than a flat file — the agent composes SQL
instead of fetching records by id.

For OPA governance it implements `policy_view`: each row a `query` returned is
treated as a record (rows carry a `source` column), so record-oriented egress
policies apply unchanged.
"""

import sqlite3
import threading
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from mycel.demo.connector.policy import policy_view_tool


class SqlStore:
    """An in-memory, read-only SQLite database seeded from a `.sql` script."""

    def __init__(self, path: str | Path):
        # check_same_thread=False: FastMCP runs sync tools in worker threads.
        self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._conn.executescript(Path(path).read_text())
        self._conn.commit()
        self._conn.execute("PRAGMA query_only = ON")

    def list_tables(self) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        return [r["name"] for r in rows]

    def describe_table(self, table: str) -> dict:
        if table not in self.list_tables():
            return {"error": f"table {table!r} not found"}
        with self._lock:
            cols = self._conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {
            "table": table,
            "columns": [{"name": c["name"], "type": c["type"]} for c in cols],
        }

    @staticmethod
    def _is_read_only(sql: str) -> bool:
        stripped = sql.strip().rstrip(";").strip()
        if not stripped or ";" in stripped:  # empty or multiple statements
            return False
        return stripped.split(None, 1)[0].lower() in ("select", "with")

    def query(self, sql: str) -> object:
        """Run one read-only SELECT/WITH and return rows as a list of dicts."""
        if not self._is_read_only(sql):
            return {"error": "only a single read-only SELECT/WITH query is allowed"}
        try:
            with self._lock:
                rows = self._conn.execute(sql).fetchall()
        except sqlite3.Error as exc:
            return {"error": f"query failed: {exc}"}
        return [dict(r) for r in rows]


def _records_from_observations(observations: list[dict]) -> dict[str, dict]:
    """Map `query` result rows to {id: record} for the egress policy.

    Each returned row is a record; rows carry a `source` column so attribution
    policies fire. Keyed by the row's `id` column when present, else synthesized.
    """
    records: dict[str, dict] = {}
    n = 0
    for obs in observations:
        if obs.get("tool") != "query":
            continue
        result = obs.get("result")
        # a single-row result is reduced to one dict; many rows arrive as a list
        rows = result if isinstance(result, list) else [result]
        for row in rows:
            if not isinstance(row, dict) or "error" in row:
                continue
            rec_id = row.get("id")
            key = str(rec_id) if rec_id is not None else f"sql:{n}"
            records[key] = row
            n += 1
    return records


def build_sql_server(
    name: str, store: SqlStore, *, host: str = "0.0.0.0", port: int = 9000
) -> FastMCP:
    mcp = FastMCP(name, host=host, port=port)

    @mcp.tool(description="List the names of all tables in the database.")
    def list_tables() -> list[str]:
        return store.list_tables()

    @mcp.tool(description="Describe a table's columns and their types.")
    def describe_table(table: str) -> dict:
        return store.describe_table(table)

    @mcp.tool(
        description=(
            "Run one read-only SQL query (a single SELECT or WITH statement) and "
            "return the matching rows. Use list_tables/describe_table first."
        )
    )
    def query(sql: str) -> object:
        return store.query(sql)

    policy_view_tool(mcp, _records_from_observations)
    return mcp
