"""config — declarative wiring loaded from ams.yaml. Shape mirrors docs/10-domain-model.md.

Secrets (serial / access_code) live only in ams.local.yaml (gitignored); never commit real
values. See SECURITY.md.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class BusConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 1883


class PrinterConfig(BaseModel):
    id: str
    model: str  # x1 | p1 | a1  -> selects the PrinterDriver
    serial: str
    access_code: str
    ip: str


class ClusterConfig(BaseModel):
    id: str
    mqtt_topic: str
    module_ids: list[str] = Field(default_factory=list)


class ModuleConfig(BaseModel):
    id: str
    cluster_id: str
    filament_index: int | None = None
    spool_ref: str | None = None


class SpoolmanConfig(BaseModel):
    enabled: bool = True
    base_url: str = "http://localhost:7912/api/v1"
    # if set, only spools in this Spoolman location are considered "in the AMS"
    active_location: str | None = None
    timeout: float = 5.0


class Config(BaseModel):
    bus: BusConfig = Field(default_factory=BusConfig)
    printers: list[PrinterConfig] = Field(default_factory=list)
    clusters: list[ClusterConfig] = Field(default_factory=list)
    modules: list[ModuleConfig] = Field(default_factory=list)
    hub: dict = Field(default_factory=dict)
    spoolman: SpoolmanConfig = Field(default_factory=SpoolmanConfig)

    def module_for_filament_index(self, index: int) -> ModuleConfig | None:
        """Config-level mapping used by ModuleRegistry (Spoolman match comes later)."""
        for m in self.modules:
            if m.filament_index == index:
                return m
        return None


def load_config(path: str | Path) -> Config:
    """Load and validate an ams.yaml into a typed Config."""
    text = Path(path).read_text()
    data = yaml.safe_load(text) or {}
    return Config.model_validate(data)
