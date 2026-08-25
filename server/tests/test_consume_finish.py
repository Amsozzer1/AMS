# server/tests/test_consume_finish.py
"""Integration test: Brain._on_finished → consume_plan path.

Verifies that when a printer hits FINISHED, the Brain decrements spool grams even when the
spool's ams_module tag is NOT present in the store's list_spools() result — i.e. the
assignment row's own spool_id is used as the fallback (the gap-aware loadout merge fix).
"""

from __future__ import annotations

import pytest

from amsx.apps.inventory import FakeSpoolStore
from amsx.apps.inventory.resolver import ProposedRow
from amsx.apps.orchestration import Orchestrator
from amsx.brain import Brain
from amsx.config import Config, ModuleConfig, PrinterConfig
from amsx.events import FinishedEvent
from amsx.types import FilamentColor, PlannedSwap, Spool, SwapPlan

pytestmark = pytest.mark.asyncio

_PRINTER_ID = "p1"
_MODULE_ID = "m1"
_SPOOL_ID = "spool-42"
_GRAMS = 15.0


def _make_brain() -> Brain:
    """Build a simulate Brain with one printer + one module, but no real hardware."""
    config = Config(
        printers=[
            PrinterConfig(
                id=_PRINTER_ID, model="x1", serial="SIM001", access_code="x", ip="127.0.0.1"
            )
        ],
        modules=[
            ModuleConfig(id=_MODULE_ID, cluster_id="c", filament_index=0),
        ],
    )
    return Brain(config, simulate=True)


@pytest.fixture
async def brain():
    b = _make_brain()
    await b.start()
    yield b
    await b.stop()


def _make_plan(grams: float) -> SwapPlan:
    """A plan with one colour at filament_index=0 and the given grams."""
    return SwapPlan(
        swaps=[PlannedSwap(seq=1, filament_index=0, tag="t1")],
        colors=[FilamentColor(index=0, material="PLA", color_hex="FFFFFF", grams=grams)],
    )


async def test_on_finished_consumes_from_assignment_row_spool(brain: Brain):
    """_on_finished should consume grams via the assignment row's spool_id even when the spool
    has no ams_module tag in the store (i.e. loaded dict from list_spools() is empty)."""
    # Store has the spool but WITHOUT an ams_module tag → store-derived loadout is empty.
    spool = Spool(
        id=_SPOOL_ID,
        filament_id="f1",
        material="PLA",
        color_hex="FFFFFF",
        remaining_g=200.0,
        module=None,  # no tag in store — this is the gap-aware path we're testing
    )
    brain.store = FakeSpoolStore([spool])

    plan = _make_plan(_GRAMS)

    # Wire a minimal orchestrator (plan is what _on_finished reads for the colours).
    orch = Orchestrator(
        brain.printers[_PRINTER_ID],
        plan,
        brain.registry,
        brain.events,
        printer_id=_PRINTER_ID,
    )
    brain.orchestrators[_PRINTER_ID] = orch

    # Assignment row carries its own spool_id (confirmed path) — module IS tagged.
    brain.assignment[_PRINTER_ID] = {
        0: ProposedRow(
            index=0,
            material="PLA",
            color_hex="FFFFFF",
            grams=_GRAMS,
            module=_MODULE_ID,
            spool_id=_SPOOL_ID,  # the key: row knows the spool even if store doesn't
            status="loaded",
        )
    }

    # Trigger the FINISH path via the event bus (exercises _on_finished end-to-end).
    await brain.events.publish(FinishedEvent(printer_id=_PRINTER_ID))

    # The spool's remaining_g must have decreased by _GRAMS.
    updated = await brain.store.get_spool(_SPOOL_ID)
    assert updated is not None
    assert updated.remaining_g == pytest.approx(200.0 - _GRAMS)


async def test_on_finished_gap_row_no_consume(brain: Brain):
    """A gap row (no spool_id) must not consume anything and must not raise."""
    spool = Spool(
        id=_SPOOL_ID,
        filament_id="f1",
        material="PLA",
        color_hex="FFFFFF",
        remaining_g=200.0,
        module=None,
    )
    brain.store = FakeSpoolStore([spool])

    plan = _make_plan(_GRAMS)
    orch = Orchestrator(
        brain.printers[_PRINTER_ID],
        plan,
        brain.registry,
        brain.events,
        printer_id=_PRINTER_ID,
    )
    brain.orchestrators[_PRINTER_ID] = orch

    # Gap row: no module, no spool_id.
    brain.assignment[_PRINTER_ID] = {
        0: ProposedRow(
            index=0,
            material="PLA",
            color_hex="FFFFFF",
            grams=_GRAMS,
            module=None,
            spool_id=None,
            status="gap",
        )
    }

    await brain.events.publish(FinishedEvent(printer_id=_PRINTER_ID))

    # remaining_g must be unchanged.
    updated = await brain.store.get_spool(_SPOOL_ID)
    assert updated is not None
    assert updated.remaining_g == pytest.approx(200.0)


async def test_on_finished_store_loadout_takes_lower_precedence(brain: Brain):
    """When both the store AND the assignment row know the spool, assignment row wins (same result
    here, but confirms the merge doesn't double-count or skip)."""
    spool = Spool(
        id=_SPOOL_ID,
        filament_id="f1",
        material="PLA",
        color_hex="FFFFFF",
        remaining_g=300.0,
        module=_MODULE_ID,  # store also has the tag this time
    )
    brain.store = FakeSpoolStore([spool])

    plan = _make_plan(_GRAMS)
    orch = Orchestrator(
        brain.printers[_PRINTER_ID],
        plan,
        brain.registry,
        brain.events,
        printer_id=_PRINTER_ID,
    )
    brain.orchestrators[_PRINTER_ID] = orch

    brain.assignment[_PRINTER_ID] = {
        0: ProposedRow(
            index=0,
            material="PLA",
            color_hex="FFFFFF",
            grams=_GRAMS,
            module=_MODULE_ID,
            spool_id=_SPOOL_ID,
            status="loaded",
        )
    }

    await brain.events.publish(FinishedEvent(printer_id=_PRINTER_ID))

    updated = await brain.store.get_spool(_SPOOL_ID)
    assert updated is not None
    # Only consumed once — not double-counted even though both store and row know the spool.
    assert updated.remaining_g == pytest.approx(300.0 - _GRAMS)
