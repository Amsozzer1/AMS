"""End-to-end + edge-case tests for the v0 orchestrator and the v0 module.

Covers (per the orchestrator agent's definition of done, docs/02 / docs/06 / docs/10):
* happy path: simulated print → PauseEvent → module prompt (auto-answered) → simulated sensor
  trip → resume → cursor advances → done.
* an untagged / stray pause → handled as an EXCEPTION (safe-hold + alert, no swap).
* a sensor timeout → FAULT + safe-hold.
* the Cluster one-module-at-a-time interlock.

Everything runs against `FakePrinter` (a `PrinterControl`) and auto-answered `ManualModule`
prompts — no hardware, no real printer package.
"""

from __future__ import annotations

import asyncio

import pytest

from amsx.events import EventBus, FaultEvent, PauseEvent, SensorEvent
from amsx.module import Cluster, ClusterBusyError, ManualModule, ModuleRegistry
from amsx.orchestration import Orchestrator, SwapStateMachine
from amsx.types import (
    ModuleState,
    PauseReason,
    PlannedSwap,
    SwapPlan,
    SwapState,
)
from fakes import FakePrinter, auto_answer

PRINTER_ID = "x1c-1"


def _plan() -> SwapPlan:
    # `line` is the gcode line of each swap's M400 U1 — the #17 line guard for untagged pauses.
    return SwapPlan(
        swaps=[
            PlannedSwap(seq=0, filament_index=1, tag="AMSX-SWAP-0", line=1000),
            PlannedSwap(seq=1, filament_index=2, tag="AMSX-SWAP-1", line=5000),
        ]
    )


def _registry(prompts: list[str] | None = None) -> ModuleRegistry:
    prompter = auto_answer(record=prompts)
    modules = [
        ManualModule("mod-a", prompter=prompter),
        ManualModule("mod-b", prompter=prompter),
        ManualModule("mod-c", prompter=prompter),
    ]
    # filament_index → module id (the config map ModuleRegistry uses today).
    index_map = {0: "mod-a", 1: "mod-b", 2: "mod-c"}
    return ModuleRegistry(modules, index_map)


def _make_orchestrator(printer: FakePrinter, prompts: list[str] | None = None) -> Orchestrator:
    orch = Orchestrator(
        printer,
        _plan(),
        _registry(prompts),
        EventBus(),
        printer_id=PRINTER_ID,
        sense_timeout_s=2.0,
        sense_poll_s=0.01,
    )
    orch.subscribe()
    return orch


# ---------------------------------------------------------------------------------------------
# Happy path: full closed loop, cursor advances to done.
# ---------------------------------------------------------------------------------------------
async def test_end_to_end_swap_advances_cursor():
    prompts: list[str] = []
    # Sensor trips after one poll on each swap (simulated feed reaching the printer inlet).
    printer = FakePrinter(trip_after_polls=1)
    orch = _make_orchestrator(printer, prompts)

    assert orch.cursor == 0
    assert not orch.done

    # First pause (our tagged swap #0) arrives over the bus.
    await orch.bus.publish(
        PauseEvent(printer_id=PRINTER_ID, reason=PauseReason.CHANGE, tag="AMSX-SWAP-0")
    )
    assert orch.cursor == 1
    assert not orch.held
    assert orch.sm.state is SwapState.WATCHING

    # Reset the sensor for the second swap and fire the second tagged pause.
    printer.reset_sensor()
    await orch.bus.publish(
        PauseEvent(printer_id=PRINTER_ID, reason=PauseReason.CHANGE, tag="AMSX-SWAP-1")
    )
    assert orch.cursor == 2
    assert orch.done
    assert not orch.held

    # Option-A routine was driven in order for both swaps.
    assert printer.calls.count("routine_unload") == 2
    assert printer.calls.count("routine_confirm_resume") == 2
    # The unload precedes the resume within each swap.
    assert printer.calls.index("routine_unload") < printer.calls.index("routine_confirm_resume")
    # A human was actually prompted (module motion happened).
    assert any("FEED" in p or "FEEDING" in p for p in prompts)
    assert any("STOP" in p for p in prompts)


async def test_sensor_event_can_close_the_loop():
    """A pushed SensorEvent (not just polling) trips the sensing loop."""
    # trip_after_polls=None → polling alone never trips; only the SensorEvent will.
    printer = FakePrinter(trip_after_polls=None)
    orch = _make_orchestrator(printer)

    async def fire_sensor_soon():
        await asyncio.sleep(0.05)
        await orch.bus.publish(SensorEvent(printer_id=PRINTER_ID, filament_present=True))

    sensor_task = asyncio.create_task(fire_sensor_soon())
    await orch.bus.publish(
        PauseEvent(printer_id=PRINTER_ID, reason=PauseReason.CHANGE, tag="AMSX-SWAP-0")
    )
    await sensor_task
    assert orch.cursor == 1
    assert not orch.held


# ---------------------------------------------------------------------------------------------
# Untagged / stray pause: exception, no swap.
# ---------------------------------------------------------------------------------------------
async def test_untagged_user_pause_holds_and_does_not_swap():
    printer = FakePrinter(trip_after_polls=1)
    orch = _make_orchestrator(printer)

    # A user hits pause on the printer: no tag, explicit USER reason → never our swap.
    await orch.bus.publish(PauseEvent(printer_id=PRINTER_ID, reason=PauseReason.USER, tag=None))

    assert orch.cursor == 0  # never advanced
    assert orch.held is True
    assert orch.alerts  # an alert was raised
    assert "user pause" in orch.alerts[-1]
    # No routine ran — we never touched the printer's change sequence.
    assert printer.calls == []


async def test_mismatched_tag_pause_holds_and_does_not_swap():
    printer = FakePrinter(trip_after_polls=1)
    orch = _make_orchestrator(printer)

    await orch.bus.publish(
        PauseEvent(printer_id=PRINTER_ID, reason=PauseReason.CHANGE, tag="SOME-OTHER-TAG")
    )

    assert orch.cursor == 0
    assert orch.held is True
    assert "does not match" in orch.alerts[-1]
    assert printer.calls == []


# ---------------------------------------------------------------------------------------------
# Untagged REAL Bambu pause (open question #17): bound by ordinal cursor + line guard.
# ---------------------------------------------------------------------------------------------
async def test_untagged_pause_with_matching_line_swaps_and_advances():
    """A real Bambu M400 U1 pause: no tag, reason UNKNOWN, line matching plan.swaps[0].line."""
    printer = FakePrinter(trip_after_polls=1)
    orch = _make_orchestrator(printer)

    await orch.bus.publish(
        PauseEvent(printer_id=PRINTER_ID, reason=PauseReason.UNKNOWN, tag=None, line=1000)
    )

    assert orch.cursor == 1
    assert orch.held is False
    assert orch.sm.state is SwapState.WATCHING
    assert "routine_unload" in printer.calls
    assert "routine_confirm_resume" in printer.calls


async def test_untagged_pause_with_near_line_within_tolerance_swaps():
    """The printer's reported line may be a little off the exact M400 U1 line — still ours."""
    printer = FakePrinter(trip_after_polls=1)
    orch = _make_orchestrator(printer)

    # expected.line=1000, tolerance ±50 → 1037 is in-window.
    await orch.bus.publish(
        PauseEvent(printer_id=PRINTER_ID, reason=PauseReason.UNKNOWN, tag=None, line=1037)
    )

    assert orch.cursor == 1
    assert orch.held is False


async def test_untagged_pause_with_far_line_holds():
    """A line far from any expected swap → the guard rejects it (safe-hold, no swap)."""
    printer = FakePrinter(trip_after_polls=1)
    orch = _make_orchestrator(printer)

    # 3000 is between swap 0 (1000) and swap 1 (5000), far from both → out of range.
    await orch.bus.publish(
        PauseEvent(printer_id=PRINTER_ID, reason=PauseReason.UNKNOWN, tag=None, line=3000)
    )

    assert orch.cursor == 0
    assert orch.held is True
    assert "out of range" in orch.alerts[-1]
    assert "3000" in orch.alerts[-1]
    assert printer.calls == []


async def test_untagged_pause_without_line_accepted_unguarded():
    """Line info absent → degrade to pure ordinal: accept + advance, but flag UNGUARDED."""
    printer = FakePrinter(trip_after_polls=1)
    orch = _make_orchestrator(printer)

    await orch.bus.publish(
        PauseEvent(printer_id=PRINTER_ID, reason=PauseReason.UNKNOWN, tag=None, line=None)
    )

    assert orch.cursor == 1  # advanced ordinally
    assert orch.held is False  # accepting unguarded does NOT hold the loop
    assert orch.alerts  # but an alert was raised
    assert "UNGUARDED" in orch.alerts[-1]
    assert "routine_confirm_resume" in printer.calls


async def test_multiple_changes_same_layer_disambiguated_by_line():
    """Two changes on one layer: same `layer`, distinct lines. Two untagged pauses at those
    lines advance the cursor twice — line is the guard, the cursor is the sequencer.
    """
    plan = SwapPlan(
        swaps=[
            PlannedSwap(seq=0, filament_index=1, tag="t0", layer=42, line=2000),
            PlannedSwap(seq=1, filament_index=2, tag="t1", layer=42, line=2080),
        ]
    )
    printer = FakePrinter(trip_after_polls=1)
    orch = Orchestrator(
        printer,
        plan,
        _registry(),
        EventBus(),
        printer_id=PRINTER_ID,
        sense_timeout_s=2.0,
        sense_poll_s=0.01,
    )
    orch.subscribe()

    await orch.bus.publish(
        PauseEvent(printer_id=PRINTER_ID, reason=PauseReason.UNKNOWN, tag=None, line=2000)
    )
    assert orch.cursor == 1
    assert not orch.held

    printer.reset_sensor()
    await orch.bus.publish(
        PauseEvent(printer_id=PRINTER_ID, reason=PauseReason.UNKNOWN, tag=None, line=2080)
    )
    assert orch.cursor == 2
    assert orch.done
    assert not orch.held


def _layer_orchestrator(printer: FakePrinter) -> Orchestrator:
    """Orchestrator whose plan binds by LAYER — the real A1 case (line is unusable)."""
    plan = SwapPlan(swaps=[PlannedSwap(seq=0, filament_index=1, tag="t0", layer=75, line=133871)])
    orch = Orchestrator(
        printer,
        plan,
        _registry(),
        EventBus(),
        printer_id=PRINTER_ID,
        sense_timeout_s=2.0,
        sense_poll_s=0.01,
    )
    orch.subscribe()
    return orch


async def test_a1_untagged_pause_binds_by_layer_despite_line_zero():
    """The real A1 pause: reason=UNKNOWN, line=0 (unusable), layer=75 matches the swap → swap.

    Regression for the live 2026-06-25 failure where the layer-75 change was safe-held because the
    line guard saw line 0. Layer is now the primary guard, so this binds and runs.
    """
    printer = FakePrinter(trip_after_polls=1)
    orch = _layer_orchestrator(printer)

    await orch.bus.publish(
        PauseEvent(printer_id=PRINTER_ID, reason=PauseReason.UNKNOWN, tag=None, layer=75, line=0)
    )

    assert orch.cursor == 1
    assert orch.held is False
    assert "routine_confirm_resume" in printer.calls


async def test_untagged_pause_at_far_layer_holds():
    """The spurious start-of-print pause (layer 0) must NOT be taken as the layer-75 swap."""
    printer = FakePrinter(trip_after_polls=1)
    orch = _layer_orchestrator(printer)

    await orch.bus.publish(
        PauseEvent(printer_id=PRINTER_ID, reason=PauseReason.UNKNOWN, tag=None, layer=0, line=0)
    )

    assert orch.cursor == 0  # not advanced
    assert orch.held is True
    assert "out of range" in orch.alerts[-1]
    assert "routine_confirm_resume" not in printer.calls


async def test_rearm_detaches_old_orchestrator_no_double_swap():
    """Re-arming a printer must detach the old orchestrator from the bus, or a single pause runs
    the swap TWICE (the duplicate-prompt bug observed live 2026-06-25: two submits → 4 prompts)."""
    bus = EventBus()
    printer = FakePrinter(trip_after_polls=1)
    plan = SwapPlan(swaps=[PlannedSwap(seq=0, filament_index=1, tag="t0", layer=2, line=10)])

    old = Orchestrator(
        printer,
        plan,
        _registry(),
        bus,
        printer_id=PRINTER_ID,
        sense_timeout_s=2.0,
        sense_poll_s=0.01,
    )
    old.subscribe()
    # Second arm (what Brain.arm_job now does): detach the old one, then wire the new one.
    old.unsubscribe()
    new = Orchestrator(
        printer,
        plan,
        _registry(),
        bus,
        printer_id=PRINTER_ID,
        sense_timeout_s=2.0,
        sense_poll_s=0.01,
    )
    new.subscribe()

    await bus.publish(
        PauseEvent(printer_id=PRINTER_ID, reason=PauseReason.UNKNOWN, tag=None, layer=2, line=0)
    )

    assert new.cursor == 1  # the live orchestrator ran the swap
    assert old.cursor == 0  # the detached one never heard the pause
    assert printer.calls.count("routine_confirm_resume") == 1  # exactly ONE swap, not two


async def test_module_resolver_overrides_registry():
    """SELECTING drives the module from the injected resolver, not the static config map.

    The config registry maps filament_index 1 → mod-b; the resolver forces 1 → mod-c. The swap
    must drive mod-c (this is what wires the operator's confirmed colour→module assignment in).
    """
    prompts: list[str] = []
    printer = FakePrinter(trip_after_polls=1)
    registry = _registry(prompts)
    orch = Orchestrator(
        printer,
        _plan(),
        registry,
        EventBus(),
        printer_id=PRINTER_ID,
        sense_timeout_s=2.0,
        sense_poll_s=0.01,
        module_resolver=lambda idx: (
            registry.by_id("mod-c") if idx == 1 else registry.for_filament_index(idx)
        ),
    )
    orch.subscribe()

    await orch.bus.publish(
        PauseEvent(printer_id=PRINTER_ID, reason=PauseReason.CHANGE, tag="AMSX-SWAP-0")
    )
    assert orch.cursor == 1 and not orch.held
    assert any("mod-c" in p for p in prompts)  # resolver's module was driven
    assert not any("mod-b" in p for p in prompts)  # NOT the static config map's module


# ---------------------------------------------------------------------------------------------
# Sensor timeout → FAULT + safe-hold.
# ---------------------------------------------------------------------------------------------
async def test_sensor_timeout_faults_and_holds():
    # Sensor never trips → SENSING times out.
    printer = FakePrinter(trip_after_polls=None)
    orch = Orchestrator(
        printer,
        _plan(),
        _registry(),
        EventBus(),
        printer_id=PRINTER_ID,
        sense_timeout_s=0.1,
        sense_poll_s=0.01,
    )
    orch.subscribe()

    await orch.bus.publish(
        PauseEvent(printer_id=PRINTER_ID, reason=PauseReason.CHANGE, tag="AMSX-SWAP-0")
    )

    assert orch.cursor == 0  # swap did not complete
    assert orch.held is True
    assert orch.sm.state is SwapState.FAULT
    assert "never tripped" in orch.alerts[-1]
    # We still drove the unload but never the resume (we faulted mid-swap).
    assert "routine_unload" in printer.calls
    assert "routine_confirm_resume" not in printer.calls


async def test_fault_event_triggers_safe_hold():
    printer = FakePrinter(trip_after_polls=1)
    orch = _make_orchestrator(printer)

    await orch.bus.publish(FaultEvent(source="cluster-1", detail="MQTT disconnect"))

    assert orch.held is True
    assert "MQTT disconnect" in orch.alerts[-1]
    assert orch.cursor == 0


# ---------------------------------------------------------------------------------------------
# ManualModule state machine.
# ---------------------------------------------------------------------------------------------
async def test_manual_module_tracks_state():
    mod = ManualModule("mod-x", prompter=auto_answer())
    assert mod.state is ModuleState.IDLE

    await mod.start_feed()
    assert mod.state is ModuleState.FEEDING
    await mod.stop()
    assert mod.state is ModuleState.IDLE

    result = await mod.retract(100.0)
    assert result.ok and result.moved_mm == 100.0
    assert mod.state is ModuleState.IDLE

    assert await mod.has_filament() is True
    mod.set_has_filament(False)
    assert await mod.has_filament() is False
    assert mod.state is ModuleState.EMPTY

    await mod.abort()
    assert mod.state is ModuleState.FAULT


# ---------------------------------------------------------------------------------------------
# Cluster one-module-at-a-time interlock.
# ---------------------------------------------------------------------------------------------
async def test_cluster_enforces_one_module_at_a_time():
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_motion() -> str:
        started.set()
        await release.wait()
        return "done"

    mod_a = ManualModule("mod-a", prompter=auto_answer())
    mod_b = ManualModule("mod-b", prompter=auto_answer())
    cluster = Cluster("cluster-1", [mod_a, mod_b])

    # Start a long-running move on module A; hold the active slot.
    task_a = asyncio.create_task(cluster.move(mod_a, slow_motion))
    await started.wait()
    assert cluster.active == "mod-a"

    # While A is active, B must be refused — never overlap on the shared hub line.
    with pytest.raises(ClusterBusyError):
        await cluster.move(mod_b, slow_motion)

    # Let A finish; the slot frees and B can now run.
    release.set()
    assert await task_a == "done"
    assert cluster.active is None

    async def quick() -> str:
        return "b-done"

    assert await cluster.move(mod_b, quick) == "b-done"


async def test_cluster_rejects_foreign_module():
    mod_a = ManualModule("mod-a", prompter=auto_answer())
    foreign = ManualModule("not-in-cluster", prompter=auto_answer())
    cluster = Cluster("cluster-1", [mod_a])

    async def quick() -> str:
        return "x"

    with pytest.raises(KeyError):
        await cluster.move(foreign, quick)


# ---------------------------------------------------------------------------------------------
# A stray pause arriving mid-swap must not double-trigger.
# ---------------------------------------------------------------------------------------------
async def test_pause_while_mid_swap_is_held_as_stray():
    sm = SwapStateMachine()
    sm.state = SwapState.FEEDING  # pretend we're mid-swap
    printer = FakePrinter(trip_after_polls=1)
    orch = Orchestrator(
        printer,
        _plan(),
        _registry(),
        EventBus(),
        printer_id=PRINTER_ID,
        sm=sm,
    )
    orch.subscribe()

    await orch.bus.publish(
        PauseEvent(printer_id=PRINTER_ID, reason=PauseReason.CHANGE, tag="AMSX-SWAP-0")
    )

    assert orch.cursor == 0
    assert orch.held is True
    assert "mid-swap" in orch.alerts[-1]
