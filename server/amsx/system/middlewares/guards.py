"""Preconditions a route can declare instead of re-checking in its body.

Each raises the right HTTP error before the handler runs, so a handler never re-verifies what
its signature already promised.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from amsx.apps.orchestration import Orchestrator
from amsx.errors import ConflictError, NotFoundError
from amsx.system.brain import Brain
from amsx.system.middlewares.context import BrainDep

__all__ = ["SimOnlyDep", "armed_orchestrator", "require_printer", "require_sim"]


def require_sim(brain: BrainDep) -> Brain:
    """Reject a simulate-only route when running against real hardware.

    The sim routers are only mounted in simulate mode, so this is belt-and-braces: it also
    guards a Brain that was constructed with simulate=False behind a mounted router.
    """
    if not brain.simulate:
        raise ConflictError("sim hooks are only available in simulate mode")
    return brain


SimOnlyDep = Annotated[Brain, Depends(require_sim)]


def require_printer(brain: Brain, printer_id: str) -> None:
    """404 unless this printer is configured. Called by handlers that take a printer_id."""
    if printer_id not in brain.printers:
        raise NotFoundError(f"unknown printer {printer_id!r}")


def armed_orchestrator(brain: Brain, printer_id: str) -> Orchestrator:
    """The orchestrator for a printer that already has a job armed, or the right HTTP error."""
    require_printer(brain, printer_id)
    orch = brain.orchestrators.get(printer_id)
    if orch is None:
        raise ConflictError(f"no job armed for {printer_id!r} — POST a 3MF to /job first")
    return orch
