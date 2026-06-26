"""Resolver — best-effort pre-fill of index→module from the loaded inventory. NOT authoritative;
the operator confirms/overrides the mapping. No auto-assignment guarantees, no delta-sync."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..types import FilamentColor, ModuleId, SwapPlan
from . import SpoolStore


@dataclass(frozen=True)
class ProposedRow:
    index: int
    material: str | None
    color_hex: str | None
    grams: float | None
    module: ModuleId | None
    spool_id: str | None
    status: Literal["loaded", "gap"]


class Resolver:
    def __init__(self, store: SpoolStore) -> None:
        self._store = store

    async def propose(self, plan: SwapPlan) -> dict[int, ProposedRow]:
        rows: dict[int, ProposedRow] = {}
        colors = list(plan.colors) or [
            FilamentColor(s.filament_index, s.material, s.color_hex, None) for s in plan.swaps
        ]
        for fc in colors:
            matches = await self._store.match(fc.material, fc.color_hex)
            loaded = next((s for s in matches if s.module is not None), None)
            rows[fc.index] = ProposedRow(
                index=fc.index,
                material=fc.material,
                color_hex=fc.color_hex,
                grams=fc.grams,
                module=loaded.module if loaded else None,
                spool_id=loaded.id if loaded else None,
                status="loaded" if loaded else "gap",
            )
        return rows
