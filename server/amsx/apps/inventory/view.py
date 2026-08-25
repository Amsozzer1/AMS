"""inventory — the wire shapes for spool CRUD, the loadout, and the assignment proposal."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from amsx.apps.inventory.resolver import ProposedRow
from amsx.types import Spool as DomainSpool

__all__ = ["AssignRow", "AssignmentResponse", "LoadoutRow", "Spool", "SpoolCreate", "SpoolUpdate"]


class SpoolCreate(BaseModel):
    """Request body for POST /api/spools."""

    material: str
    color_hex: str | None = None
    name: str | None = None
    vendor: str | None = None
    initial_g: float = 1000.0
    module: str | None = None
    location: str | None = None


class SpoolUpdate(BaseModel):
    """Request body for PATCH /api/spools/{spool_id}."""

    remaining_g: float | None = None
    location: str | None = None
    archived: bool | None = None


class Spool(BaseModel):
    """One physical spool from the inventory. ``color_hex`` is bare 6-hex RRGGBB (no '#')."""

    id: str
    filament_id: str
    material: str | None
    color_hex: str | None
    name: str | None
    remaining_g: float | None
    module: str | None
    archived: bool

    @classmethod
    def from_domain(cls, s: DomainSpool) -> Spool:
        return cls(
            id=s.id,
            filament_id=s.filament_id,
            material=s.material,
            color_hex=s.color_hex,
            name=s.name,
            remaining_g=s.remaining_g,
            module=s.module,
            archived=s.archived,
        )


class LoadoutRow(BaseModel):
    """One configured module and the spool currently loaded in it (null when empty)."""

    module: str
    spool: Spool | None


class AssignRow(BaseModel):
    """One filament index from the armed plan with the module/spool the resolver proposed."""

    index: int
    material: str | None
    color_hex: str | None
    grams: float | None
    module: str | None
    spool_id: str | None
    status: Literal["loaded", "gap"]

    @classmethod
    def from_proposed(cls, row: ProposedRow) -> AssignRow:
        return cls(
            index=row.index,
            material=row.material,
            color_hex=row.color_hex,
            grams=row.grams,
            module=row.module,
            spool_id=row.spool_id,
            status=row.status,
        )


class AssignmentResponse(BaseModel):
    """GET /api/printers/{id}/job/assignment. ``rows`` is empty when nothing is armed."""

    rows: list[AssignRow]
    confirmed: bool
