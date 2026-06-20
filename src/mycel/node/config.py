"""
Node configuration.

A Diplomat node is one generic codebase; its identity (department, prompt,
data source, policy endpoint) comes entirely from a YAML config file pointed
to by the NODE_CONFIG env var. Env vars override deployment-specific fields.

The node's agent is an MCP *client*: it reasons over whatever tools a remote
MCP server (`mcp.url`) exposes. The container ships no data of its own — what
the agent can see is exactly what that server chooses to expose.
"""

import os
from pathlib import Path

import yaml
from pydantic import BaseModel

from mycel.llm import DEFAULT_MODEL, BackendConfig


class McpClientConfig(BaseModel):
    """Where the node's agent connects to fetch data.

    `url` is a remote MCP server's streamable-HTTP endpoint (the company's
    data connector). `headers` carries optional auth (e.g. a bearer token).
    """

    url: str
    headers: dict[str, str] | None = None


class NodeConfig(BaseModel):
    id: str
    title: str
    description: str
    system_prompt: str
    # remote MCP server the agent connects to for data; required at runtime
    mcp: McpClientConfig | None = None
    # legacy/demo: a local JSON file. Only the reference connector reads this;
    # the agent container no longer touches data directly.
    data_path: Path | None = None
    # egress policy endpoint; None => OPA disabled (no egress safety net)
    opa_url: str | None = None
    audit_log_path: Path = Path("logs/audit.log")
    model: str = DEFAULT_MODEL
    # where this node's agent runs inference; None => HF router (default)
    backend: BackendConfig | None = None


def load_config(path: str | Path | None = None) -> NodeConfig:
    config_path = path or os.environ.get("NODE_CONFIG")
    if not config_path:
        raise RuntimeError(
            "no node config given — set NODE_CONFIG to a node YAML "
            "(e.g. nodes/energy.yaml from `mycel-demo init`)"
        )
    config_path = Path(config_path)
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

    # The remote MCP server can come from YAML (`mcp.url`) or be injected at
    # deploy time via MCP_URL (+ optional MCP_AUTH_TOKEN bearer header).
    if os.environ.get("MCP_URL"):
        mcp_raw = raw.get("mcp") or {}
        mcp_raw["url"] = os.environ["MCP_URL"]
        raw["mcp"] = mcp_raw
    if os.environ.get("MCP_AUTH_TOKEN") and raw.get("mcp"):
        headers = dict(raw["mcp"].get("headers") or {})
        headers["Authorization"] = f"Bearer {os.environ['MCP_AUTH_TOKEN']}"
        raw["mcp"]["headers"] = headers

    config = NodeConfig(**raw)

    # A device profile (DEVICE_PROFILE) points this node at a local/self-hosted
    # model. Its backend.model wins unless NODE_MODEL was set explicitly.
    profile_path = os.environ.get("DEVICE_PROFILE")
    if profile_path:
        from mycel.device import load_device_profile

        profile = load_device_profile(profile_path)
        config.backend = profile.backend
        if profile.backend.model and not os.environ.get("NODE_MODEL"):
            config.model = profile.backend.model

    return config
