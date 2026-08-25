"""Which spool is loaded in which module, per printer."""

from __future__ import annotations

from fastapi import APIRouter

from amsx.apps.inventory.view import LoadoutRow, Spool
from amsx.system.infra.http.view import OkResponse
from amsx.system.middlewares import BrainDep, require_printer

router = APIRouter(prefix="/api/printers", tags=["loadout"])


@router.get("/{printer_id}/loadout")
async def get_loadout(brain: BrainDep, printer_id: str) -> list[LoadoutRow]:
    """Current spool→module mapping for every configured module on this printer."""
    require_printer(brain, printer_id)
    rows = []
    for mc in brain.config.modules:
        spool = await brain.store.loaded_in(mc.id)
        rows.append(LoadoutRow(module=mc.id, spool=Spool.from_domain(spool) if spool else None))
    return rows


@router.put("/{printer_id}/loadout")
async def set_loadout(brain: BrainDep, printer_id: str, module: str, spool_id: str) -> OkResponse:
    """Assign a spool to a module (writes `set_module` on the store)."""
    require_printer(brain, printer_id)
    await brain.store.set_module(spool_id, module)
    return OkResponse(ok=True)
