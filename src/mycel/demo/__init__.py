"""
Mycel demo — the MICE (Magical Institute for Commons and Energy) scenario.

This subpackage carries the demo's *content*: five department data files, node
configs, OPA policies, a registry, and a docker-compose stack — plus the
reference ``connector`` (a runnable MCP server with JSON/SQL/RAG backends). None
of the core framework lives here; a real deployment replaces the connector with
the company's own MCP server. Install it with ``pip install mycel[demo]`` and lay
the assets down with the ``mycel-demo`` command.
"""

from pathlib import Path

# Directory holding the bundled demo assets (data, nodes, opa, registry, compose).
ASSETS = Path(__file__).resolve().parent / "assets"
