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

    def parse_external_filament(self, report: Report) -> tuple[str | None, str | None]: ...
    def request_set_external_filament(
        self,
        material: str | None,
        color_hex: str | None,
        *,
        tray_info_idx: str = "GFL04",
        tmin: int = 190,
        tmax: int = 240,
    ) -> Report: ...


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

    def parse_external_filament(self, report: Report) -> tuple[str | None, str | None]:
        """X1/P1 does not expose vt_tray — returns (None, None) as a safe no-op."""
        return None, None

    def request_set_external_filament(
        self,
        material: str | None,
        color_hex: str | None,
        *,
        tray_info_idx: str = "GFL04",
        tmin: int = 190,
        tmax: int = 240,
    ) -> Report:
        """X1/P1 does not support ams_filament_setting via this path — returns empty payload."""
        return {"print": {}}


class A1Driver:
    """Driver for the A1 series (incl. A1 mini).

    READ path: confirmed live against an A1 mini on 2026-06-24 — the report nests state under
    ``print``; the toolhead filament-present switch is ``hw_switch_state`` (1 = present).

    WRITE path: ``unload_filament`` and ``resume`` are CONFIRMED live against the A1 mini on
    2026-06-25 (Bambu auto-heats the nozzle for the unload itself — we send the verb, never a
    temperature). ``request_start_print`` is still a CANDIDATE payload (v0.4 item), and
    ``request_extrude`` (raw ``M83``/``G1 E45``) is a clearly-labelled diagnostic fallback only.

    The envelope is the standard Bambu command form: a ``print`` object with a ``command`` and a
    monotonic ``sequence_id`` the printer echoes in its ack. Option A = ride Bambu's OWN routine
    (``unload_filament`` / ``resume``); ``request_extrude`` is the raw load gcode for when the
    closed sensor loop wants an explicit push.
    """

    model = "A1"

    _PRINT_KEY = "print"
    # Confirmed live (A1 mini, 2026-06-24): toolhead filament-present switch.
    _SENSOR_FIELD = "hw_switch_state"
    _VT_TRAY = "vt_tray"

    def __init__(self) -> None:
        self._seq = 0

    def _next_seq(self) -> str:
        self._seq += 1
        return str(self._seq)

    def _gcode(self, *lines: str) -> Report:
        """A ``gcode_line`` command carrying one or more raw gcode lines (newline-terminated)."""
        return {
            "print": {
                "sequence_id": self._next_seq(),
                "command": "gcode_line",
                "param": "".join(f"{ln}\n" for ln in lines),
            }
        }

    def request_unload(self) -> Report:
        """Ride Bambu's own unload routine (Option A) — CONFIRMED live A1 mini 2026-06-25.

        ``unload_filament`` is the confirmed command verb: the A1 mini honours it on an
        external-spool change and Bambu auto-heats the nozzle for the retract itself (we send
        only the verb — never a temperature or distance). No raw ``G1 E-100`` retract needed.
        """
        return {"print": {"sequence_id": self._next_seq(), "command": "unload_filament"}}

    def request_extrude(self) -> Report:
        """Load/grab the new filament toward the nozzle (raw gcode) — DIAGNOSTIC FALLBACK ONLY.

        PHASE-0: verify — this is NOT part of the confirmed Option-A loop. ``M83`` (relative
        extrusion) then ``G1 E45 F500`` (grab-and-feed value from the A1 manual-change gcode).
        ``M83`` matters: a bare ``G1 E45`` in the default absolute mode targets E-coordinate 45
        rather than pushing 45mm. Requires a HOT nozzle — firmware blocks cold extrusion. The
        confirmed v0 loop closes on the printer sensor + ``resume`` (Bambu loads/purges itself),
        so this raw push is the diagnostic fallback for when that closed loop wants an explicit
        nudge — keep it labelled and unverified.
        """
        return self._gcode("M83", "G1 E45 F500")

    def request_confirm_resume(self) -> Report:
        """Resume the paused print (the load-bearing gate) — CONFIRMED live A1 mini 2026-06-25.

        ``resume`` is the confirmed verb: after an external-spool change it lifts the pause and
        the print continues (this is the load-bearing gate from docs/09 — if it were wrong the
        print would sit paused forever; it does not).
        """
        return {"print": {"sequence_id": self._next_seq(), "command": "resume", "param": ""}}

    def request_start_print(self, remote_path: str) -> Report:
        """Build the 'start printing the FTPS-uploaded file' command (Bambu ``project_file``).

        ``remote_path`` is what ``FtpsClient.upload`` returns — ``/cache/<name>``. The A1 reads
        the print file off its **SD card**, addressed as ``file:///sdcard/cache/<name>`` — i.e.
        FTP's ``/cache`` IS the card's ``/sdcard/cache``. Sending ``ftp:///cache/<name>`` instead
        made the A1 mini fault with the MicroSD read/write exception (0500_C010) the instant the
        print started — the firmware couldn't resolve that to a card read (confirmed live
        2026-06-25; ground-truth ``print_error`` from the report). ``param`` is the plate gcode
        inside the .3mf zip; ``use_ams`` is false (external spool, no AMS).

        PHASE-0 (v0.4): the ``file:///sdcard/cache/`` url form matches the only confirmed-working
        A1 project_file example; the cali/inspect toggles are sensible defaults, not gospel.
        """
        name = remote_path.rsplit("/", 1)[-1]
        return {
            "print": {
                "sequence_id": self._next_seq(),
                "command": "project_file",
                "param": "Metadata/plate_1.gcode",  # plate gcode inside the .3mf zip
                # FTP /cache == the card's /sdcard/cache; the A1 prints from the card, not ftp://.
                "url": f"file:///sdcard{remote_path}",  # -> file:///sdcard/cache/<name>
                "plate_idx": 0,
                "subtask_name": name,
                "project_id": "0",  # "0" across the ids = a local/LAN print (no cloud project)
                "profile_id": "0",
                "task_id": "0",
                "subtask_id": "0",
                "md5": "",
                "timelapse": False,
                "bed_type": "auto",
                "bed_leveling": True,  # Bambu field spelling (American)
                "flow_cali": False,
                "vibration_cali": False,
                "layer_inspect": False,
                "ams_mapping": [],  # external spool — no AMS tray map (list, not "")
                "use_ams": False,  # external spool — never the AMS
            }
        }

    def parse_external_filament(self, report: Report) -> tuple[str | None, str | None]:
        """Read the external spool's material + colour from ``print.vt_tray`` — confirmed live.

        Returns ``(material, color_hex6)`` where ``color_hex6`` is the first 6 chars of
        ``tray_color`` uppercased (stripping the AA alpha byte Bambu appends).
        Returns ``(None, None)`` when the report doesn't carry ``vt_tray``.
        """
        blob = report.get(self._PRINT_KEY)
        vt = blob.get(self._VT_TRAY) if isinstance(blob, dict) else None
        if not isinstance(vt, dict):
            return None, None
        color = vt.get("tray_color")
        hex6 = color[:6].upper() if isinstance(color, str) and len(color) >= 6 else None
        return vt.get("tray_type"), hex6

    def request_set_external_filament(
        self,
        material: str | None,
        color_hex: str | None,
        *,
        tray_info_idx: str = "GFL04",
        tmin: int = 190,
        tmax: int = 240,
    ) -> Report:
        """Build the ``ams_filament_setting`` command to tell the printer what it now holds.

        Confirmed protocol (live A1 mini): ``ams_id=255, tray_id=254, slot_id=0`` addresses
        the external spool. ``tray_color`` is 8-char RRGGBBAA uppercase (we append ``"FF"``).
        """
        rgba = ((color_hex or "FFFFFF").upper()[:6]) + "FF"
        return {
            "print": {
                "sequence_id": self._next_seq(),
                "command": "ams_filament_setting",
                "ams_id": 255,
                "tray_id": 254,
                "slot_id": 0,
                "tray_info_idx": tray_info_idx,
                "setting_id": "",
                "tray_color": rgba,
                "tray_type": material or "PLA",
                "nozzle_temp_min": tmin,
                "nozzle_temp_max": tmax,
            }
        }

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
