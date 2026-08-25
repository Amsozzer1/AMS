"""Liveness + what the Brain came up with."""

from __future__ import annotations

from fastapi import APIRouter

from amsx.system.infra.http.view import Health
from amsx.system.middlewares import BrainDep

router = APIRouter()


@router.get("/health", tags=["health"])
async def health(brain: BrainDep) -> Health:
    return Health(
        ok=True,
        simulate=brain.simulate,
        printers=list(brain.printers),
        modules=len(brain._module_by_id),
    )
