#!/usr/bin/env python3
"""End-to-end check of the SHIPPED vt_tray code path against the live A1.

Unlike a1_vt_tray.py (which hand-built the payload), this drives the *production* methods —
`A1Driver.parse_external_filament` (read) and `A1Driver.request_set_external_filament` (write) —
to prove the wired code reads the base colour and sets the printer's external filament correctly.
Sets a distinctive test colour, reads it back through the driver, then restores the original.

    cd server && uv run python scripts/check_a1_vt_tray.py
"""

from __future__ import annotations

import json
import ssl
import threading
import time

import paho.mqtt.client as mqtt

from amsx.config import load_config
from amsx.printer.drivers import A1Driver

pc = load_config("config/ams.local.yaml").printers[0]
drv = A1Driver()
REQ = f"device/{pc.serial}/request"
REP = f"device/{pc.serial}/report"
TEST = "1BAF1B"  # distinctive green (6-hex), clearly not the white base

_vt: dict = {}
_lock = threading.Lock()


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
            _vt.update(blob["vt_tray"])


def _read() -> tuple[str | None, str | None]:
    """Force a fresh report and return (material, color_hex) via the PRODUCTION parser."""
    with _lock:
        _vt.clear()
    c.publish(REQ, json.dumps({"pushing": {"command": "pushall", "sequence_id": "1"}}))
    t0 = time.time()
    while time.time() - t0 < 8:
        with _lock:
            if "tray_color" in _vt:
                return drv.parse_external_filament({"print": {"vt_tray": dict(_vt)}})
        time.sleep(0.2)
    return None, None


c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
c.username_pw_set("bblp", pc.access_code)
c.tls_set(cert_reqs=ssl.CERT_NONE)
c.tls_insecure_set(True)
c.on_connect = _on_connect
c.on_message = _on_message
c.connect(pc.ip, 8883, 60)
c.loop_start()
time.sleep(1.5)

base_mat, base_col = _read()
print(f"READ (driver.parse_external_filament): material={base_mat} color={base_col}")
assert base_col, "could not read vt_tray base colour"

print(f"WRITE (driver.request_set_external_filament -> {TEST} green)…")
c.publish(REQ, json.dumps(drv.request_set_external_filament("PLA", TEST)))
time.sleep(2.5)
mat, col = _read()
print(f"READ-BACK: material={mat} color={col}")
ok = col == TEST

print(f"RESTORE -> {base_col}…")
c.publish(REQ, json.dumps(drv.request_set_external_filament(base_mat or "PLA", base_col)))
time.sleep(2.5)
fmat, fcol = _read()
print(f"RESTORED: material={fmat} color={fcol}")

c.loop_stop()
c.disconnect()
print("\n=== VERDICT ===")
print(
    "✓ Production vt_tray read+write path works end-to-end on the A1."
    if ok and fcol == base_col
    else f"✗ mismatch (wrote {TEST}, read {col}; restored {fcol} vs {base_col})"
)
