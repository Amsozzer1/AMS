"""middlewares — the per-request dependencies every route can ask for by name.

FastAPI's `Depends` is the equivalent of an Express middleware that hangs a service off `req`,
with two differences: it is declared in the handler's signature rather than in the route chain,
and it is typed, so the handler says exactly what it needs.

    async def health(brain: BrainDep) -> Health: ...

Before this existed, every route was a closure over a `_brain()` local inside `create_app`,
which is what physically kept all 20 handlers in one 445-line file — a closure cannot be moved
to another module. `BrainDep` is what let them split.

The guards below (`SimOnlyDep`, `armed_orchestrator`) are the same idea for preconditions: they
raise the right HTTP error before the handler body runs, so a handler never re-checks what its
signature already promised.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from amsx.apps.orchestration import Orchestrator
from amsx.errors import ConflictError, NotFoundError
from amsx.system.brain import Brain

__all__ = ["BrainDep", "SimOnlyDep", "armed_orchestrator", "get_brain", "require_printer"]


def get_brain(request: Request) -> Brain:
    """The running Brain, stashed on app.state by the lifespan."""
    return request.app.state.brain


BrainDep = Annotated[Brain, Depends(get_brain)]


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
