"""
Node registry.

A flat YAML file mapping node identities to capabilities and endpoints.
Deliberately simple — upgrade to Consul/service mesh only when needed.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel


class NodeEntry(BaseModel):
    id: str
    title: str
    description: str
    endpoint: str


class Registry(BaseModel):
    nodes: list[NodeEntry]

    def get(self, node_id: str) -> NodeEntry | None:
        return next((n for n in self.nodes if n.id == node_id), None)

    def describe(self) -> str:
        """Capability overview fed to the planner LLM."""
        return "\n".join(
            f"- {n.id} ({n.title}): {n.description.strip()}" for n in self.nodes
        )


def load_registry(path: str | Path = "registry.yaml") -> Registry:
    with Path(path).open() as f:
        return Registry(**yaml.safe_load(f))
