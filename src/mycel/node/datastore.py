"""
Record store for a Diplomat node.

A flat JSON file mapping record IDs to record dicts. Inside its own
environment the agent has full, unfiltered access — data sovereignty is
enforced at egress by the policy layer, not by hiding data from the agent.
"""

import json
from pathlib import Path


class DataStore:
    def __init__(self, path: str | Path):
        self._records: dict[str, dict] = json.loads(Path(path).read_text())

    def list_records(self) -> list[dict]:
        """Record IDs with a short label, for discovery."""
        return [
            {"id": record_id, "label": record.get("label", record_id)}
            for record_id, record in self._records.items()
        ]

    def get_record(self, record_id: str) -> dict:
        record = self._records.get(record_id)
        if record is None:
            return {"error": f"record {record_id!r} not found"}
        return record

    @property
    def records(self) -> dict[str, dict]:
        return self._records
