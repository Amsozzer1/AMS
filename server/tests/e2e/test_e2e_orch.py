from pathlib import Path

import pytest

from amsx.apps.job import JobParseError
from tests.e2e.utils import PRINTER_ID, a1_brain

FIXTURES = Path(__file__).resolve().parents[3] / "tmp" / "fixtures"
LAYER_TOLERANCE = 1
LINE_TOLERANCE = 50

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def arm(file_name: str):
    return await a1_brain.arm_job(PRINTER_ID, FIXTURES / file_name)


def indices(plan):
    return [swap.filament_index for swap in plan.swaps]


def layers(plan):
    return [swap.layer for swap in plan.swaps]


def lines(plan):
    return [swap.line for swap in plan.swaps]


def tags(plan):
    return [swap.tag for swap in plan.swaps]


def coloured(plan):
    return [swap for swap in plan.swaps if swap.color_hex]


async def test_single_colour_job_has_an_empty_plan():
    orch = await arm("01-single-colour-no-swaps.gcode.3mf")
    assert len(orch.plan) == 0, f"expected no swaps, got {indices(orch.plan)}"
    assert orch.done, "an empty plan should be done before it starts"
    assert orch.cursor == 0, f"cursor should never move, got {orch.cursor}"


async def test_one_swap_job_plans_a_single_swap():
    orch = await arm("02-two-colour-1-swap.gcode.3mf")
    assert len(orch.plan) == 1, f"expected 1 swap, got {len(orch.plan)}"
    assert indices(orch.plan) == [1], f"wrong filament, got {indices(orch.plan)}"
    assert layers(orch.plan) == [12], f"wrong layer, got {layers(orch.plan)}"
    assert not orch.done, "a job with a pending swap is not done"


async def test_two_swap_job_plans_both_swaps():
    orch = await arm("03-three-colour-2-swaps.gcode.3mf")
    assert len(orch.plan) == 2, f"expected 2 swaps, got {len(orch.plan)}"
    assert indices(orch.plan) == [1, 2], f"wrong filaments, got {indices(orch.plan)}"
    assert layers(orch.plan) == [10, 20], f"wrong layers, got {layers(orch.plan)}"
    assert tags(orch.plan) == ["swap-001", "swap-002"], f"wrong tags, got {tags(orch.plan)}"


async def test_matched_colour_metadata_fills_every_swap():
    orch = await arm("04-four-colour-3-swaps.gcode.3mf")
    assert len(orch.plan) == 3, f"expected 3 swaps, got {len(orch.plan)}"
    assert len(coloured(orch.plan)) == 3, (
        f"tool_change count matches the pause count, so every swap should carry a colour; "
        f"only {len(coloured(orch.plan))} did"
    )
    assert all(swap.material for swap in orch.plan.swaps), "every swap should carry a material"


async def test_twelve_swap_job_plans_all_twelve():
    orch = await arm("05-many-swaps-12.gcode.3mf")
    assert len(orch.plan) == 12, f"expected 12 swaps, got {len(orch.plan)}"
    assert tags(orch.plan) == [
        f"swap-{n:03d}" for n in range(1, 13)
    ], f"tags should be sequential, got {tags(orch.plan)}"
    assert layers(orch.plan) == [
        5 * n for n in range(1, 13)
    ], f"wrong layers, got {layers(orch.plan)}"


async def test_bare_pauses_default_to_filament_zero():
    orch = await arm("06-bare-pauses-no-m1020.gcode.3mf")
    assert len(orch.plan) == 3, f"expected 3 swaps, got {len(orch.plan)}"
    assert indices(orch.plan) == [
        0,
        0,
        0,
    ], f"a bare M400 U1 carries no M1020, so every swap is slot 0; got {indices(orch.plan)}"


async def test_alternating_filaments_keep_their_order():
    orch = await arm("07-repeated-filament-abab.gcode.3mf")
    assert indices(orch.plan) == [
        1,
        0,
        1,
        0,
    ], f"repeated filaments must stay in file order, got {indices(orch.plan)}"
    assert tags(orch.plan) == [
        "swap-001",
        "swap-002",
        "swap-003",
        "swap-004",
    ], f"repeats must not collapse, got {tags(orch.plan)}"


async def test_job_without_layer_markers_has_no_layers():
    orch = await arm("08-no-layer-markers.gcode.3mf")
    assert len(orch.plan) == 2, f"expected 2 swaps, got {len(orch.plan)}"
    assert layers(orch.plan) == [
        None,
        None,
    ], f"no layer comments means no layer binding, got {layers(orch.plan)}"
    assert all(
        line is not None for line in lines(orch.plan)
    ), f"the line guard is the only binding left, got {lines(orch.plan)}"


async def test_far_apart_swaps_are_outside_the_line_tolerance():
    orch = await arm("09-swaps-far-apart.gcode.3mf")
    first, second = lines(orch.plan)
    assert second - first > LINE_TOLERANCE, (
        f"swaps {first} and {second} are within +/-{LINE_TOLERANCE} lines, "
        f"so the line guard cannot tell them apart"
    )


async def test_adjacent_layer_swaps_are_separable_by_line():
    orch = await arm("10-swaps-adjacent-layers.gcode.3mf")
    first, second = layers(orch.plan)
    assert (
        second - first <= LAYER_TOLERANCE
    ), f"layers {first} and {second} should sit inside +/-{LAYER_TOLERANCE}"
    assert (
        lines(orch.plan)[0] != lines(orch.plan)[1]
    ), f"the layer guard is ambiguous here, so lines must differ; got {lines(orch.plan)}"


async def test_same_layer_swaps_are_separable_only_by_order():
    orch = await arm("11-two-swaps-same-layer.gcode.3mf")
    assert layers(orch.plan) == [15, 15], f"both swaps share a layer, got {layers(orch.plan)}"
    first, second = lines(orch.plan)
    assert second - first <= LINE_TOLERANCE, (
        f"lines {first} and {second} are inside +/-{LINE_TOLERANCE} too, so neither guard "
        f"can bind these; only the cursor ordinal can"
    )
    assert tags(orch.plan) == ["swap-001", "swap-002"], f"got {tags(orch.plan)}"


async def test_swap_on_first_layer_is_planned():
    orch = await arm("12-swap-on-first-layer.gcode.3mf")
    assert len(orch.plan) == 1, f"expected 1 swap, got {len(orch.plan)}"
    assert layers(orch.plan) == [1], f"expected layer 1, got {layers(orch.plan)}"
    assert lines(orch.plan)[0] > 0, f"line numbers are 1-based, got {lines(orch.plan)}"


async def test_mismatched_colour_metadata_leaves_colours_unset():
    orch = await arm("13-colour-metadata-mismatch.gcode.3mf")
    assert len(orch.plan) == 3, f"expected 3 swaps, got {len(orch.plan)}"
    assert coloured(orch.plan) == [], (
        f"2 tool_changes against 3 pauses should bind nothing rather than guess; "
        f"{len(coloured(orch.plan))} swaps got a colour"
    )


async def test_job_without_slice_info_has_no_colours():
    orch = await arm("14-no-slice-info.gcode.3mf")
    assert len(orch.plan) == 2, f"expected 2 swaps, got {len(orch.plan)}"
    assert orch.plan.colors == [], f"no slice_info means no colours, got {orch.plan.colors}"
    assert orch.plan.base is None, f"no slice_info means no base, got {orch.plan.base}"


async def test_ams_sliced_job_is_rejected():
    with pytest.raises(JobParseError, match="sliced for the AMS"):
        await a1_brain.arm_job(PRINTER_ID, FIXTURES / "15-ams-mis-slice.gcode.3mf")


async def test_unsliced_project_is_rejected():
    with pytest.raises(JobParseError, match=r"plate_1\.gcode"):
        await a1_brain.arm_job(PRINTER_ID, FIXTURES / "16-unsliced-project.gcode.3mf")


async def test_non_zip_file_is_rejected():
    with pytest.raises(JobParseError, match="not a valid 3MF"):
        await a1_brain.arm_job(PRINTER_ID, FIXTURES / "17-not-a-zip.gcode.3mf")
