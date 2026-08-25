"""printer — Printer, PrinterState (loaded_filament is Pi-authoritative).

``Printer`` is the live model of one machine. On ``connect()`` it pulls the FULL report once
to seed ``PrinterState``, then applies incremental DELTAS as each report arrives, emitting
typed ``PauseEvent`` / ``SensorEvent`` on the ``EventBus`` when the fields the Orchestrator
cares about change. It satisfies ``amsx.protocols.PrinterControl`` so the Orchestrator can use
it through that Protocol (real MQTT or simulator, X1/P1 or A1 — all hidden).

**Single-brain:** ``PrinterState.loaded_filament`` is **Pi-authoritative**. The report is
reconciled against it (a mismatch raises a FaultEvent-worthy signal), never blindly trusted.

⚠️ PHASE-0: the report field names this reads (stage / pause-reason / sensor) are unconfirmed
and live in ``X1P1Driver`` behind ``# PHASE-0: verify`` comments. The state-machine + event
emission here are real and simulator-tested; only the wire facts are pending the v0.2 spike.
"""

from __future__ import annotations

import copy
import logging

from ..enums import PauseReason, PrinterStage
from ..events import EventBus, FaultEvent, FinishedEvent, PauseEvent, SensorEvent
from ..transport import FtpClient, PrinterLink, Report
from ..types import FilamentRef, PrinterId
from .drivers import PrinterDriver

log = logging.getLogger("amsx.printer")

# Map the driver-parsed stage string → our PrinterStage enum. The RHS keys are PHASE-0 guesses.
# PHASE-0: verify — the actual gcode_state literals Bambu emits (docs/09 UNVERIFIED #1).
_STAGE_FROM_REPORT: dict[str, PrinterStage] = {
    "IDLE": PrinterStage.IDLE,
    "PREPARE": PrinterStage.PRINTING,  # PHASE-0: verify
    "RUNNING": PrinterStage.PRINTING,  # PHASE-0: verify
    "PAUSE": PrinterStage.PAUSED,  # PHASE-0: verify
    "PAUSED": PrinterStage.PAUSED,  # PHASE-0: verify
    "FINISH": PrinterStage.FINISHED,  # PHASE-0: verify
    "FAILED": PrinterStage.ERROR,  # PHASE-0: verify
}


def _deep_merge(base: dict, delta: dict) -> None:
    """Recursively merge ``delta`` into ``base`` in place (nested dicts merged, not replaced).

    Used to accumulate Bambu's full report + incremental deltas into one complete snapshot.
    Non-dict values (incl. lists) are replaced wholesale — the printer resends full arrays.
    """
    for key, val in delta.items():
        existing = base.get(key)
        if isinstance(val, dict) and isinstance(existing, dict):
            _deep_merge(existing, val)
        else:
            base[key] = val


class PrinterState:
    """Cached snapshot of one printer, seeded by the full report and mutated by deltas.

    Fields mirror docs/10. ``loaded_filament`` is the Pi-authoritative belief and is NEVER set
    from a report — only the Brain (Orchestrator, on a successful swap) sets it.
    """

    def __init__(self) -> None:
        self.stage: PrinterStage = PrinterStage.IDLE
        self.pause_reason: PauseReason | None = None
        self.progress: dict[str, object] = {}  # { layer?, percent?, line? }
        self.filament_sensor: bool = False  # printer's own present-sensor
        self.loaded_filament: FilamentRef | None = None  # ← Pi-AUTHORITATIVE
        self.raw: dict[str, object] = {}  # last full report, for fields we don't model yet


class Printer:
    """Live model + authoritative truth for one machine. Satisfies ``PrinterControl``.

    Sequencing of the Option-A change routine lives here; the model-specific payloads live in
    the ``PrinterDriver``; the wire lives in the ``PrinterLink``.
    """

    def __init__(
        self,
        printer_id: PrinterId,
        link: PrinterLink,
        driver: PrinterDriver,
        bus: EventBus,
        ftp: FtpClient | None = None,
    ) -> None:
        self.id = printer_id
        self.link = link
        self.driver = driver
        self.bus = bus
        self.ftp = ftp
        self.state = PrinterState()
        self._seeded = False  # True once the full report has seeded state

    # -- lifecycle ---------------------------------------------------------------------------
    async def connect(self) -> None:
        """Register the report handler, then pull the FULL state once.

        After seeding, ``on_report`` applies deltas. The full-pull request envelope is a
        PHASE-0 guess (Bambu's ``pushall``); the *handler wiring* is real.
        """
        self.link.on_report(self.on_report)
        # PHASE-0: verify — the real "give me the full state" request (community: a "pushall"
        # under {"pushing": {"command": "pushall"}}). Sent so a real printer would reply with a
        # full report; the simulator is fed its full report directly in tests.
        await self.link.request({"pushing": {"command": "pushall"}})  # PHASE-0: verify envelope

    async def on_report(self, report: Report) -> None:
        """Apply a report (full on first, delta after) and emit typed events on changes.

        The first report seeds the cache as the full snapshot; subsequent reports are treated
        as deltas (only the fields they carry are updated). Stage→PAUSED emits a ``PauseEvent``;
        a change in the filament-present sensor emits a ``SensorEvent``.
        """
        prev_stage = self.state.stage
        prev_sensor = self.state.filament_sensor

        if not self._seeded:
            # Full report: keep the whole thing as raw; treat it as the baseline.
            self.state.raw = copy.deepcopy(dict(report))
            self._seeded = True
            log.info("printer %s: full state seeded (stage=%s)", self.id, self.state.stage)
        else:
            log.debug("printer %s: report delta (%d top-level keys)", self.id, len(report))
            # Delta: DEEP-merge into raw so the accumulated snapshot stays complete. Bambu sends
            # tiny deltas like {"print": {"bed_temper": ...}}; a shallow update would replace the
            # whole "print" blob and discard every other field. Deep merge keeps them all current.
            _deep_merge(self.state.raw, report)

        self._apply_fields(report)
        await self._reconcile_loaded_filament(report)

        # Emit a pause event on a fresh transition into PAUSED.
        if self.state.stage == PrinterStage.PAUSED and prev_stage != PrinterStage.PAUSED:
            reason = self.state.pause_reason or PauseReason.UNKNOWN
            layer, line = self._progress_layer(), self._progress_line()
            log.info(
                "printer %s: ▶ PAUSE detected (reason=%s line=%s layer=%s) — emitting PauseEvent",
                self.id,
                reason,
                line,
                layer,
            )
            await self.bus.publish(
                PauseEvent(printer_id=self.id, reason=reason, layer=layer, line=line)
            )

        # Emit a finished event on a fresh transition into FINISHED.
        if self.state.stage == PrinterStage.FINISHED and prev_stage != PrinterStage.FINISHED:
            log.info("printer %s: ▶ FINISHED — emitting FinishedEvent", self.id)
            await self.bus.publish(FinishedEvent(printer_id=self.id))

        # Emit a sensor event when the present-sensor actually changes.
        if self.state.filament_sensor != prev_sensor:
            log.info(
                "printer %s: filament sensor → %s",
                self.id,
                "PRESENT" if self.state.filament_sensor else "absent",
            )
            await self.bus.publish(
                SensorEvent(printer_id=self.id, filament_present=self.state.filament_sensor)
            )

    def _apply_fields(self, report: Report) -> None:
        """Update modelled fields from whatever the report carries (delta-safe)."""
        # Stage.
        stage = self._parse_stage(report)
        if stage is not None:
            self.state.stage = stage
            self.state.pause_reason = (
                self.driver.parse_pause_reason(report) if stage == PrinterStage.PAUSED else None
            )

        # Filament-present sensor (None ⇒ this delta didn't mention it; leave cached value).
        sensor = self.driver.parse_filament_present(report)
        if sensor is not None:
            self.state.filament_sensor = sensor

        # Progress (best-effort; PHASE-0 field names).
        print_blob = report.get("print")
        if isinstance(print_blob, dict):
            for src, dst in (("layer_num", "layer"), ("mc_percent", "percent")):
                # PHASE-0: verify — real progress field names (docs/10 progress dict).
                val = print_blob.get(src)
                if val is not None:
                    self.state.progress[dst] = val
            # Gcode line number — Bambu reports it as a STRING int. Parse to int so the pause
            # guard (open question #17) gets a real line; delta-safe (skip if absent/garbage).
            # PHASE-0: verify — field name "mc_print_line_number" (community-reported).
            line_raw = print_blob.get("mc_print_line_number")
            if isinstance(line_raw, str) and line_raw.strip().lstrip("-").isdigit():
                self.state.progress["line"] = int(line_raw)
            elif isinstance(line_raw, int) and not isinstance(line_raw, bool):
                self.state.progress["line"] = line_raw

    def _parse_stage(self, report: Report) -> PrinterStage | None:
        """Map the report's stage string to a PrinterStage, or None if absent in this delta."""
        print_blob = report.get("print")
        if not isinstance(print_blob, dict):
            return None
        # PHASE-0: verify — field name "gcode_state" (docs/09 UNVERIFIED #1).
        raw_stage = print_blob.get("gcode_state")
        if not isinstance(raw_stage, str):
            return None
        return _STAGE_FROM_REPORT.get(raw_stage.upper())

    def _progress_layer(self) -> int | None:
        layer = self.state.progress.get("layer")
        return layer if isinstance(layer, int) else None

    def _progress_line(self) -> int | None:
        line = self.state.progress.get("line")
        return line if isinstance(line, int) else None

    async def _reconcile_loaded_filament(self, report: Report) -> None:
        """Single-brain reconciliation: the report is checked against our authoritative belief.

        We never set ``loaded_filament`` from a report. If the report claims a different loaded
        filament than the Brain believes, that's a discrepancy worth surfacing — but it does
        NOT overwrite our truth. PHASE-0: the report field that *claims* a loaded filament is
        unconfirmed, so this currently only guards; the active set happens in the Orchestrator.
        """
        believed = self.state.loaded_filament
        if believed is None:
            return
        print_blob = report.get("print")
        if not isinstance(print_blob, dict):
            return
        # PHASE-0: verify — the report field that names the currently-loaded filament index
        # (e.g. an AMS tray id or external-spool index). Guess below; do not trust.
        reported_index = print_blob.get("tray_now")  # PHASE-0: verify field name
        if isinstance(reported_index, int) and reported_index != believed.index:
            await self.bus.publish(
                FaultEvent(
                    source=f"printer:{self.id}",
                    detail=(
                        f"loaded_filament reconcile mismatch: brain believes index "
                        f"{believed.index}, report claims {reported_index} — keeping brain's "
                        f"truth (single-brain)"
                    ),
                )
            )

    def set_loaded_filament(self, ref: FilamentRef | None) -> None:
        """Brain-only setter for the Pi-authoritative loaded filament (called after a swap)."""
        self.state.loaded_filament = ref

    def read_external_filament(self) -> tuple[str | None, str | None]:
        """Read (material, color_hex6) from the cached vt_tray snapshot.

        Delegates to the driver so X1/P1 returns (None, None) and A1 extracts from
        ``state.raw["print"]["vt_tray"]`` — no live MQTT call, just the cached full report.
        """
        return self.driver.parse_external_filament({"print": self.state.raw.get("print", {})})

    async def set_external_filament(self, material: str | None, color_hex: str | None) -> None:
        """Tell the printer what filament it now holds (after a swap) via ams_filament_setting."""
        await self.link.request(self.driver.request_set_external_filament(material, color_hex))

    # -- PrinterControl Protocol --------------------------------------------------------------
    @property
    def loaded_filament(self) -> FilamentRef | None:
        return self.state.loaded_filament

    async def filament_present(self) -> bool:
        """The printer's own present-sensor, from the cached state (delta-updated)."""
        return self.state.filament_sensor

    async def routine_unload(self) -> None:
        """Drive Bambu's own 'unload old filament' step over MQTT (Option A)."""
        log.debug("printer %s: MQTT → unload_filament", self.id)
        await self.link.request(self.driver.request_unload())

    async def routine_extrude(self) -> None:
        """Drive Bambu's own 'extrude / load new filament' step over MQTT (Option A)."""
        log.debug("printer %s: MQTT → extrude (raw load fallback)", self.id)
        await self.link.request(self.driver.request_extrude())

    async def routine_confirm_resume(self) -> None:
        """Confirm the change is done and resume the print (the load-bearing gate)."""
        log.debug("printer %s: MQTT → resume", self.id)
        await self.link.request(self.driver.request_confirm_resume())

    async def send_job(self, file: str) -> str:
        """Upload the sliced job via FTPS and return its remote path.

        PHASE-0: verify — FTPS path semantics (transport.FtpsClient; docs/03).
        """
        if self.ftp is None:
            raise RuntimeError(
                f"Printer {self.id}: no FtpClient configured; cannot send_job (PHASE-0 wiring)."
            )
        log.info("printer %s: uploading job %s …", self.id, file)
        remote = await self.ftp.upload(self.id, file)
        log.info("printer %s: job uploaded → %s", self.id, remote)
        return remote

    async def start_print(self, path: str) -> None:
        """Start printing the uploaded file at ``path``."""
        payload = self.driver.request_start_print(path)
        blob = payload.get("print")
        url = blob.get("url") if isinstance(blob, dict) else None
        log.info("printer %s: start_print → project_file (url=%s)", self.id, url)
        await self.link.request(payload)


__all__ = ["Printer", "PrinterState"]
