"""
Node registry.

A flat YAML file mapping node identities to capabilities and endpoints.
Deliberately simple — upgrade to Consul/service mesh only when needed.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class NodeEntry(BaseModel):
    id: str
    title: str
    description: str
    endpoint: str
    # display-only hint for UIs: "deny" | "redact" | "oblige"
    policy_mode: str | None = None
    # keyword list of the data this node holds; helps the planner route, and
    # shared tags across nodes signal where data overlaps (and can be corroborated)
    tags: list[str] = Field(default_factory=list)


class Registry(BaseModel):
    nodes: list[NodeEntry]

    def get(self, node_id: str) -> NodeEntry | None:
        return next((n for n in self.nodes if n.id == node_id), None)

    def describe(self) -> str:
        """Capability overview fed to the planner LLM."""
        lines = []
        for n in self.nodes:
            tags = f" [data: {', '.join(n.tags)}]" if n.tags else ""
            lines.append(f"- {n.id} ({n.title}){tags}: {n.description.strip()}")
        return "\n".join(lines)


def load_registry(path: str | Path = "registry.yaml") -> Registry:
    with Path(path).open() as f:
        return Registry(**yaml.safe_load(f))
