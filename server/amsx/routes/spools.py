"""Spool inventory CRUD, proxied to whichever SpoolStore is wired in (Spoolman or fake)."""

from __future__ import annotations

import logging

from fastapi import APIRouter

from amsx.apps.inventory.view import Spool, SpoolCreate, SpoolUpdate
from amsx.errors import HTTPError, NotFoundError
from amsx.system.infra.http.view import DeleteResult
from amsx.system.middlewares import BrainDep
from amsx.types import SpoolSpec

log = logging.getLogger("amsx.routes.spools")

router = APIRouter(prefix="/api/spools", tags=["spools"])


class _StoreUnavailable(HTTPError):
    """The inventory store (Spoolman) could not be reached or refused the write."""

    status_code = 502


@router.get("")
async def list_spools(brain: BrainDep, include_archived: bool = False) -> list[Spool]:
    """List all spools from the inventory (Spoolman or fake)."""
    spools = await brain.store.list_spools(include_archived=include_archived)
    return [Spool.from_domain(s) for s in spools]


@router.post("")
async def create_spool(brain: BrainDep, body: SpoolCreate) -> Spool:
    """Create a new spool in the inventory."""
    spec = SpoolSpec(
        material=body.material,
        color_hex=body.color_hex,
        name=body.name,
        vendor=body.vendor,
        initial_g=body.initial_g,
        module=body.module,
        location=body.location,
    )
    try:
        spool = await brain.store.create_spool(spec)
    except Exception as exc:
        log.exception("create_spool FAILED")
        raise _StoreUnavailable(str(exc)) from exc
    return Spool.from_domain(spool)


@router.patch("/{spool_id}")
async def update_spool(brain: BrainDep, spool_id: str, body: SpoolUpdate) -> Spool:
    """Update weight, location, or archived status of a spool."""
    try:
        spool = await brain.store.update_spool(
            spool_id,
            remaining_g=body.remaining_g,
            location=body.location,
            archived=body.archived,
        )
    except KeyError as exc:
        raise NotFoundError(f"unknown spool {spool_id!r}") from exc
    except Exception as exc:
        log.exception("update_spool FAILED for %s", spool_id)
        raise _StoreUnavailable(str(exc)) from exc
    return Spool.from_domain(spool)


@router.delete("/{spool_id}")
async def delete_spool(brain: BrainDep, spool_id: str) -> DeleteResult:
    """Hard-delete a spool from the inventory."""
    try:
        await brain.store.delete_spool(spool_id)
    except KeyError as exc:
        raise NotFoundError(f"unknown spool {spool_id!r}") from exc
    except Exception as exc:
        log.exception("delete_spool FAILED for %s", spool_id)
        raise _StoreUnavailable(str(exc)) from exc
    # Success return is outside the try — the model can't raise, so it doesn't belong
    # under the error guard.
    return DeleteResult(ok=True, id=spool_id)
