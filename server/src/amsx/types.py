"""Shared value objects, enums, and data contracts — the kernel every layer depends on.

Design source: docs/10-domain-model.md ("Value objects & enums") and docs/06-module-interface.md.
These types are the stable seams between the layers (transport / printer / job / module /
orchestration) so each can be built independently. Keep this module dependency-free (stdlib only).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

# ---- stable string ids (aliases, not new types, to stay friendly to YAML/JSON) ----
PrinterId = str
ClusterId = str
ModuleId = str


# ---- enums ----
class PrinterStage(StrEnum):
    """Coarse printer state, mirrored from the report stream into PrinterState.stage."""

    IDLE = "IDLE"
    PRINTING = "PRINTING"
    PAUSED = "PAUSED"
    ERROR = "ERROR"
    FINISHED = "FINISHED"


class PauseReason(StrEnum):
    """Why the printer is paused — CHANGE is ours to act on; USER/ERROR are exceptions."""

    CHANGE = "CHANGE"
    USER = "USER"
    ERROR = "ERROR"
    UNKNOWN = "UNKNOWN"


class ModuleState(StrEnum):
    """Module state machine (docs/06-module-interface.md)."""

    IDLE = "IDLE"
    FEEDING = "FEEDING"
    RETRACTING = "RETRACTING"
    FAULT = "FAULT"
    EMPTY = "EMPTY"


class SwapState(StrEnum):
    """Orchestrator's per-swap state machine (docs/10-domain-model.md)."""

    WATCHING = "WATCHING"
    UNLOADING = "UNLOADING"
    SELECTING = "SELECTING"
    FEEDING = "FEEDING"
    SENSING = "SENSING"
    RESUMING = "RESUMING"
    FAULT = "FAULT"


# ---- value objects ----
@dataclass(frozen=True)
class FilamentRef:
    """What the Brain believes is (or should be) loaded. `index` is the M1020 S<n> value."""

    index: int
    material: str | None = None
    color: str | None = None
    spool_id: str | None = None


@dataclass(frozen=True)
class MoveResult:
    """Result of a bounded module move (feed/retract)."""

    ok: bool
    reason: str | None = None
    moved_mm: float | None = None


@dataclass(frozen=True)
class PlannedSwap:
    """One material change parsed from the job. `seq` matches the k-th M400 U1 pause.

    `filament_index` comes from the governing `M1020 S<n>`. `tag` lets the orchestrator
    validate a live pause against the plan (docs/09-filament-change-protocol.md).
    """

    seq: int
    filament_index: int
    tag: str
    layer: int | None = None
    line: int | None = None  # gcode line of this swap's M400 U1 (the #17 ordinal+line guard)


@dataclass(frozen=True)
class SwapPlan:
    """Ordered material-change plan produced by JobParser; consumed by the Orchestrator."""

    swaps: list[PlannedSwap] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.swaps)
