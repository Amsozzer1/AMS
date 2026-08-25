"""The armed swap loop's status for one printer."""

from __future__ import annotations

from fastapi import APIRouter

from amsx.apps.orchestration.view import OrchestratorArmed, OrchestratorIdle, OrchestratorStatus
from amsx.system.middlewares import BrainDep, require_printer

router = APIRouter(prefix="/api/printers", tags=["orchestrator"])


@router.get("/{printer_id}/orchestrator")
async def get_orchestrator(brain: BrainDep, printer_id: str) -> OrchestratorStatus:
    """The armed swap loop for this printer (cursor / held / swap_state / alerts).

    404 if the printer is unknown; ``{"armed": false}`` if no job has been submitted yet.
    """
    require_printer(brain, printer_id)
    orch = brain.orchestrators.get(printer_id)
    if orch is None:
        return OrchestratorIdle(printer_id=printer_id)
    return OrchestratorArmed.from_orchestrator(orch)
