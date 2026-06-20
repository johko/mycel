"""
Device / runtime profile.

A loosely-specified file describing the machine a process runs on and the
inference backend it should use. The `hardware` block is advisory (hints that
could later drive automatic model selection); `backend` is the authoritative
choice. Selected via the DEVICE_PROFILE env var; absent it, processes use the
Hugging Face default and behave exactly as before.

This decouples a node's *identity* (which department) from *where its brain
runs*, which is what lets the same image ship as cloud / on-prem / edge
deployment templates.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from mycel.llm import BackendConfig


class DeviceProfile(BaseModel):
    name: str
    hardware: dict = Field(default_factory=dict)
    backend: BackendConfig


def load_device_profile(path: str | Path) -> DeviceProfile:
    with Path(path).open() as f:
        return DeviceProfile(**yaml.safe_load(f))
