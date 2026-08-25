"""The configured AMS modules (feeds the add-spool form's module dropdown)."""

from __future__ import annotations

from fastapi import APIRouter

from amsx.apps.module.view import ModuleInfo
from amsx.system.middlewares import BrainDep

router = APIRouter(prefix="/api/modules", tags=["modules"])


@router.get("")
async def list_modules(brain: BrainDep) -> list[ModuleInfo]:
    """All configured AMS modules (for the add-spool form module dropdown)."""
    return [
        ModuleInfo(id=mc.id, cluster_id=mc.cluster_id, filament_index=mc.filament_index)
        for mc in brain.config.modules
    ]
