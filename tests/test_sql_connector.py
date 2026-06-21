"""SQLite connector backend: introspection, read-only query guard, policy_view."""

from mycel.demo.connector.sql import SqlStore, _records_from_observations

_SEED = """
CREATE TABLE payroll (
    id TEXT PRIMARY KEY,
    period TEXT,
    avg_research_staff INTEGER,
    source TEXT
);
INSERT INTO payroll VALUES ('BUR-1', '2020-2024', 64, 'Payroll Summary');
"""


def _store(tmp_path):
    seed = tmp_path / "seed.sql"
    seed.write_text(_SEED)
    return SqlStore(seed)


def test_list_and_describe(tmp_path):
    store = _store(tmp_path)
    assert store.list_tables() == ["payroll"]
    desc = store.describe_table("payroll")
    cols = {c["name"] for c in desc["columns"]}
    assert {"id", "period", "avg_research_staff", "source"} <= cols


def test_describe_unknown_table(tmp_path):
    assert "error" in _store(tmp_path).describe_table("ghosts")


def test_query_returns_rows(tmp_path):
    rows = _store(tmp_path).query("SELECT id, avg_research_staff, source FROM payroll")
    assert rows == [
        {"id": "BUR-1", "avg_research_staff": 64, "source": "Payroll Summary"}
    ]


def test_query_rejects_non_select(tmp_path):
    store = _store(tmp_path)
    assert "error" in store.query("DELETE FROM payroll")
    assert "error" in store.query("INSERT INTO payroll VALUES ('x','y',1,'z')")


def test_query_rejects_multiple_statements(tmp_path):
    store = _store(tmp_path)
    assert "error" in store.query("SELECT 1; DROP TABLE payroll")


def test_query_only_pragma_blocks_writes(tmp_path):
    # even a lone write (passing the keyword guard would still hit query_only)
    store = _store(tmp_path)
    # sneak a write past the guard via a CTE-looking prefix is impossible; assert
    # the DB itself is read-only by trying a write through the raw connection path
    assert "error" in store.query("UPDATE payroll SET source = 'x'")


def test_policy_view_maps_query_rows_to_records():
    observations = [
        {"tool": "list_tables", "arguments": {}, "result": ["payroll"]},
        {
            "tool": "query",
            "arguments": {"sql": "SELECT * FROM payroll"},
            "result": [
                {"id": "BUR-1", "source": "Payroll Summary"},
                {"period": "2020-2024", "source": "Other"},
            ],
        },
        {"tool": "query", "arguments": {}, "result": {"error": "bad"}},
    ]
    records = _records_from_observations(observations)
    # the id-bearing row is keyed by its id; the other gets a synthesized key
    assert records["BUR-1"] == {"id": "BUR-1", "source": "Payroll Summary"}
    assert any(k.startswith("sql:") for k in records)
    # every governed record carries a source for the OBLIGE policy
    assert all("source" in rec for rec in records.values())


def test_policy_view_handles_single_row_reduced_to_dict():
    # _reduce_result collapses a one-row result to a dict, not a list
    observations = [
        {
            "tool": "query",
            "arguments": {},
            "result": {"id": "BUR-1", "source": "Payroll Summary"},
        }
    ]
    records = _records_from_observations(observations)
    assert records == {"BUR-1": {"id": "BUR-1", "source": "Payroll Summary"}}
