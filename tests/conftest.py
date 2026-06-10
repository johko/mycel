import json

import pytest

from mycel.node.config import NodeConfig


@pytest.fixture
def node_config(tmp_path) -> NodeConfig:
    data = {
        "R1": {"label": "record one", "value": 42, "sensitivity": "high"},
        "R2": {"label": "record two", "value": 7, "sensitivity": "low"},
    }
    data_path = tmp_path / "data.json"
    data_path.write_text(json.dumps(data))
    return NodeConfig(
        id="test-node",
        title="Test Node",
        description="A node for tests.",
        system_prompt="You are a test node.",
        data_path=data_path,
        opa_url="http://opa.test",
        audit_log_path=tmp_path / "audit.log",
    )
