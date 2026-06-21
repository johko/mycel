"""
Reference MCP connector.

A standalone, runnable MCP server with three interchangeable backends — a flat
JSON record store, an in-memory SQLite database, and an in-memory Qdrant RAG
index — selected via ``CONNECTOR_KIND``. It is the *reference* for the data
connector a company runs in their own environment: copy a backend, or replace it
with a server backed by their real data sources. The agent container speaks to
it purely over MCP, so the contract is "expose an MCP server", not "use this
implementation".

A connector that wants the node's OPA egress layer to govern record fields
(rather than raw observations) implements the well-known ``policy_view`` tool,
which maps the agent's observation log to a canonical ``{id: record}`` map.
"""
