"""config — declarative wiring loaded from ams.json. Shape mirrors docs/10-domain-model.md.

Secrets (serial / access_code) live only in ams.local.json (gitignored); never commit real
values. See SECURITY.md.

JSON has no comments, so what used to be a YAML comment now lives in the field's
``description=`` — which keeps it next to the field it documents and makes it readable by
tooling instead of only by humans.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field


class BusConfig(BaseModel):
    """Our own MQTT broker (Mosquitto on the CasaOS host) — not the printer's endpoint."""

    host: str = "127.0.0.1"
    port: int = 1883


class PrinterConfig(BaseModel):
    id: str
    model: str = Field(..., description="x1 | p1 | a1 — selects the PrinterDriver")
    serial: str
    access_code: str = Field(..., description="from the printer's LAN-mode network settings")
    ip: str


class ClusterConfig(BaseModel):
    id: str
    mqtt_topic: str = Field(..., description="the ESP32 subscribes/publishes here")
    module_ids: list[str] = Field(default_factory=list)


class ModuleConfig(BaseModel):
    id: str
    cluster_id: str
    filament_index: int | None = None
    spool_ref: str | None = None


class SpoolmanConfig(BaseModel):
    enabled: bool = True
    base_url: str = "http://localhost:7912/api/v1"
    active_location: str | None = Field(
        default=None,
        description="if set, only spools in this Spoolman location count as 'in the AMS'",
    )
    timeout: float = 5.0


class Config(BaseModel):
    bus: BusConfig = Field(default_factory=BusConfig)
    printers: list[PrinterConfig] = Field(default_factory=list)
    clusters: list[ClusterConfig] = Field(default_factory=list)
    modules: list[ModuleConfig] = Field(default_factory=list)
    hub: dict = Field(
        default_factory=dict,
        description="mostly informational for now (passive Y-connector per printer)",
    )
    spoolman: SpoolmanConfig = Field(default_factory=SpoolmanConfig)

    def module_for_filament_index(self, index: int) -> ModuleConfig | None:
        """Config-level mapping used by ModuleRegistry (Spoolman match comes later)."""
        for m in self.modules:
            if m.filament_index == index:
                return m
        return None


def load_config(path: str | Path) -> Config:
    """Load and validate an ams.json into a typed Config."""
    text = Path(path).read_text()
    data = json.loads(text) if text.strip() else {}
    return Config.model_validate(data)
