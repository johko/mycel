"""
Node configuration.

A Diplomat node is one generic codebase; its identity (department, prompt,
data store, policy endpoint) comes entirely from a YAML config file pointed
to by the NODE_CONFIG env var. Env vars override deployment-specific fields.
"""

import os
from pathlib import Path

import yaml
from pydantic import BaseModel

from mycel.llm import DEFAULT_MODEL


class NodeConfig(BaseModel):
    id: str
    title: str
    description: str
    system_prompt: str
    data_path: Path
    opa_url: str = "http://localhost:8181"
    audit_log_path: Path = Path("logs/audit.log")
    model: str = DEFAULT_MODEL


def load_config(path: str | Path | None = None) -> NodeConfig:
    config_path = Path(path or os.environ.get("NODE_CONFIG", "nodes/energy.yaml"))
    with config_path.open() as f:
        raw = yaml.safe_load(f)

    for env_var, field in [
        ("OPA_URL", "opa_url"),
        ("AUDIT_LOG_PATH", "audit_log_path"),
        ("DATA_PATH", "data_path"),
        ("NODE_MODEL", "model"),
    ]:
        if os.environ.get(env_var):
            raw[field] = os.environ[env_var]

    return NodeConfig(**raw)
