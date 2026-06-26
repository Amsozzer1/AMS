#!/usr/bin/env python3
"""Reverse-engineer the A1 external-spool (vt_tray) filament SET command — live.

READ is already confirmed: the printer reports `print.vt_tray` with `id=254`, `tray_type`,
`tray_color` (RRGGBBAA), `tray_info_idx`, nozzle temps. This tests the WRITE half — the
`ams_filament_setting` command (ams_id=255). BambuStudio uses `tray_id=254`; pybambu uses
`tray_id=0`. We send a distinctive TEST color and verify by reading `vt_tray.tray_color` back,
trying tray_id 254 first, then 0. The printer's ORIGINAL filament is restored at the end.

    cd server
    uv run python ../spikes/a1_vt_tray.py
"""

from __future__ import annotations

import json
import ssl
import threading
import time

import paho.mqtt.client as mqtt

from amsx.config import load_config

pc = load_config("config/ams.local.yaml").printers[0]
REQ = f"device/{pc.serial}/request"
REP = f"device/{pc.serial}/report"
TEST_COLOR = (
    "1BAF1BFF"  # a distinctive green (RRGGBBAA) — clearly not the white baseline
)

_latest: dict = {}
_lock = threading.Lock()
_seq = [1000]


def _next_seq() -> str:
    _seq[0] += 1
    return str(_seq[0])


def _on_connect(c, u, f, rc, p):
    c.subscribe(REP)


def _on_message(c, u, msg):
    try:
        r = json.loads(msg.payload)
    except ValueError:
        return
    blob = r.get("print")
    if isinstance(blob, dict) and isinstance(blob.get("vt_tray"), dict):
        with _lock:
            _latest.update(blob["vt_tray"])


def _client() -> mqtt.Client:
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    c.username_pw_set("bblp", pc.access_code)
    c.tls_set(cert_reqs=ssl.CERT_NONE)
    c.tls_insecure_set(True)
    c.on_connect = _on_connect
    c.on_message = _on_message
    c.connect(pc.ip, 8883, 60)
    c.loop_start()
    return c


def _pushall(c):
    c.publish(
        REQ, json.dumps({"pushing": {"command": "pushall", "sequence_id": _next_seq()}})
    )


def _read_vt(c, timeout=8.0):
    """Force a fresh report and return (tray_color, tray_type, tray_info_idx)."""
    with _lock:
        _latest.clear()
    _pushall(c)
    t0 = time.time()
    while time.time() - t0 < timeout:
        with _lock:
            if "tray_color" in _latest:
                return (
                    _latest.get("tray_color"),
                    _latest.get("tray_type"),
                    _latest.get("tray_info_idx"),
                )
        time.sleep(0.2)
    return None, None, None


def _set_filament(c, *, color, tray_id, ttype="PLA", idx="GFL04", tmin=190, tmax=240):
    payload = {
        "print": {
            "sequence_id": _next_seq(),
            "command": "ams_filament_setting",
            "ams_id": 255,
            "tray_id": tray_id,
            "slot_id": 0,
            "tray_info_idx": idx,
            "setting_id": "",
            "tray_color": color,
            "tray_type": ttype,
            "nozzle_temp_min": tmin,
            "nozzle_temp_max": tmax,
        }
    }
    c.publish(REQ, json.dumps(payload))


def _rgb(color: str | None) -> str | None:
    return color[:6].upper() if color else None


def main() -> int:
    print(f"vt_tray SET test on {pc.id} — {pc.ip}")
    c = _client()
    time.sleep(1.5)

    base_color, base_type, base_idx = _read_vt(c)
    print(f"baseline: color={base_color} type={base_type} idx={base_idx}")
    if base_color is None:
        print("could not read vt_tray — aborting")
        return 1

    worked = None
    for tray_id in (254, 0):
        print(
            f"\n--- sending ams_filament_setting color={TEST_COLOR} tray_id={tray_id} ---"
        )
        _set_filament(c, color=TEST_COLOR, tray_id=tray_id)
        time.sleep(2.5)
        got, _, _ = _read_vt(c)
        print(f"   read back: tray_color={got}")
        if _rgb(got) == _rgb(TEST_COLOR):
            print(f"   ✓ STUCK with tray_id={tray_id}")
            worked = tray_id
            break
        print(f"   ✗ did not change with tray_id={tray_id}")

    # Restore the original filament so we leave the printer as we found it.
    restore_id = worked if worked is not None else 254
    print(f"\n--- restoring original color={base_color} (tray_id={restore_id}) ---")
    _set_filament(
        c,
        color=base_color or "FFFFFFFF",
        tray_id=restore_id,
        ttype=base_type or "PLA",
        idx=base_idx or "GFL04",
    )
    time.sleep(2.5)
    final, ftype, _ = _read_vt(c)
    print(f"   restored: tray_color={final} type={ftype}")

    print("\n=== VERDICT ===")
    if worked is not None:
        print(
            f"ams_filament_setting WORKS on the A1 with ams_id=255, tray_id={worked}."
        )
    else:
        print("Neither tray_id 254 nor 0 changed vt_tray — needs more digging.")
    c.loop_stop()
    c.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
