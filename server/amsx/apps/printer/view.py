"""printer — the wire shapes for the live printer snapshot and the simulate-only hooks."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator

__all__ = [
    "LoadedFilament",
    "PrinterDetail",
    "PrinterState",
    "Progress",
    "SimPauseResult",
    "SimSensorResult",
]


class Progress(BaseModel):
    """Best-effort progress from the printer report.

    The server writes ``layer`` / ``percent`` / ``line`` straight off the report in
    ``Printer._apply_fields`` **without validating them** — only the pause guard's
    ``_progress_layer()`` filters non-ints, and that happens at read time, not write time.
    So a firmware reporting ``layer_num: 12.5`` (or a non-numeric string) really can land in
    ``state.progress``.

    Before these models existed the route returned that dict verbatim and never failed. A
    plain ``int | None`` would instead raise ``ValidationError`` and 500 EVERY printer-state
    response — ``/api/printers``, ``/{id}``, and ``/{id}/detail`` — taking the whole dashboard
    down over one odd field. The validator below keeps the old never-fails behaviour: a value
    that is not cleanly numeric is reported as absent, which is what the server already
    believes when it makes decisions.

    ``extra="allow"`` keeps any future report key from being silently dropped on the way out.
    """

    # Defaults stay HERE (unlike the other response models): these keys are genuinely
    # absent until the printer reports them, so `?` in the generated TS is accurate.
    model_config = ConfigDict(extra="allow")

    layer: int | None = None
    percent: float | None = None
    line: int | None = None

    @field_validator("layer", "line", mode="before")
    @classmethod
    def _int_or_absent(cls, v: object) -> int | None:
        """Report a non-integral value as absent rather than 500-ing the response."""
        if isinstance(v, bool) or v is None:
            return None
        if isinstance(v, int):
            return v
        if isinstance(v, float) and v.is_integer():
            return int(v)
        if isinstance(v, str) and v.strip().lstrip("-").isdigit():
            return int(v)
        return None

    @field_validator("percent", mode="before")
    @classmethod
    def _float_or_absent(cls, v: object) -> float | None:
        if isinstance(v, bool) or v is None:
            return None
        if isinstance(v, int | float):
            return float(v)
        if isinstance(v, str):
            try:
                return float(v.strip())
            except ValueError:
                return None
        return None


class LoadedFilament(BaseModel):
    """What the Brain believes is loaded — Pi-authoritative, never set from a report."""

    index: int
    material: str | None
    color: str | None


class PrinterState(BaseModel):
    """GET /api/printers and GET /api/printers/{id} — the modeled printer snapshot."""

    id: str
    stage: str
    pause_reason: str | None
    filament_sensor: bool
    progress: Progress
    loaded_filament: LoadedFilament | None

    @classmethod
    def from_printer(cls, printer: Any) -> PrinterState:
        s = printer.state
        loaded = s.loaded_filament
        return cls(
            id=printer.id,
            stage=str(s.stage),
            pause_reason=str(s.pause_reason) if s.pause_reason is not None else None,
            filament_sensor=s.filament_sensor,
            progress=Progress(**s.progress),
            loaded_filament=(
                LoadedFilament(index=loaded.index, material=loaded.material, color=loaded.color)
                if loaded is not None
                else None
            ),
        )


class PrinterDetail(PrinterState):
    """GET /api/printers/{id}/detail — modeled state + identity + the full raw report.

    ``raw`` is the deep-merged snapshot of the printer's own report (temps, fans, wifi, ams,
    ipcam, ...). It is printer- and firmware-dependent, so it stays open JSON and is rendered
    generically by the UI. The access code is never included.
    """

    # `model` is a plain field name here, not Pydantic's reserved `model_` namespace.
    model_config = ConfigDict(protected_namespaces=())

    serial: str
    model: str
    ip: str | None
    simulate: bool
    connected: bool
    seeded: bool
    raw: dict[str, Any]


class SimPauseResult(BaseModel):
    """POST /api/printers/{id}/sim/pause — echoes which form of pause was injected."""

    injected: Literal["pause"] = "pause"
    printer_id: str
    tag: str | None = None
    line: int | None = None


class SimSensorResult(BaseModel):
    """POST /api/printers/{id}/sim/sensor."""

    injected: Literal["sensor"] = "sensor"
    printer_id: str
    filament_present: bool
