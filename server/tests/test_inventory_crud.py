# server/tests/test_inventory_crud.py
"""Tests for SpoolStore.create_spool / update_spool / delete_spool (Task 1)."""

from __future__ import annotations

import json

import httpx
import pytest

from amsx.config import SpoolmanConfig
from amsx.inventory import FakeSpoolStore, SpoolStore
from amsx.inventory.spoolman import SpoolmanStore
from amsx.types import Spool, SpoolSpec

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FILAMENT_RED = {
    "id": 7,
    "material": "PLA",
    "color_hex": "FF0000",
    "name": "Red",
    "vendor": {"id": 3, "name": "Bambu"},
}

SPOOL_RED = {
    "id": 42,
    "archived": False,
    "remaining_weight": 1000.0,
    "filament": FILAMENT_RED,
    "extra": {"ams_module": json.dumps("")},
}

SPOOL_RED_UPDATED = {
    **SPOOL_RED,
    "remaining_weight": 750.0,
    "extra": {"ams_module": json.dumps("")},
}


def _store(handler) -> SpoolmanStore:
    s = SpoolmanStore(SpoolmanConfig(base_url="http://x/api/v1"))
    s._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://x/api/v1"
    )
    return s


# ---------------------------------------------------------------------------
# FakeSpoolStore tests
# ---------------------------------------------------------------------------


async def test_fake_create_returns_spool_with_spec_fields():
    store = FakeSpoolStore()
    spec = SpoolSpec(material="PLA", color_hex="ff0000", name="Red", initial_g=500.0)
    spool = await store.create_spool(spec)

    assert spool.material == "PLA"
    assert spool.color_hex == "FF0000"  # uppercased
    assert spool.name == "Red"
    assert spool.remaining_g == 500.0
    assert spool.archived is False
    assert spool.id  # non-empty fresh id


async def test_fake_create_appears_in_list_spools():
    store = FakeSpoolStore()
    spec = SpoolSpec(material="PETG", color_hex="00FF00", name="Green")
    spool = await store.create_spool(spec)

    spools = await store.list_spools()
    assert any(s.id == spool.id for s in spools)


async def test_fake_create_no_color_hex():
    store = FakeSpoolStore()
    spec = SpoolSpec(material="ABS")
    spool = await store.create_spool(spec)
    assert spool.color_hex is None


async def test_fake_create_module_assigned():
    store = FakeSpoolStore()
    spec = SpoolSpec(material="PLA", module="m1")
    spool = await store.create_spool(spec)
    assert spool.module == "m1"


async def test_fake_update_changes_only_named_fields():
    store = FakeSpoolStore([Spool(id="1", filament_id="10", material="PLA", remaining_g=800.0)])
    updated = await store.update_spool("1", remaining_g=600.0)
    assert updated.remaining_g == 600.0
    assert updated.material == "PLA"  # unchanged


async def test_fake_update_location_only():
    store = FakeSpoolStore([Spool(id="1", filament_id="10", material="PLA", remaining_g=800.0)])
    updated = await store.update_spool("1", location="shelf-A")
    assert updated.remaining_g == 800.0  # unchanged


async def test_fake_update_archived():
    store = FakeSpoolStore([Spool(id="1", filament_id="10", material="PLA")])
    updated = await store.update_spool("1", archived=True)
    assert updated.archived is True


async def test_fake_update_raises_keyerror_for_missing():
    store = FakeSpoolStore()
    with pytest.raises(KeyError):
        await store.update_spool("nonexistent", remaining_g=100.0)


async def test_fake_delete_removes_spool():
    store = FakeSpoolStore([Spool(id="1", filament_id="10", material="PLA")])
    await store.delete_spool("1")
    assert await store.get_spool("1") is None


async def test_fake_delete_raises_keyerror_for_missing():
    store = FakeSpoolStore()
    with pytest.raises(KeyError):
        await store.delete_spool("ghost")


async def test_fake_is_still_a_spoolstore():
    """Protocol check still passes after adding new methods."""
    assert isinstance(FakeSpoolStore(), SpoolStore)


async def test_fake_id_counter_does_not_collide_with_seeded_ids():
    """Generated ids must be different from pre-seeded ids."""
    existing = [Spool(id="1", filament_id="10", material="PLA")]
    store = FakeSpoolStore(existing)
    s = await store.create_spool(SpoolSpec(material="ABS"))
    assert s.id != "1"


# ---------------------------------------------------------------------------
# SpoolmanStore tests — create with new vendor + filament
# ---------------------------------------------------------------------------


async def test_spoolman_create_new_vendor_and_filament():
    """POST /vendor → POST /filament → POST /spool; returns decoded Spool."""
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append((req.method, req.url.path))
        if req.method == "GET" and req.url.path.endswith("/vendor"):
            return httpx.Response(200, json=[])
        if req.method == "POST" and req.url.path.endswith("/vendor"):
            body = json.loads(req.content)
            assert body["name"] == "Bambu"
            return httpx.Response(200, json={"id": 3, "name": "Bambu"})
        if req.method == "GET" and req.url.path.endswith("/filament"):
            return httpx.Response(200, json=[])
        if req.method == "POST" and req.url.path.endswith("/filament"):
            body = json.loads(req.content)
            assert body["material"] == "PLA"
            assert body["vendor_id"] == 3
            assert body["color_hex"] == "FF0000"
            assert body["density"] == 1.24
            assert body["diameter"] == 1.75
            return httpx.Response(200, json={"id": 7, **FILAMENT_RED})
        if req.method == "POST" and req.url.path.endswith("/spool"):
            body = json.loads(req.content)
            assert body["filament_id"] == 7
            assert body["initial_weight"] == 1000.0
            assert body["remaining_weight"] == 1000.0
            return httpx.Response(200, json=SPOOL_RED)
        raise AssertionError(f"Unexpected request: {req.method} {req.url.path}")

    spec = SpoolSpec(material="PLA", color_hex="FF0000", name="Red", vendor="Bambu")
    spool = await _store(handler).create_spool(spec)

    # Verify call sequence
    assert ("GET", "/api/v1/vendor") in calls
    assert ("POST", "/api/v1/vendor") in calls
    assert ("GET", "/api/v1/filament") in calls
    assert ("POST", "/api/v1/filament") in calls
    assert ("POST", "/api/v1/spool") in calls

    assert spool.id == "42"
    assert spool.material == "PLA"
    assert spool.color_hex == "FF0000"


async def test_spoolman_create_reuses_existing_filament():
    """When an exact-matching filament exists, skip POST /filament."""
    # No vendor → vendor_id is None; filament has vendor {"id":3} which wouldn't match None,
    # so use a filament with no vendor for the reuse path.
    filament_no_vendor = {**FILAMENT_RED, "vendor": None}
    spool_no_vendor = {**SPOOL_RED, "filament": filament_no_vendor}
    calls: list = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append((req.method, req.url.path))
        if req.method == "GET" and req.url.path.endswith("/filament"):
            return httpx.Response(200, json=[filament_no_vendor])
        if req.method == "POST" and req.url.path.endswith("/spool"):
            body = json.loads(req.content)
            assert body["filament_id"] == 7
            return httpx.Response(200, json=spool_no_vendor)
        raise AssertionError(f"Unexpected: {req.method} {req.url.path}")

    spec = SpoolSpec(material="PLA", color_hex="FF0000", name="Red")
    spool = await _store(handler).create_spool(spec)

    assert ("POST", "/api/v1/filament") not in calls
    assert spool.id == "42"


async def test_spoolman_create_reuses_filament_with_matching_vendor():
    """Reuse filament when vendor_id matches existing filament.vendor.id."""
    calls: list = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append((req.method, req.url.path))
        if req.method == "GET" and req.url.path.endswith("/vendor"):
            return httpx.Response(200, json=[{"id": 3, "name": "Bambu"}])
        if req.method == "GET" and req.url.path.endswith("/filament"):
            return httpx.Response(200, json=[FILAMENT_RED])  # vendor.id==3 matches
        if req.method == "POST" and req.url.path.endswith("/spool"):
            return httpx.Response(200, json=SPOOL_RED)
        raise AssertionError(f"Unexpected: {req.method} {req.url.path}")

    spec = SpoolSpec(material="PLA", color_hex="FF0000", name="Red", vendor="bambu")
    spool = await _store(handler).create_spool(spec)

    assert ("POST", "/api/v1/vendor") not in calls
    assert ("POST", "/api/v1/filament") not in calls
    assert spool.id == "42"


# ---------------------------------------------------------------------------
# SpoolmanStore tests — update
# ---------------------------------------------------------------------------


async def test_spoolman_update_sends_only_changed_keys():
    """PATCH body contains only the non-None kwargs."""
    seen: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "PATCH" and "/spool/42" in req.url.path:
            seen["body"] = json.loads(req.content)
            return httpx.Response(200, json=SPOOL_RED_UPDATED)
        raise AssertionError(f"Unexpected: {req.method} {req.url}")

    spool = await _store(handler).update_spool("42", remaining_g=750.0)
    assert seen["body"] == {"remaining_weight": 750.0}
    assert spool.remaining_g == 750.0


async def test_spoolman_update_location_and_archived():
    """Multiple fields can be updated together."""
    seen: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "PATCH":
            seen["body"] = json.loads(req.content)
            return httpx.Response(200, json={**SPOOL_RED, "archived": True})
        raise AssertionError(f"Unexpected: {req.method} {req.url}")

    await _store(handler).update_spool("42", location="shelf-B", archived=True)
    assert seen["body"] == {"location": "shelf-B", "archived": True}


async def test_spoolman_update_404_raises_keyerror():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "Not Found"})

    with pytest.raises(KeyError):
        await _store(handler).update_spool("999", remaining_g=0.0)


# ---------------------------------------------------------------------------
# SpoolmanStore tests — delete
# ---------------------------------------------------------------------------


async def test_spoolman_delete_sends_delete_request():
    calls: list = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append((req.method, req.url.path))
        if req.method == "DELETE" and "/spool/42" in req.url.path:
            return httpx.Response(200, json={})
        raise AssertionError(f"Unexpected: {req.method} {req.url}")

    result = await _store(handler).delete_spool("42")
    assert result is None
    assert any("DELETE" == m for m, _ in calls)


async def test_spoolman_delete_404_raises_keyerror():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "Not Found"})

    with pytest.raises(KeyError):
        await _store(handler).delete_spool("nonexistent")
