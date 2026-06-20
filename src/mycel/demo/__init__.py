"""
Mycel demo — the MICE (Magical Institute for Commons and Energy) scenario.

This subpackage carries the demo's *content* only: five department data files,
node configs, OPA policies, a registry, and a docker-compose stack. None of the
core framework lives here. Install it with ``pip install mycel[demo]`` and lay
the assets down with the ``mycel-demo`` command.
"""

from pathlib import Path

# Directory holding the bundled demo assets (data, nodes, opa, registry, compose).
ASSETS = Path(__file__).resolve().parent / "assets"
