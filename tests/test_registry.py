import pytest

from mycel.orchestrator.registry import load_registry

REGISTRY_YAML = """\
nodes:
  - id: energy-wizards
    title: Energy Wizards
    description: Energy data, aggregates only.
    endpoint: http://localhost:8001
  - id: archivists
    title: Archivists
    description: History, PII redacted.
    endpoint: http://localhost:8003
"""


@pytest.fixture
def registry(tmp_path):
    path = tmp_path / "registry.yaml"
    path.write_text(REGISTRY_YAML)
    return load_registry(path)


def test_load_registry(registry):
    assert [n.id for n in registry.nodes] == ["energy-wizards", "archivists"]


def test_get(registry):
    assert registry.get("archivists").endpoint == "http://localhost:8003"
    assert registry.get("unknown") is None


def test_describe_mentions_all_nodes(registry):
    description = registry.describe()
    assert "energy-wizards" in description
    assert "Archivists" in description
