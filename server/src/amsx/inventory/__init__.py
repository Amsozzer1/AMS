"""inventory — spool catalog behind a SpoolStore seam (SpoolmanStore real, FakeSpoolStore tests).

The Brain depends ONLY on `SpoolStore`. Spoolman is a SOFT dependency: a real store that can't
reach Spoolman returns empty/None and logs, never raising into the swap path.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Protocol, runtime_checkable

from ..types import ModuleId, Spool

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


class FakeSpoolStore:
    """In-memory SpoolStore for tests and the simulate path."""

    def __init__(self, spools: list[Spool] | None = None) -> None:
        self._by_id: dict[str, Spool] = {s.id: s for s in (spools or [])}

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
