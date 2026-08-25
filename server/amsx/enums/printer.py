"""Printer-reported state: what the machine says it is doing, and why it paused."""

from __future__ import annotations

from enum import StrEnum

__all__ = ["PauseReason", "PrinterStage"]


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
