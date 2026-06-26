"""SpoolmanStore — SpoolStore over a (user-run, external) Spoolman REST instance.

SOFT by contract: every call wraps HTTP and on ANY error logs + returns empty/None so the swap
path never breaks because the inventory service is down. Spool `extra` values are JSON-encoded
strings on the wire (we json.loads/json.dumps the `ams_module` key).
"""

from __future__ import annotations

import json
import logging

import httpx

from ..config import SpoolmanConfig
from ..types import ModuleId, Spool

log = logging.getLogger("amsx.inventory")
MODULE_FIELD = "ams_module"


class SpoolmanStore:
    def __init__(self, cfg: SpoolmanConfig) -> None:
        self._cfg = cfg
        self._client = httpx.AsyncClient(base_url=cfg.base_url, timeout=cfg.timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    def _spool(self, j: dict) -> Spool:
        fil = j.get("filament") or {}
        extra = j.get("extra") or {}
        module = None
        raw = extra.get(MODULE_FIELD)
        if isinstance(raw, str) and raw:
            try:
                module = json.loads(raw) or None
            except ValueError:
                module = raw or None
        color = fil.get("color_hex")
        return Spool(
            id=str(j["id"]),
            filament_id=str(fil.get("id", "")),
            material=fil.get("material"),
            color_hex=color.upper() if isinstance(color, str) else None,
            name=fil.get("name"),
            remaining_g=j.get("remaining_weight"),
            module=module,
            archived=bool(j.get("archived")),
        )

    async def list_spools(self, *, include_archived: bool = False) -> list[Spool]:
        params: dict[str, object] = {"allow_archived": str(include_archived).lower()}
        if self._cfg.active_location:
            params["location"] = self._cfg.active_location
        try:
            r = await self._client.get("/spool", params=params)
            r.raise_for_status()
            return [self._spool(j) for j in r.json()]
        except Exception:  # SOFT
            log.warning("Spoolman list_spools failed (soft)", exc_info=True)
            return []

    async def get_spool(self, spool_id: str) -> Spool | None:
        try:
            r = await self._client.get(f"/spool/{spool_id}")
            r.raise_for_status()
            return self._spool(r.json())
        except Exception:
            log.warning("Spoolman get_spool failed (soft)", exc_info=True)
            return None

    async def loaded_in(self, module_id: ModuleId) -> Spool | None:
        return next((s for s in await self.list_spools() if s.module == module_id), None)

    async def set_module(self, spool_id: str, module_id: ModuleId | None) -> None:
        body = {"extra": {MODULE_FIELD: json.dumps(module_id or "")}}
        try:
            r = await self._client.patch(f"/spool/{spool_id}", json=body)
            r.raise_for_status()
        except Exception:
            log.warning("Spoolman set_module failed (soft)", exc_info=True)

    async def match(self, material: str | None, color_hex: str | None) -> list[Spool]:
        # Spoolman matches colour perceptually via color_similarity_threshold; we then keep only
        # spools of those filaments. SOFT.
        params: dict[str, object] = {}
        if material:
            params["material"] = material
        if color_hex:
            params["color_hex"] = color_hex
            params["color_similarity_threshold"] = 20
        try:
            r = await self._client.get("/filament", params=params)
            r.raise_for_status()
            ids = {str(f["id"]) for f in r.json()}
        except Exception:
            log.warning("Spoolman match failed (soft)", exc_info=True)
            return []
        return [s for s in await self.list_spools() if s.filament_id in ids]

    async def consume(self, spool_id: str, grams: float) -> None:
        try:
            r = await self._client.put(f"/spool/{spool_id}/use", json={"use_weight": grams})
            r.raise_for_status()
        except Exception:
            log.warning("Spoolman consume failed (soft)", exc_info=True)

    async def ensure_module_field(self) -> None:
        try:
            r = await self._client.get("/field/spool")
            r.raise_for_status()
            if any(f.get("key") == MODULE_FIELD for f in r.json()):
                return
            post_r = await self._client.post(
                f"/field/spool/{MODULE_FIELD}",
                json={"name": "AMS Module", "field_type": "text"},
            )
            post_r.raise_for_status()
        except Exception:
            log.warning("Spoolman ensure_module_field failed (soft)", exc_info=True)
