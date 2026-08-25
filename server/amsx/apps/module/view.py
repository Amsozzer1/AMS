"""module — the wire shape for a configured AMS module."""

from __future__ import annotations

from pydantic import BaseModel

__all__ = ["ModuleInfo"]


class ModuleInfo(BaseModel):
    """One configured AMS module. ``filament_index`` is null when the slot is unmapped."""

    id: str
    cluster_id: str
    filament_index: int | None
