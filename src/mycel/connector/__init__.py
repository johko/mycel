"""
Reference MCP connector.

A standalone, runnable MCP server that exposes a flat JSON file as record
tools. It is the *reference* for the data connector a company runs in their
own environment: copy it, or replace it with a server backed by their real
data sources (SQL, search, internal APIs). The agent container speaks to it
purely over MCP, so the contract is "expose an MCP server", not "use this
implementation".
"""
