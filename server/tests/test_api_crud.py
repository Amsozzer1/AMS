"""API tests for spool CRUD + module-list endpoints (Task 2).

Covers:
- GET /api/modules   — returns configured module ids
- POST /api/spools   — creates spool; appears in GET /api/spools; 422 on bad body; 502 on error
- PATCH /api/spools/{id} — updates weight; 404 on unknown id; 502 on store error
- DELETE /api/spools/{id} — removes spool; 404 on unknown id; 502 on store error
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from amsx.api import create_app
from amsx.apps.inventory import FakeSpoolStore
from amsx.config import Config, ModuleConfig, PrinterConfig
from amsx.types import Spool, SpoolSpec

# ---- helpers (same pattern as test_api_inventory.py) ------------------------------------


def _brain_with_store(spools: list[Spool] | None = None):
    """Build a simulate Brain with an injected FakeSpoolStore and known printer/module ids."""
    config = Config(
        printers=[
            PrinterConfig(id="x1c-1", model="x1", serial="SIM123", access_code="x", ip="1.2.3.4")
        ],
        modules=[
            ModuleConfig(id="m1", cluster_id="c", filament_index=0),
            ModuleConfig(id="m2", cluster_id="c", filament_index=1),
        ],
    )
    from amsx.brain import Brain

    brain = Brain(config, simulate=True)
    brain.store = FakeSpoolStore(spools or [])
    return brain


def _client(spools: list[Spool] | None = None):
    brain = _brain_with_store(spools)
    app = create_app(brain)
    return TestClient(app)


_SPOOL = Spool(
    id="1",
    filament_id="10",
    material="PLA",
    color_hex="FFFFFF",
    name="White",
    remaining_g=900.0,
    module="m1",
)


# ---- GET /api/modules -------------------------------------------------------------------


def test_get_modules_returns_configured_ids():
    with _client() as c:
        r = c.get("/api/modules")
        assert r.status_code == 200
        ids = {m["id"] for m in r.json()}
        assert ids == {"m1", "m2"}


def test_get_modules_fields():
    with _client() as c:
        modules = {m["id"]: m for m in c.get("/api/modules").json()}
        m1 = modules["m1"]
        assert m1["cluster_id"] == "c"
        assert m1["filament_index"] == 0
        m2 = modules["m2"]
        assert m2["filament_index"] == 1


# ---- POST /api/spools -------------------------------------------------------------------
# Note: vendor/location round-trip coverage lives in tests/test_inventory_crud.py — the
# FakeSpoolStore intentionally drops them (Spool has no such fields), so that boundary is
# tested there, not here.


def test_post_spool_creates_and_returns_spool():
    with _client() as c:
        r = c.post(
            "/api/spools",
            json={"material": "PETG", "color_hex": "00FF00", "initial_g": 500.0},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["material"] == "PETG"
        assert body["color_hex"] == "00FF00"
        assert body["remaining_g"] == 500.0
        assert "id" in body


def test_post_spool_appears_in_list():
    with _client() as c:
        c.post("/api/spools", json={"material": "ABS"})
        spools = c.get("/api/spools").json()
        assert any(s["material"] == "ABS" for s in spools)


def test_post_spool_missing_material_422():
    with _client() as c:
        r = c.post("/api/spools", json={"color_hex": "FF0000"})
        assert r.status_code == 422


def test_post_spool_bad_body_422():
    with _client() as c:
        r = c.post("/api/spools", content=b"not-json", headers={"Content-Type": "application/json"})
        assert r.status_code == 422


def test_post_spool_optional_fields_default():
    """POST with only material — name/vendor/module/location default to None."""
    with _client() as c:
        r = c.post("/api/spools", json={"material": "TPU"})
        assert r.status_code == 200
        body = r.json()
        assert body["material"] == "TPU"
        assert body["color_hex"] is None
        assert body["name"] is None
        assert body["module"] is None


def test_post_spool_502_on_store_error():
    """A store whose create_spool raises a non-KeyError maps to HTTP 502."""
    brain = _brain_with_store()

    class _BrokenStore(FakeSpoolStore):
        async def create_spool(self, spec: SpoolSpec) -> Spool:
            raise RuntimeError("spoolman down")

    brain.store = _BrokenStore()
    app = create_app(brain)
    with TestClient(app) as c:
        r = c.post("/api/spools", json={"material": "PLA"})
        assert r.status_code == 502
        assert "spoolman down" in r.json()["detail"]


# ---- PATCH /api/spools/{spool_id} -------------------------------------------------------


def test_patch_spool_updates_remaining_g():
    with _client([_SPOOL]) as c:
        r = c.patch("/api/spools/1", json={"remaining_g": 500.0})
        assert r.status_code == 200
        assert r.json()["remaining_g"] == 500.0


def test_patch_spool_updates_archived():
    with _client([_SPOOL]) as c:
        r = c.patch("/api/spools/1", json={"archived": True})
        assert r.status_code == 200
        assert r.json()["archived"] is True


def test_patch_spool_unknown_id_404():
    with _client() as c:
        r = c.patch("/api/spools/999", json={"remaining_g": 100.0})
        assert r.status_code == 404


def test_patch_spool_502_on_store_error():
    brain = _brain_with_store([_SPOOL])

    class _BrokenStore(FakeSpoolStore):
        async def update_spool(self, spool_id, **kwargs):
            raise RuntimeError("db exploded")

    brain.store = _BrokenStore([_SPOOL])
    app = create_app(brain)
    with TestClient(app) as c:
        r = c.patch("/api/spools/1", json={"remaining_g": 100.0})
        assert r.status_code == 502
        assert "db exploded" in r.json()["detail"]


# ---- DELETE /api/spools/{spool_id} -------------------------------------------------------


def test_delete_spool_removes_it():
    with _client([_SPOOL]) as c:
        r = c.delete("/api/spools/1")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["id"] == "1"
        # Verify it's gone
        spools = c.get("/api/spools").json()
        assert not any(s["id"] == "1" for s in spools)


def test_delete_spool_unknown_id_404():
    with _client() as c:
        r = c.delete("/api/spools/999")
        assert r.status_code == 404


def test_delete_spool_502_on_store_error():
    brain = _brain_with_store([_SPOOL])

    class _BrokenStore(FakeSpoolStore):
        async def delete_spool(self, spool_id):
            raise RuntimeError("storage failure")

    brain.store = _BrokenStore([_SPOOL])
    app = create_app(brain)
    with TestClient(app) as c:
        r = c.delete("/api/spools/1")
        assert r.status_code == 502
        assert "storage failure" in r.json()["detail"]
