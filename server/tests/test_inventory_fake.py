# server/tests/test_inventory_fake.py
import pytest

from amsx.apps.inventory import FakeSpoolStore, SpoolStore
from amsx.types import Spool

pytestmark = pytest.mark.asyncio


def _store():
    return FakeSpoolStore(
        [
            Spool(
                id="1",
                filament_id="10",
                material="PLA",
                color_hex="FFFFFF",
                name="White",
                remaining_g=900,
                module="m1",
            ),
            Spool(
                id="2",
                filament_id="11",
                material="PLA",
                color_hex="FF0000",
                name="Red",
                remaining_g=400,
                module="m2",
            ),
            Spool(
                id="3",
                filament_id="12",
                material="PLA",
                color_hex="FF0000",
                name="Red2",
                remaining_g=50,
                module=None,
            ),
        ]
    )


async def test_is_a_spoolstore():
    assert isinstance(_store(), SpoolStore)


async def test_loaded_in_and_set_module():
    s = _store()
    assert (await s.loaded_in("m2")).id == "2"
    await s.set_module("3", "m3")
    assert (await s.loaded_in("m3")).id == "3"
    await s.set_module("2", None)
    assert await s.loaded_in("m2") is None


async def test_match_by_material_and_color():
    s = _store()
    reds = await s.match("PLA", "FF0000")
    assert {sp.id for sp in reds} == {"2", "3"}


async def test_consume_decrements():
    s = _store()
    await s.consume("2", 100)
    assert (await s.get_spool("2")).remaining_g == 300
