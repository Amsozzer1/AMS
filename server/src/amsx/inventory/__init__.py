"""inventory — spool catalog behind a SpoolStore seam (SpoolmanStore real, FakeSpoolStore tests).

The Brain depends ONLY on `SpoolStore`. Spoolman is a SOFT dependency: a real store that can't
reach Spoolman returns empty/None and logs, never raising into the swap path.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Protocol, runtime_checkable

from ..types import ModuleId, Spool, SpoolSpec

__all__ = ["FakeSpoolStore", "SpoolStore"]


@runtime_checkable
class SpoolStore(Protocol):
    async def list_spools(self, *, include_archived: bool = False) -> list[Spool]: ...
    async def get_spool(self, spool_id: str) -> Spool | None: ...
    async def loaded_in(self, module_id: ModuleId) -> Spool | None: ...
    async def set_module(self, spool_id: str, module_id: ModuleId | None) -> None: ...
    async def match(self, material: str | None, color_hex: str | None) -> list[Spool]: ...
    async def consume(self, spool_id: str, grams: float) -> None: ...
    async def ensure_module_field(self) -> None: ...
    async def create_spool(self, spec: SpoolSpec) -> Spool: ...
    async def update_spool(
        self,
        spool_id: str,
        *,
        remaining_g: float | None = None,
        location: str | None = None,
        archived: bool | None = None,
    ) -> Spool: ...
    async def delete_spool(self, spool_id: str) -> None: ...


class FakeSpoolStore:
    """In-memory SpoolStore for tests and the simulate path."""

    def __init__(self, spools: list[Spool] | None = None) -> None:
        self._by_id: dict[str, Spool] = {s.id: s for s in (spools or [])}
        # Start id counter past any seeded numeric ids to avoid collisions.
        numeric_ids = [int(s.id) for s in (spools or []) if s.id.isdigit()]
        self._next: int = max(numeric_ids, default=0) + 1

    async def list_spools(self, *, include_archived: bool = False) -> list[Spool]:
        return [s for s in self._by_id.values() if include_archived or not s.archived]

    async def get_spool(self, spool_id: str) -> Spool | None:
        return self._by_id.get(spool_id)

    async def loaded_in(self, module_id: ModuleId) -> Spool | None:
        return next((s for s in self._by_id.values() if s.module == module_id), None)

    async def set_module(self, spool_id: str, module_id: ModuleId | None) -> None:
        s = self._by_id.get(spool_id)
        if s is not None:
            self._by_id[spool_id] = replace(s, module=module_id)

    async def match(self, material: str | None, color_hex: str | None) -> list[Spool]:
        out = []
        for s in self._by_id.values():
            if material and s.material != material:
                continue
            if color_hex and (s.color_hex or "").upper() != color_hex.upper():
                continue
            out.append(s)
        return out

    async def consume(self, spool_id: str, grams: float) -> None:
        s = self._by_id.get(spool_id)
        if s is not None and s.remaining_g is not None:
            self._by_id[spool_id] = replace(s, remaining_g=max(s.remaining_g - grams, 0.0))

    async def ensure_module_field(self) -> None:
        return None

    async def create_spool(self, spec: SpoolSpec) -> Spool:
        # spec.vendor and spec.location are intentionally NOT modeled here: Spool has no
        # vendor/location field, so the Fake store drops them. The real SpoolmanStore
        # forwards them to Spoolman. This is the coverage boundary, not a missing field.
        new_id = str(self._next)
        self._next += 1
        spool = Spool(
            id=new_id,
            filament_id=str(self._next),
            material=spec.material,
            color_hex=spec.color_hex.upper() if spec.color_hex else None,
            name=spec.name,
            remaining_g=spec.initial_g,
            module=spec.module,
            archived=False,
        )
        self._next += 1
        self._by_id[new_id] = spool
        return spool

    async def update_spool(
        self,
        spool_id: str,
        *,
        remaining_g: float | None = None,
        # location is intentionally NOT modeled: Spool has no location field, so the Fake
        # store accepts the argument (matching the SpoolStore Protocol) but drops it. The
        # real SpoolmanStore forwards it. This is the coverage boundary, not a missing field.
        location: str | None = None,
        archived: bool | None = None,
    ) -> Spool:
        s = self._by_id.get(spool_id)
        if s is None:
            raise KeyError(spool_id)
        kwargs: dict[str, object] = {}
        if remaining_g is not None:
            kwargs["remaining_g"] = remaining_g
        if archived is not None:
            kwargs["archived"] = archived
        updated = replace(s, **kwargs)
        self._by_id[spool_id] = updated
        return updated

    async def delete_spool(self, spool_id: str) -> None:
        if spool_id not in self._by_id:
            raise KeyError(spool_id)
        del self._by_id[spool_id]
