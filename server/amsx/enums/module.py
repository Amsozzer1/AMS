"""Module state machine (docs/06-module-interface.md)."""

from __future__ import annotations

from enum import StrEnum

__all__ = ["ModuleState"]


class ModuleState(StrEnum):
    """Module state machine (docs/06-module-interface.md)."""

    IDLE = "IDLE"
    FEEDING = "FEEDING"
    RETRACTING = "RETRACTING"
    FAULT = "FAULT"
    EMPTY = "EMPTY"
