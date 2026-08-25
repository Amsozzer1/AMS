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
from ..types import ModuleId, Spool, SpoolSpec

log = logging.getLogger("amsx.inventory")
MODULE_FIELD = "ams_module"

# Filament density defaults by material (g/cm³), diameter always 1.75 mm.
_DENSITY: dict[str, float] = {
    "PLA": 1.24,
    "PETG": 1.27,
    "ABS": 1.04,
    "ASA": 1.07,
    "TPU": 1.21,
    "PC": 1.20,
    "PA": 1.14,
    "NYLON": 1.14,
    "PVA": 1.23,
    "HIPS": 1.04,
}
_DIAMETER = 1.75


def _strip_hash(hex_value: str | None) -> str | None:
    """Return None for falsy values, else strip any leading '#'."""
    if not hex_value:
        return None
    return hex_value.lstrip("#")


def _soft(op: str, exc: Exception) -> None:
    """Log a SOFT Spoolman failure concisely — one WARNING line, no stack-spam per poll.

    Spoolman being down/flaky/disconnecting is an EXPECTED, handled condition (the inventory is
    optional), so a full traceback on every poll is noise. The traceback goes to DEBUG for when
    it's actually wanted.
    """
    log.warning("Spoolman %s failed (soft): %s: %s", op, type(exc).__name__, exc)
    log.debug("Spoolman %s traceback:", op, exc_info=exc)


class SpoolmanStore:
    def __init__(self, cfg: SpoolmanConfig) -> None:
        self._cfg = cfg
        # Disable keep-alive connection REUSE. Spoolman (or anything between us) closes idle
        # connections, and reusing a server-closed socket raises RemoteProtocolError ("Server
        # disconnected without sending a response") on the NEXT request. A fresh connection per
        # request sidesteps it; inventory polling is infrequent, so the overhead is negligible.
        self._client = httpx.AsyncClient(
            base_url=cfg.base_url,
            timeout=cfg.timeout,
            limits=httpx.Limits(max_keepalive_connections=0),
        )

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
        except Exception as exc:  # SOFT
            _soft("list_spools", exc)
            return []

    async def get_spool(self, spool_id: str) -> Spool | None:
        try:
            r = await self._client.get(f"/spool/{spool_id}")
            r.raise_for_status()
            return self._spool(r.json())
        except Exception as exc:
            _soft("get_spool", exc)
            return None

    async def loaded_in(self, module_id: ModuleId) -> Spool | None:
        return next((s for s in await self.list_spools() if s.module == module_id), None)

    async def set_module(self, spool_id: str, module_id: ModuleId | None) -> None:
        body = {"extra": {MODULE_FIELD: json.dumps(module_id or "")}}
        try:
            r = await self._client.patch(f"/spool/{spool_id}", json=body)
            r.raise_for_status()
        except Exception as exc:
            _soft("set_module", exc)

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
        except Exception as exc:
            _soft("match", exc)
            return []
        return [s for s in await self.list_spools() if s.filament_id in ids]

    async def consume(self, spool_id: str, grams: float) -> None:
        try:
            r = await self._client.put(f"/spool/{spool_id}/use", json={"use_weight": grams})
            r.raise_for_status()
        except Exception as exc:
            _soft("consume", exc)

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
        except Exception as exc:
            _soft("ensure_module_field", exc)

    async def create_spool(self, spec: SpoolSpec) -> Spool:
        """Create a new spool in Spoolman, creating-or-reusing the filament and vendor records.

        NOT soft — let errors propagate to the caller.
        """
        # 1. Resolve vendor_id
        vendor_id: int | None = None
        if spec.vendor:
            r = await self._client.get("/vendor")
            r.raise_for_status()
            match = next(
                (v for v in r.json() if v["name"].lower() == spec.vendor.lower()),
                None,
            )
            if match:
                vendor_id = match["id"]
            else:
                r = await self._client.post("/vendor", json={"name": spec.vendor})
                r.raise_for_status()
                vendor_id = r.json()["id"]

        # 2. Resolve filament_id
        filament_id: int
        params: dict[str, object] = {}
        if spec.material:
            params["material"] = spec.material
        r = await self._client.get("/filament", params=params)
        r.raise_for_status()
        # Strip '#' on the spec side too (mirroring the POST body + the filament side below) so a
        # caller that passes "#RRGGBB" still matches a stored bare "RRGGBB" instead of duplicating.
        spec_stripped = _strip_hash(spec.color_hex)
        spec_color = spec_stripped.upper() if spec_stripped else None
        existing = next(
            (
                f
                for f in r.json()
                # None→"" on both sides so missing-color == missing-color
                if (_strip_hash(f.get("color_hex")) or "").upper() == (spec_color or "")
                and (f.get("vendor") or {}).get("id") == vendor_id
                and f.get("name") == spec.name
            ),
            None,
        )
        if existing:
            filament_id = existing["id"]
        else:
            body: dict[str, object] = {
                "material": spec.material,
                "density": _DENSITY.get((spec.material or "").upper(), 1.24),
                "diameter": _DIAMETER,
            }
            if spec.name is not None:
                body["name"] = spec.name
            if vendor_id is not None:
                body["vendor_id"] = vendor_id
            stripped = _strip_hash(spec.color_hex)
            if stripped is not None:
                body["color_hex"] = stripped
            r = await self._client.post("/filament", json=body)
            r.raise_for_status()
            filament_id = r.json()["id"]

        # 3. Create the spool
        spool_body: dict[str, object] = {
            "filament_id": filament_id,
            "initial_weight": spec.initial_g,
            "remaining_weight": spec.initial_g,
            "extra": {MODULE_FIELD: json.dumps(spec.module or "")},
        }
        location = spec.location or self._cfg.active_location
        if location is not None:
            spool_body["location"] = location
        r = await self._client.post("/spool", json=spool_body)
        r.raise_for_status()
        return self._spool(r.json())

    async def update_spool(
        self,
        spool_id: str,
        *,
        remaining_g: float | None = None,
        location: str | None = None,
        archived: bool | None = None,
    ) -> Spool:
        """PATCH a spool with only the supplied fields. 404 → KeyError. NOT soft."""
        body: dict[str, object] = {}
        if remaining_g is not None:
            body["remaining_weight"] = remaining_g
        if location is not None:
            body["location"] = location
        if archived is not None:
            body["archived"] = archived
        r = await self._client.patch(f"/spool/{spool_id}", json=body)
        if r.status_code == 404:
            raise KeyError(spool_id)
        r.raise_for_status()
        return self._spool(r.json())

    async def delete_spool(self, spool_id: str) -> None:
        """DELETE a spool, then clean up the filament/vendor AMS created for it.

        The spool delete itself is NOT soft (404 → KeyError; other errors propagate). The orphan
        cleanup that follows IS best-effort: the spool — the thing the operator asked to remove —
        is already gone, so failing to also remove a now-orphaned filament/vendor is logged, not
        raised. Cleanup is orphan-GUARDED: the filament is deleted only when no remaining spool
        (archived included) references it, and its vendor only when no remaining filament does, so
        anything still in use is never touched.
        """
        # Learn the filament/vendor BEFORE deleting so we can orphan-check afterwards.
        g = await self._client.get(f"/spool/{spool_id}")
        if g.status_code == 404:
            raise KeyError(spool_id)
        g.raise_for_status()
        fil = g.json().get("filament") or {}
        filament_id = fil.get("id")
        vendor_id = (fil.get("vendor") or {}).get("id")

        r = await self._client.delete(f"/spool/{spool_id}")
        if r.status_code == 404:
            raise KeyError(spool_id)
        r.raise_for_status()

        try:
            await self._cleanup_orphans(filament_id, vendor_id)
        except Exception as exc:  # cascade is best-effort — the spool is already gone
            _soft("delete_spool orphan cleanup", exc)

    async def _cleanup_orphans(self, filament_id: object, vendor_id: object) -> None:
        """Delete the filament (then its vendor) iff nothing else still references them."""
        if filament_id is None:
            return
        # Any spool (archived included, all locations) still on this filament? Then keep it.
        r = await self._client.get("/spool", params={"allow_archived": "true"})
        r.raise_for_status()
        if any((s.get("filament") or {}).get("id") == filament_id for s in r.json()):
            return
        await self._client.delete(f"/filament/{filament_id}")

        if vendor_id is None:
            return
        # Any remaining filament still on this vendor? Then keep it.
        r = await self._client.get("/filament")
        r.raise_for_status()
        if not any((f.get("vendor") or {}).get("id") == vendor_id for f in r.json()):
            await self._client.delete(f"/vendor/{vendor_id}")
