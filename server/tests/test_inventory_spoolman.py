# server/tests/test_inventory_spoolman.py
import json

import httpx
import pytest

from amsx.config import SpoolmanConfig
from amsx.libs.spoolman import SpoolmanStore

pytestmark = pytest.mark.asyncio

SPOOL_JSON = {
    "id": 2,
    "archived": False,
    "remaining_weight": 400.0,
    "filament": {"id": 11, "material": "PLA", "color_hex": "FF0000", "name": "Red"},
    "extra": {"ams_module": json.dumps("m2")},
}


def _store(handler) -> SpoolmanStore:
    s = SpoolmanStore(SpoolmanConfig(base_url="http://x/api/v1"))
    s._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://x/api/v1"
    )
    return s


async def test_list_maps_filament_and_module():
    def handler(req):
        assert req.url.path.endswith("/spool")
        return httpx.Response(200, json=[SPOOL_JSON])

    spools = await _store(handler).list_spools()
    assert len(spools) == 1
    s = spools[0]
    assert s.id == "2" and s.material == "PLA" and s.color_hex == "FF0000"
    assert s.module == "m2" and s.remaining_g == 400.0


async def test_set_module_patches_extra_json_encoded():
    seen = {}

    def handler(req):
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={**SPOOL_JSON, "extra": {"ams_module": json.dumps("m3")}})

    await _store(handler).set_module("2", "m3")
    assert seen["body"]["extra"]["ams_module"] == json.dumps("m3")


async def test_errors_are_soft():
    def handler(req):
        raise httpx.ConnectError("down")

    assert await _store(handler).list_spools() == []  # no raise
    assert await _store(handler).loaded_in("m2") is None
