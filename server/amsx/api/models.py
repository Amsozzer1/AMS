"""api.models — the HTTP wire contract: every request and response body, and nothing else.

This module owns ONE job: the shapes that cross the network boundary. Routes live in
``api/__init__.py``; domain objects live in ``amsx.types``. Keeping the wire contract
separate is what lets the frontend's TypeScript types be *generated* from this file's
OpenAPI schema instead of hand-mirrored (and silently drifting).

Every model here mirrors what the route already returned as a plain dict — these are
faithful translations, not a redesign of the API.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator

from ..inventory.resolver import ProposedRow
from ..orchestration import Orchestrator
from ..types import Spool as DomainSpool

# ---- requests -------------------------------------------------------------------------


class SpoolCreate(BaseModel):
    """Request body for POST /api/spools."""

    material: str
    color_hex: str | None = None
    name: str | None = None
    vendor: str | None = None
    initial_g: float = 1000.0
    module: str | None = None
    location: str | None = None


class SpoolUpdate(BaseModel):
    """Request body for PATCH /api/spools/{spool_id}."""

    remaining_g: float | None = None
    location: str | None = None
    archived: bool | None = None


# ---- generic acks ---------------------------------------------------------------------


class OkResponse(BaseModel):
    """Bare success ack (PUT /loadout, POST /job/assignment)."""

    ok: bool = True


class DeleteResult(BaseModel):
    """DELETE /api/spools/{spool_id}."""

    ok: bool = True
    id: str


# ---- health ---------------------------------------------------------------------------


class Health(BaseModel):
    """GET /health."""

    ok: bool
    simulate: bool
    printers: list[str]
    modules: int


# ---- printer --------------------------------------------------------------------------


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


# ---- job ------------------------------------------------------------------------------


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


# ---- prompts --------------------------------------------------------------------------


class Prompt(BaseModel):
    """One pending human-swap action the orchestrator is blocked on."""

    id: str
    module_id: str
    message: str


class AnswerResult(BaseModel):
    """POST /api/prompts/{prompt_id}/answer."""

    ok: bool = True
    prompt_id: str


# ---- orchestrator ---------------------------------------------------------------------


class OrchestratorSwap(BaseModel):
    """One swap in the armed plan, flagged when it is the cursor's current target."""

    seq: int
    filament_index: int
    tag: str
    current: bool


class OrchestratorArmed(BaseModel):
    """The live swap loop for a printer with a job armed."""

    armed: Literal[True] = True
    printer_id: str
    cursor: int
    total: int
    done: bool
    held: bool
    swap_state: str
    alerts: list[str]
    swaps: list[OrchestratorSwap]

    @classmethod
    def from_orchestrator(cls, orch: Orchestrator) -> OrchestratorArmed:
        return cls(
            printer_id=orch.printer_id,
            cursor=orch.cursor,
            total=len(orch.plan),
            done=orch.done,
            held=orch.held,
            swap_state=str(orch.sm.state),
            alerts=list(orch.alerts),
            swaps=[
                OrchestratorSwap(
                    seq=sw.seq,
                    filament_index=sw.filament_index,
                    tag=sw.tag,
                    current=i == orch.cursor,
                )
                for i, sw in enumerate(orch.plan.swaps)
            ],
        )


class OrchestratorIdle(BaseModel):
    """No job armed for this printer yet."""

    armed: Literal[False] = False
    printer_id: str


# A plain union, NOT Field(discriminator="armed"). Pydantic renders a discriminator mapping
# with Python's "True"/"False" string keys, which makes openapi-typescript type the tag as the
# *string* "True" instead of the boolean the server actually sends. Left as a bare union, each
# member's `armed: Literal[...]` becomes a JSON-schema const and TypeScript narrows on it
# correctly. Pydantic's smart-union matching picks the right member on its own.
OrchestratorStatus = OrchestratorArmed | OrchestratorIdle


# ---- inventory ------------------------------------------------------------------------


class ModuleInfo(BaseModel):
    """One configured AMS module. ``filament_index`` is null when the slot is unmapped."""

    id: str
    cluster_id: str
    filament_index: int | None


class Spool(BaseModel):
    """One physical spool from the inventory. ``color_hex`` is bare 6-hex RRGGBB (no '#')."""

    id: str
    filament_id: str
    material: str | None
    color_hex: str | None
    name: str | None
    remaining_g: float | None
    module: str | None
    archived: bool

    @classmethod
    def from_domain(cls, s: DomainSpool) -> Spool:
        return cls(
            id=s.id,
            filament_id=s.filament_id,
            material=s.material,
            color_hex=s.color_hex,
            name=s.name,
            remaining_g=s.remaining_g,
            module=s.module,
            archived=s.archived,
        )


class LoadoutRow(BaseModel):
    """One configured module and the spool currently loaded in it (null when empty)."""

    module: str
    spool: Spool | None


class AssignRow(BaseModel):
    """One filament index from the armed plan with the module/spool the resolver proposed."""

    index: int
    material: str | None
    color_hex: str | None
    grams: float | None
    module: str | None
    spool_id: str | None
    status: Literal["loaded", "gap"]

    @classmethod
    def from_proposed(cls, row: ProposedRow) -> AssignRow:
        return cls(
            index=row.index,
            material=row.material,
            color_hex=row.color_hex,
            grams=row.grams,
            module=row.module,
            spool_id=row.spool_id,
            status=row.status,
        )


class AssignmentResponse(BaseModel):
    """GET /api/printers/{id}/job/assignment. ``rows`` is empty when nothing is armed."""

    rows: list[AssignRow]
    confirmed: bool


# ---- simulate-only test hooks ---------------------------------------------------------


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
