"""printer.drivers — PrinterDriver interface; X1P1Driver, A1Driver (Option A).

A ``PrinterDriver`` hides X1/P1 vs A1 model differences behind one interface. Per Option A
(docs/09-filament-change-protocol.md) we drive Bambu's **own** change routine over MQTT — we
NEVER author hotend gcode. The driver builds the request payloads; ``PrinterLink`` sends them.

⚠️ PHASE-0: the *exact* request payloads for unload / extrude / confirm-resume are the
load-bearing UNVERIFIED items for the v0.2 keystone spike (docs/09 UNVERIFIED #3, open
question #1). Every payload below is a best-guess **shape** marked ``# PHASE-0: verify`` — it
must be confirmed against a real printer before it can be trusted. We do not claim any of these
are confirmed.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ...transport import Report
from ...types import PauseReason
from ...utils import todo


@runtime_checkable
class PrinterDriver(Protocol):
    """Model-specific command builder. Option A: ride Bambu's existing change routine.

    Methods return the request payload (a dict) to be sent over the ``PrinterLink`` — keeping
    the driver pure/testable and the link responsible for the wire. The Printer owns sequencing
    and state; the driver only knows "what does an unload look like on *this* model".
    """

    model: str

    def request_unload(self) -> Report: ...
    def request_extrude(self) -> Report: ...
    def request_confirm_resume(self) -> Report: ...
    def request_start_print(self, remote_path: str) -> Report: ...

    def parse_pause_reason(self, report: Report) -> PauseReason: ...
    def parse_filament_present(self, report: Report) -> bool | None: ...


class X1P1Driver:
    """Driver for X1 / P1 series (first target). Routine payloads are PHASE-0 stubs.

    These printers share the LAN-MQTT ``device/{serial}/request`` command surface. The change
    routine we ride is the manual external-spool flow (docs/09): cancel-prompt → filament menu
    → swap → resume, expressed as gcode/command messages over MQTT.
    """

    model = "X1P1"

    # --- field-name guesses for the report stream (UNVERIFIED) -------------------------------
    # PHASE-0: verify — Bambu's report nests print state under a "print" key; the field names
    # below are the community-reported shapes, NOT confirmed by us (docs/09 UNVERIFIED #1/#2).
    _PRINT_KEY = "print"
    _STAGE_FIELD = "gcode_state"  # PHASE-0: verify — e.g. RUNNING/PAUSE/FINISH/FAILED strings
    _PAUSE_REASON_FIELD = "print_error"  # PHASE-0: verify — whether a change-pause is tagged here

    def request_unload(self) -> Report:
        """Build the 'unload old filament' command (Bambu's routine, not our gcode).

        PHASE-0: verify — the real envelope. Riding the manual flow likely means an
        ``M620`` / gcode_line push or the ``ams`` / ``unload_filament`` command verb; the
        line(s) below are placeholders only (docs/09 UNVERIFIED #3, open question #1).
        """
        # PHASE-0: verify — payload shape + verb. Do NOT trust until v0.2 confirms.
        return {
            "print": {
                "command": "gcode_line",  # PHASE-0: verify command verb
                "param": "M620 S255\n",  # PHASE-0: verify — external-spool unload trigger
            }
        }

    def request_extrude(self) -> Report:
        """Build the 'extrude / load new filament to nozzle' confirmation step.

        PHASE-0: verify — in the manual UI this is the "extrude more" / "filament loaded" tap;
        the MQTT equivalent verb + param are unconfirmed (docs/09 UNVERIFIED #3).
        """
        # PHASE-0: verify — payload shape + verb.
        return {
            "print": {
                "command": "gcode_line",  # PHASE-0: verify command verb
                "param": "M1020 S0\n",  # PHASE-0: verify — "which filament" select / extrude
            }
        }

    def request_confirm_resume(self) -> Report:
        """Build the 'confirm change done, resume print' command (the load-bearing gate).

        PHASE-0: verify — docs/09 stresses: if we can't resume over MQTT the print sits paused
        forever. The resume verb is unconfirmed; ``pause``/``resume`` print commands are the
        likely surface but must be confirmed (docs/09 UNVERIFIED #3).
        """
        # PHASE-0: verify — payload shape + verb.
        return {
            "print": {
                "command": "resume",  # PHASE-0: verify command verb for resume-after-change
            }
        }

    def request_start_print(self, remote_path: str) -> Report:
        """Build the 'start printing the uploaded file' command.

        PHASE-0: verify — the ``project_file`` / ``url`` / ``subtask`` field names and the
        path form (``ftp://`` vs ``/cache/...``) the printer expects (docs/03 FTPS; v0.2).
        """
        # PHASE-0: verify — payload shape + path form.
        return {
            "print": {
                "command": "project_file",  # PHASE-0: verify command verb
                "url": f"ftp://{remote_path}",  # PHASE-0: verify URL/path form
                "param": "Metadata/plate_1.gcode",  # PHASE-0: verify plate param
            }
        }

    def parse_pause_reason(self, report: Report) -> PauseReason:
        """Best-effort: classify a pause as CHANGE vs USER vs ERROR from the report.

        PHASE-0: verify — whether the live report distinguishes our tagged change-pause from a
        stray user pause at all (docs/09 UNVERIFIED #2). Until confirmed we surface UNKNOWN and
        let the Orchestrator validate against its own authored plan/tag, which is the
        single-brain-safe default.
        """
        print_blob = report.get(self._PRINT_KEY)
        if isinstance(print_blob, dict):
            # PHASE-0: verify — real field + values that mark a filament-change pause.
            reason = print_blob.get(self._PAUSE_REASON_FIELD)
            if reason in ("FILAMENT_RUNOUT", "FILAMENT_CHANGE"):  # PHASE-0: verify literals
                return PauseReason.CHANGE
        return PauseReason.UNKNOWN

    def parse_filament_present(self, report: Report) -> bool | None:
        """Read the printer's own filament-present sensor from the report, if present.

        Returns ``None`` when the report doesn't carry the sensor field (so the Printer leaves
        its cached value untouched on a delta that doesn't mention it).

        PHASE-0: verify — the real sensor field name/location. Whether the X1/P1 even exposes an
        external-spool present sensor over MQTT is a v0.2 spike question (docs/09 UNVERIFIED #2).
        """
        print_blob = report.get(self._PRINT_KEY)
        if isinstance(print_blob, dict):
            # PHASE-0: verify — field name for the present sensor (guess below).
            val = print_blob.get("filam_bak")  # PHASE-0: verify field name
            if isinstance(val, bool):
                return val
        return None


class A1Driver:
    """Driver for the A1 series (incl. A1 mini).

    READ path: confirmed live against an A1 mini on 2026-06-24 — the report nests state under
    ``print``; the toolhead filament-present switch is ``hw_switch_state`` (1 = present).

    WRITE path (unload / extrude / confirm-resume / start-print): still DEFERRED. The A1 /
    AMS-Lite feed path and change-routine differ from X1/P1 (docs/10 'Deferred / open' #10/#11);
    those payloads come after the change routine is proven on hardware. They raise until then.
    """

    model = "A1"

    _PRINT_KEY = "print"
    # Confirmed live (A1 mini, 2026-06-24): toolhead filament-present switch.
    _SENSOR_FIELD = "hw_switch_state"

    @todo("A1 feed path differs; build after X1/P1 is proven (PHASE-0, docs/10 #10/#11)")
    def request_unload(self) -> Report: ...

    @todo("PHASE-0, docs/10 #10/#11")
    def request_extrude(self) -> Report: ...

    @todo("PHASE-0, docs/10 #10/#11")
    def request_confirm_resume(self) -> Report: ...

    @todo("PHASE-0, docs/10 #10/#11")
    def request_start_print(self, remote_path: str) -> Report: ...

    def parse_pause_reason(self, report: Report) -> PauseReason:
        # PHASE-0: verify — how the A1 tags a filament-change pause vs a user pause. Until
        # confirmed we surface UNKNOWN and let the Orchestrator validate against its own plan
        # (single-brain-safe default).
        return PauseReason.UNKNOWN

    def parse_filament_present(self, report: Report) -> bool | None:
        """Toolhead filament-present switch — confirmed ``hw_switch_state`` (1=present).

        Returns ``None`` when this report/delta doesn't carry the field, so the Printer keeps
        its cached value.
        """
        print_blob = report.get(self._PRINT_KEY)
        if isinstance(print_blob, dict):
            val = print_blob.get(self._SENSOR_FIELD)
            if isinstance(val, bool):  # bool is an int subclass — check first
                return val
            if isinstance(val, int):
                return val != 0
            if isinstance(val, str) and val.strip().isdigit():
                return int(val) != 0
        return None


__all__ = ["A1Driver", "PrinterDriver", "X1P1Driver"]
