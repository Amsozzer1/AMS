# server/tests/test_consume.py
import pytest

from amsx.inventory import FakeSpoolStore

# Construct the consume helper directly (pure function over store + plan + assignment).
from amsx.orchestration import consume_plan
from amsx.types import FilamentColor, Spool, SwapPlan

pytestmark = pytest.mark.asyncio


async def test_consume_aggregates_by_spool():
    store = FakeSpoolStore(
        [
            Spool(
                id="1",
                filament_id="10",
                material="PLA",
                color_hex="FFFFFF",
                remaining_g=1000,
                module="m1",
            )
        ]
    )
    plan = SwapPlan(
        colors=[FilamentColor(1, "PLA", "FFFFFF", 4.0), FilamentColor(5, "PLA", "FFFFFF", 6.0)]
    )
    # both indices mapped to m1 -> same spool -> 10g total
    await consume_plan(store, plan, assignment={1: "m1", 5: "m1"}, loaded={"m1": "1"})
    assert (await store.get_spool("1")).remaining_g == 990
