"""enums — every closed set of states in the system, and nothing else.

Split out of the old ``types.py`` so a state machine's vocabulary is findable in one place.
All of these are ``StrEnum``: they compare equal to their own string value, which keeps them
JSON-serialisable and readable in logs without a ``.value`` everywhere.

Design source: docs/10-domain-model.md ("Value objects & enums") and docs/06-module-interface.md.
Keep dependency-free (stdlib only).
"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["ModuleState", "PauseReason", "PrinterStage", "SwapState"]


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
