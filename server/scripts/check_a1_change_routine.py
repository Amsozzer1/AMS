#!/usr/bin/env python3
"""v0.2 keystone spike — drive the A1 filament-change routine on the REAL printer.

This is the make-or-break live check (docs/09 UNVERIFIED #3): can we unload / load / resume an
external-spool color change over local MQTT? It connects to the real printer from
``server/config/ams.local.json`` (the A1 mini "Bedroom"), streams its live report, and lets you
fire each change command ONE AT A TIME with a confirmation — so you watch the printer and record
what actually happens. It calls the real ``Printer`` + ``A1Driver`` utilities (Option A: ride
Bambu's own routine), so a "PASS" here is a payload we can trust and the @todo notes come off.

THROWAWAY: discovery only (docs/07 principle 2). Once a command is confirmed, the *finding*
already lives in ``A1Driver``; this script does not ship.

Option A — let Bambu do the work. The PRIMARY path (unload_filament / resume) hands heating,
target temps, retract/load distances, and purge to Bambu's own routine, per the filament profile
on the printer. We send a command verb; Bambu owns the thermals. In the real money-shot the print
is already running at the M400 U1 pause, so the nozzle is ALREADY hot — we never send heat.

The raw-gcode options (heat / G1 E-100 / G1 E45) are a DIAGNOSTIC FALLBACK only, for the open
question of whether the external-spool A1 honours Bambu's verbs the same as an AMS printer. Raw
`G1 E` bypasses Bambu and the firmware blocks cold extrusion, which is the ONLY reason a heat
step exists here. If the primary verbs work, the fallback (and heating) goes away entirely.

SAFETY — this physically actuates a real printer:
  * The extruder motor WILL move (and the nozzle WILL heat if you use the fallback). Stay at the
    printer; keep clear.
  * `resume` / `unload_filament` only make sense while the printer is paused mid-print.
  * Every action prints the exact JSON and asks y/N before sending. Nothing fires on its own.

Run it from the server venv (has amsx + paho):

    cd server
    uv run python scripts/check_a1_change_routine.py
    uv run python scripts/check_a1_change_routine.py --printer Bedroom
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from amsx.apps.printer import Printer
from amsx.apps.printer.drivers import A1Driver
from amsx.config import load_config
from amsx.events import EventBus, FaultEvent, PauseEvent, SensorEvent
from amsx.system.infra.mqtt import MqttBus, MqttPrinterLink

REPO = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO / "server" / "config" / "ams.local.json"


def _status_line(printer: Printer) -> str:
    p = printer.state.raw.get("print", {}) if isinstance(printer.state.raw, dict) else {}
    p = p if isinstance(p, dict) else {}
    return (
        f"stage={printer.state.stage} "
        f"gcode_state={p.get('gcode_state')} "
        f"layer={p.get('layer_num')} line={p.get('mc_print_line_number')} "  # #17 guard fields
        f"nozzle={p.get('nozzle_temper')}/{p.get('nozzle_target_temper')}C "
        f"bed={p.get('bed_temper')}C "
        f"filament_present={printer.state.filament_sensor}"
    )


async def _ask(prompt: str) -> str:
    return (await asyncio.to_thread(input, prompt)).strip()


async def _confirm_send(link: MqttPrinterLink, label: str, payload: dict) -> None:
    print(f"\n  → {label}")
    print(f"    topic:   {link.request_topic}")
    print(f"    payload: {json.dumps(payload)}")
    if (await _ask("    send this? [y/N] ")).lower() == "y":
        await link.request(payload)
        print("    sent. watch the printer + the report stream above.")
    else:
        print("    skipped.")


MENU = """
  ── A1 change-routine spike ───────────────────────────────────
   PRIMARY — Option A (Bambu owns heating / temps / distances / purge):
     1) refresh state (pushall)
     3) UNLOAD via Bambu routine     [routine_unload  -> unload_filament]
     6) RESUME print                 [routine_confirm_resume -> resume]
     7) PAUSE print
   DIAGNOSTIC FALLBACK — only if 3/6 are no-ops on external spool. Raw gcode
   bypasses Bambu, so you MUST heat first (the only reason heat is here):
     2) heat nozzle (M104 S<t>)
     4) UNLOAD raw  (G1 E-5; G1 E-100)
     5) LOAD  raw   (G1 E45)         [routine_extrude]
     8) raw gcode_line (free text)
     9) watch live status for N seconds
     0) quit
  ──────────────────────────────────────────────────────────────"""


async def run(config_path: Path, printer_id: str | None) -> int:
    cfg = load_config(config_path)
    if not cfg.printers:
        print(f"no printers in {config_path}")
        return 1
    pc = next((p for p in cfg.printers if p.id == printer_id), cfg.printers[0])
    print(f"connecting to {pc.id} ({pc.model}) at {pc.ip}:8883 …")

    bus = MqttBus(host=pc.ip, port=8883)
    try:
        bus.connect(access_code=pc.access_code)
    except Exception as exc:
        print(f"  MQTT connect FAILED: {exc}")
        print("  check: printer on, LAN mode on, access code correct, same network.")
        return 1

    link = MqttPrinterLink(bus, pc.id, pc.serial)
    driver = A1Driver()
    events = EventBus()
    printer = Printer(pc.id, link, driver, events)

    async def on_pause(e: PauseEvent) -> None:
        print(f"\n  [EVENT] PAUSE  reason={e.reason} tag={e.tag} layer={e.layer}")

    async def on_sensor(e: SensorEvent) -> None:
        print(f"\n  [EVENT] SENSOR filament_present={e.filament_present}")

    async def on_fault(e: FaultEvent) -> None:
        print(f"\n  [EVENT] FAULT  {e.source}: {e.detail}")

    events.subscribe(PauseEvent, on_pause)
    events.subscribe(SensorEvent, on_sensor)
    events.subscribe(FaultEvent, on_fault)

    await printer.connect()  # registers report handler + requests the full state (pushall)
    await asyncio.sleep(1.5)  # let the first full report land
    print("connected. " + _status_line(printer))

    try:
        while True:
            print(MENU)
            choice = await _ask("  choice: ")
            if choice == "0":
                break
            elif choice == "1":
                await printer.connect()  # re-request pushall
                await asyncio.sleep(1.0)
                print("  " + _status_line(printer))
            elif choice == "2":
                t = await _ask("  nozzle target °C [220]: ") or "220"
                await _confirm_send(link, f"heat nozzle to {t}C", driver._gcode(f"M104 S{t}"))
            elif choice == "3":
                await _confirm_send(link, "UNLOAD (Bambu routine)", driver.request_unload())
            elif choice == "4":
                await _confirm_send(
                    link,
                    "UNLOAD (raw retract)",
                    driver._gcode("G1 E-5 F1000", "G1 E-100 F1000"),
                )
            elif choice == "5":
                await _confirm_send(link, "LOAD (raw extrude)", driver.request_extrude())
            elif choice == "6":
                await _confirm_send(link, "RESUME print", driver.request_confirm_resume())
            elif choice == "7":
                pause = {"print": {"sequence_id": "0", "command": "pause", "param": ""}}
                await _confirm_send(link, "PAUSE print", pause)
            elif choice == "8":
                g = await _ask("  gcode (e.g. M109 S220): ")
                if g:
                    await _confirm_send(link, f"gcode_line {g!r}", driver._gcode(g))
            elif choice == "9":
                secs = int(await _ask("  watch seconds [10]: ") or "10")
                for _ in range(secs):
                    print("  " + _status_line(printer))
                    await asyncio.sleep(1.0)
            else:
                print("  ?")
    finally:
        bus.disconnect()
        print("\ndisconnected.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Drive the A1 change routine on the real printer.")
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help=f"default {DEFAULT_CONFIG}")
    ap.add_argument("--printer", default=None, help="printer id (default: first in config)")
    args = ap.parse_args()
    raise SystemExit(asyncio.run(run(args.config, args.printer)))
