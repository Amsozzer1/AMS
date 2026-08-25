"""Domain errors — raised by the swap path and the parsers.

Each of these used to live in whichever module happened to raise it (`orchestration`, `job`,
`module`), which made "what can go wrong here?" impossible to answer without reading all three.
"""

from __future__ import annotations

from amsx.errors.base import AmsxError

__all__ = ["ClusterBusyError", "JobParseError", "PauseValidationError", "SwapFault"]


class PauseValidationError(AmsxError):
    """A live pause did not match the plan — never a swap, never a guess (docs/02).

    Carries the offending event so the caller can log/alert with the full context rather than
    just a message.
    """

    def __init__(self, message: str, event: object) -> None:
        super().__init__(message)
        self.event = event


class SwapFault(AmsxError):
    """A swap could not complete. Drives the state machine into FAULT + safe-hold."""


class JobParseError(AmsxError):
    """The sliced 3MF could not be parsed into a SwapPlan."""


class ClusterBusyError(AmsxError, RuntimeError):
    """Another module in this cluster is already moving (one motor at a time, docs/08).

    Also a ``RuntimeError`` so existing ``except RuntimeError`` callers keep working.
    """
