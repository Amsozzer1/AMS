from amsx.config import Config, SpoolmanConfig, load_config  # noqa: F401
from amsx.types import FilamentColor, PlannedSwap, Spool, SwapPlan


def test_spoolman_config_defaults():
    c = Config()
    assert c.spoolman.base_url == "http://localhost:7912/api/v1"
    assert c.spoolman.enabled is True
    assert c.spoolman.active_location is None


def test_spool_and_color_value_objects():
    s = Spool(
        id="7",
        filament_id="3",
        material="PLA",
        color_hex="FF0000",
        name="Red",
        remaining_g=412.0,
        module="m2",
    )
    assert s.module == "m2" and s.archived is False
    fc = FilamentColor(index=5, material="PLA", color_hex="FF0000", grams=1.14)
    assert fc.index == 5


def test_plan_carries_colors():
    plan = SwapPlan(
        swaps=[
            PlannedSwap(
                seq=1,
                filament_index=5,
                tag="swap-001",
                layer=2,
                line=10,
                material="PLA",
                color_hex="FF0000",
            )
        ],
        base=FilamentColor(index=1, material="PLA", color_hex="FFFFFF", grams=0.36),
        colors=[FilamentColor(1, "PLA", "FFFFFF", 0.36), FilamentColor(5, "PLA", "FF0000", 1.14)],
    )
    assert plan.swaps[0].color_hex == "FF0000"
    assert plan.base.color_hex == "FFFFFF"
    assert len(plan.colors) == 2
