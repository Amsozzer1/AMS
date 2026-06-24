"""Simulator-backed tests for the Printer state model + event emission (no network).

Proves, using ``SimulatedPrinterLink`` + scripted report dicts:
  - full state on connect, then incremental DELTA application;
  - a stage→PAUSED report emits a typed ``PauseEvent`` on the EventBus;
  - a filament-sensor change emits a typed ``SensorEvent``;
  - the Printer satisfies the runtime_checkable ``PrinterControl`` Protocol;
  - single-brain: ``loaded_filament`` is never set from a report.

The report field names mirror the PHASE-0 guesses in ``X1P1Driver`` — these tests pin the
*state-machine behaviour*, not the wire facts (those wait on the v0.2 spike).
"""

from __future__ import annotations

import pytest

from amsx.events import EventBus, FaultEvent, PauseEvent, SensorEvent
from amsx.printer import Printer, PrinterState
from amsx.printer.drivers import X1P1Driver
from amsx.protocols import PrinterControl
from amsx.transport import SimulatedFtpClient, SimulatedPrinterLink
from amsx.types import FilamentRef, PauseReason, PrinterStage


class _Recorder:
    """Collects events published on the EventBus for assertions."""

    def __init__(self, bus: EventBus) -> None:
        self.pauses: list[PauseEvent] = []
        self.sensors: list[SensorEvent] = []
        self.faults: list[FaultEvent] = []
        bus.subscribe(PauseEvent, self._on_pause)
        bus.subscribe(SensorEvent, self._on_sensor)
        bus.subscribe(FaultEvent, self._on_fault)

    async def _on_pause(self, e: object) -> None:
        assert isinstance(e, PauseEvent)
        self.pauses.append(e)

    async def _on_sensor(self, e: object) -> None:
        assert isinstance(e, SensorEvent)
        self.sensors.append(e)

    async def _on_fault(self, e: object) -> None:
        assert isinstance(e, FaultEvent)
        self.faults.append(e)


def _make_printer() -> tuple[Printer, SimulatedPrinterLink, EventBus, _Recorder]:
    bus = EventBus()
    link = SimulatedPrinterLink(printer_id="p1")
    printer = Printer(
        printer_id="p1",
        link=link,
        driver=X1P1Driver(),
        bus=bus,
        ftp=SimulatedFtpClient(),
    )
    rec = _Recorder(bus)
    return printer, link, bus, rec


def _full_report(stage: str = "RUNNING", sensor: bool = True) -> dict:
    """A 'full' report shaped like the PHASE-0 guesses in X1P1Driver."""
    return {
        "print": {
            "gcode_state": stage,
            "filam_bak": sensor,
            "layer_num": 0,
            "mc_percent": 0,
        }
    }


async def test_protocol_smoke() -> None:
    """The Printer satisfies the runtime_checkable PrinterControl Protocol."""
    printer, _link, _bus, _rec = _make_printer()
    assert isinstance(printer, PrinterControl)


async def test_full_state_on_connect_then_deltas() -> None:
    printer, link, _bus, _rec = _make_printer()
    await printer.connect()

    # connect() should have issued a full-state pull request on the link.
    assert link.sent, "connect() should request the full state once"

    # Seed with the FULL report.
    await link.feed_report(_full_report(stage="RUNNING", sensor=True))
    assert printer.state.stage is PrinterStage.PRINTING
    assert printer.state.filament_sensor is True
    assert printer.state.raw  # full report cached as baseline

    # A DELTA that mentions ONLY progress must not disturb stage/sensor.
    await link.feed_report({"print": {"layer_num": 42}})
    assert printer.state.stage is PrinterStage.PRINTING  # unchanged by partial delta
    assert printer.state.filament_sensor is True  # unchanged: delta didn't mention sensor
    assert printer.state.progress["layer"] == 42  # delta applied
    # raw merged the delta on top of the baseline.
    assert isinstance(printer.state.raw["print"], dict)


async def test_raw_deep_merges_deltas() -> None:
    """A delta touching one nested field must not wipe the rest of the accumulated snapshot."""
    printer, link, _bus, _rec = _make_printer()
    await printer.connect()
    await link.feed_report(_full_report(stage="RUNNING", sensor=True))

    # Delta mentions only layer_num; deep-merge must keep the baseline fields intact.
    await link.feed_report({"print": {"layer_num": 42}})
    pr = printer.state.raw["print"]
    assert pr["gcode_state"] == "RUNNING"  # preserved, not clobbered by the small delta
    assert pr["filam_bak"] is True  # preserved
    assert pr["layer_num"] == 42  # delta applied


async def test_pause_report_emits_pause_event() -> None:
    printer, link, _bus, rec = _make_printer()
    await printer.connect()
    await link.feed_report(_full_report(stage="RUNNING", sensor=True))
    assert not rec.pauses

    # Transition into PAUSED → exactly one PauseEvent.
    await link.feed_report({"print": {"gcode_state": "PAUSE"}})
    assert printer.state.stage is PrinterStage.PAUSED
    assert len(rec.pauses) == 1
    assert rec.pauses[0].printer_id == "p1"
    # PHASE-0: with no confirmed change-tag in the report, reason defaults to UNKNOWN and the
    # Orchestrator validates against its authored plan (single-brain-safe).
    assert rec.pauses[0].reason is PauseReason.UNKNOWN

    # A second PAUSE delta (still paused) must NOT re-emit.
    await link.feed_report({"print": {"gcode_state": "PAUSE"}})
    assert len(rec.pauses) == 1


async def test_sensor_change_emits_sensor_event() -> None:
    printer, link, _bus, rec = _make_printer()
    await printer.connect()
    await link.feed_report(_full_report(stage="RUNNING", sensor=True))
    # Seeding from False→True default emits one SensorEvent.
    assert [e.filament_present for e in rec.sensors] == [True]

    # Sensor trips to absent → one more event.
    await link.feed_report({"print": {"filam_bak": False}})
    assert printer.state.filament_sensor is False
    assert [e.filament_present for e in rec.sensors] == [True, False]

    # A delta that doesn't mention the sensor must NOT emit.
    await link.feed_report({"print": {"layer_num": 7}})
    assert [e.filament_present for e in rec.sensors] == [True, False]


async def test_loaded_filament_is_pi_authoritative() -> None:
    """Reports never set loaded_filament; a conflicting report raises a FaultEvent, not a set."""
    printer, link, _bus, rec = _make_printer()
    await printer.connect()
    await link.feed_report(_full_report())

    # Report alone never populates the Pi-authoritative belief.
    assert printer.loaded_filament is None

    # Brain sets the truth (as the Orchestrator would after a successful swap).
    printer.set_loaded_filament(FilamentRef(index=2, material="PLA", color="red"))
    assert printer.loaded_filament == FilamentRef(index=2, material="PLA", color="red")

    # A report claiming a DIFFERENT loaded index surfaces a FaultEvent and does NOT overwrite.
    await link.feed_report({"print": {"tray_now": 5}})
    assert printer.loaded_filament.index == 2  # truth preserved
    assert len(rec.faults) == 1
    assert "reconcile mismatch" in rec.faults[0].detail


async def test_routine_calls_send_driver_payloads() -> None:
    """The Option-A routine methods push the driver's (PHASE-0) payloads over the link."""
    printer, link, _bus, _rec = _make_printer()
    await printer.connect()
    base = len(link.sent)

    await printer.routine_unload()
    await printer.routine_extrude()
    await printer.routine_confirm_resume()
    assert len(link.sent) == base + 3
    # Each payload is the driver's request dict (shape, not confirmed wire facts).
    assert all(isinstance(p, dict) for p in link.sent[base:])


async def test_send_job_and_start_print() -> None:
    printer, link, _bus, _rec = _make_printer()
    await printer.connect()
    remote = await printer.send_job("/jobs/two_color.gcode.3mf")
    assert remote == "/cache/two_color.gcode.3mf"

    base = len(link.sent)
    await printer.start_print(remote)
    assert len(link.sent) == base + 1


async def test_state_defaults() -> None:
    state = PrinterState()
    assert state.stage is PrinterStage.IDLE
    assert state.pause_reason is None
    assert state.loaded_filament is None
    assert state.filament_sensor is False


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
