"""job — the wire shapes for uploading and starting a sliced job."""

from __future__ import annotations

from pydantic import BaseModel

__all__ = ["JobResult", "PlannedSwap", "StartArmedResult"]


class PlannedSwap(BaseModel):
    """One planned material change, as echoed back on upload."""

    seq: int
    filament_index: int
    tag: str


class JobResult(BaseModel):
    """POST /api/printers/{id}/job."""

    printer_id: str
    filename: str | None
    started: bool
    planned_swaps: list[PlannedSwap]


class StartArmedResult(BaseModel):
    """POST /api/printers/{id}/job/start."""

    printer_id: str
    started: bool
