"""The orchestrator's per-swap state machine (docs/10-domain-model.md)."""

from __future__ import annotations

from enum import StrEnum

__all__ = ["SwapState"]


class SwapState(StrEnum):
    """Orchestrator's per-swap state machine (docs/10-domain-model.md)."""

    WATCHING = "WATCHING"
    UNLOADING = "UNLOADING"
    SELECTING = "SELECTING"
    FEEDING = "FEEDING"
    SENSING = "SENSING"
    RESUMING = "RESUMING"
    FAULT = "FAULT"
