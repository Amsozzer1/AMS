import pytest

from amsx.inventory import FakeSpoolStore
from amsx.inventory.resolver import Resolver
from amsx.types import FilamentColor, PlannedSwap, Spool, SwapPlan

pytestmark = pytest.mark.asyncio


async def test_propose_matches_loaded_and_flags_gap():
    store = FakeSpoolStore(
        [
            Spool(id="1", filament_id="10", material="PLA", color_hex="FFFFFF", module="m1"),
            Spool(id="2", filament_id="11", material="PLA", color_hex="FF0000", module="m2"),
        ]
    )
    plan = SwapPlan(
        swaps=[
            PlannedSwap(
                seq=1,
                filament_index=5,
                tag="t",
                layer=2,
                line=1,
                material="PLA",
                color_hex="0000FF",
            )
        ],  # blue: not loaded -> gap
        base=FilamentColor(1, "PLA", "FFFFFF", 0.3),
        colors=[FilamentColor(1, "PLA", "FFFFFF", 0.3), FilamentColor(5, "PLA", "0000FF", 1.0)],
    )
    rows = await Resolver(store).propose(plan)
    assert rows[1].status == "loaded" and rows[1].module == "m1"  # base white -> m1
    assert rows[5].status == "gap" and rows[5].module is None  # blue -> gap
