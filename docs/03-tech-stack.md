# 03 — Tech Stack

> Proposed, not locked. Rationale given so we can argue each choice. Nothing here is built
> until a piece is explicitly green-lit.

## Guiding principles
- **De-risk software before hardware** — the keystone is MQTT control; pick tools that make
  the Phase 0 spike fast.
- **One language for the server** end-to-end where reasonable; reach for firmware-level
  tooling only at the module edge.
- **Lean on existing open source** (Bambu MQTT libs, Spoolman) instead of rebuilding.

## Central server

| Concern | Proposed choice | Why |
|---------|----------------|-----|
| Language | **Python 3.11+** | Fastest path for the MQTT spike; best ecosystem for Bambu (`bambulabs_api`, `paho-mqtt`), Spoolman has a REST API, easy on a Pi. |
| MQTT client | **paho-mqtt**, or a Bambu wrapper (`bambulabs-api` / `pybambu` as used by Home Assistant) | Local broker is TLS on 8883 with access-code auth; wrappers already model the report schema. |
| Multi-printer mgr | **Our own MQTT connection manager** (not Bambu cloud API) | Bambu's API won't hold multiple printers cleanly; we maintain a live connection per printer and full control. |
| Printer state | **Class per printer**: full-state-on-connect + incremental deltas | Pull everything once, then apply small updates from the report stream; front end reads cached state. |
| Orchestrator | **Plain async state machine** (`asyncio`) | The swap is a small, explicit state machine; no heavy framework needed in v1. |
| Job parser | **Sliced-3MF reader** — unzip → `Metadata/plate_1.gcode` → scan `M400 U1` + `M1020 S<n>` | Build the ordered material-change plan. See [09](09-filament-change-protocol.md). **No custom slicer.** |
| Slicing (fallback) | **OrcaSlicer headless**, self-hosted, only if needed | Open option if a future input isn't pre-sliced; not used unless required. |
| Job upload | **FTPS client** to the printer (LAN) | Push the sliced job locally, then start via MQTT. To confirm in Phase 0. |
| Config | **YAML/TOML** | Printer serials, access codes, module map, hub geometry. |
| Backend/API | **FastAPI** (+ websockets for live state) | Serves the UI, accepts the 3MF upload, streams printer state. |
| Front end | **Normal web SPA** — React/Svelte/Vue (TBD) | Live printer dashboard + Spoolman view + 3MF upload. **Not ComfyUI** — that's an AI image-gen node graph, wrong tool for this. |
| Process mgmt | **Docker containers** (server + Mosquitto broker) | Brain is the user's **CasaOS** box (Docker-native); a Pi w/ systemd is the alt. |
| Hosting | **Everything on the brain** — server, UI, MQTT broker (OrcaSlicer only if needed) | Brain = **CasaOS device** for now. No GPIO needed (modules are network devices). |
| Remote access | Optional **reverse proxy / tunnel** (e.g. ngrok / Cloudflare / Tailscale) | Local-first by default; user can expose a port if they want remote. |

Alternative considered: **Go** for the server (single static binary, great concurrency).
Rejected for v1 because Python gets the MQTT spike done faster and the Bambu library
support is richer. Revisit if performance/footprint ever matters.

## Printer interface

| Concern | Choice | Notes |
|---------|--------|-------|
| Transport | **Local MQTT** (LAN mode) | `device/{serial}/report` (in), `device/{serial}/request` (out). Avoids cloud dependency/latency. |
| Auth | Printer **access code** + serial, TLS | From the printer's network settings; LAN mode must be enabled. |
| Commands | `gcode_line` + structured `print`/`system` payloads | **Option A:** we drive Bambu's own change routine (unload/extrude/confirm/resume) — exact payloads are **Phase 0 deliverables to confirm**. |
| Abstraction | Per-family driver behind one interface | `X1P1Driver`, `A1Driver` → common `PrinterControl`. |

**Reality check:** the precise gcode/MQTT payloads for external-spool unload/load and the
exact field for the filament sensor are **assumptions to verify in Phase 0**, not settled
facts. The stack is chosen so that verification is cheap.

## Module hardware (when we get there)

| Concern | Leaning | Open |
|---------|---------|------|
| Motor | Stepper (NEMA 17; geared 28BYJ-48 only for bench *learning*) + BMG-style extruder | Torque/length sizing pinned at H1 |
| Driver | **TMC2209** (quiet, StallGuard jam-detect) — one per module | A4988 fallback; ULN2003 for the 28BYJ learning kit |
| Cluster controller | **ESP32** (or Pico W) per ~16 modules | Drives the cluster's drivers; talks to the brain |
| Module bus | **WiFi → MQTT to the brain's broker** (DECIDED) | Same bus as the printers; one comms model for everything. (Wired USB/serial or CAN/RS-485 remain fallbacks if WiFi proves flaky.) |
| Motion model | **One module moves at a time** → shared step/dir + per-module enable select | Cheap pins/power/heat; idle motors disabled |
| Filament sensor | Mechanical/optical presence at module exit (optional but wanted) | Part selection at H1 |
| Firmware | ESP32 firmware (Arduino / ESP-IDF / MicroPython); FluidNC is prior art | Decide at H1 |

**Why ESP32-over-MQTT (not a wired CAN/RS-485 bus):** clustering means **~1 controller per
16 modules**, so 30 modules ≈ 2 ESP32s — few enough that WiFi scale is a non-issue, and the
module clusters reuse the **exact MQTT bus the printers already use**. A power cable already
runs to each cluster (motors need 24V), so wireless removes the *data* cable specifically.
**Safe-failure:** ESP32 stops/holds on disconnect; brain pauses + alerts.

## Inventory (long term)
- **Spoolman** (existing open-source) over its **REST API**. Module↔spool mapping stored
  there or referenced from server config. No need to build inventory ourselves.

## Repo / tooling (proposed)
- Monorepo: `server/` (Python), `firmware/` (module MCU), `hardware/` (CAD/wiring),
  `docs/` (these files).
- `uv` or `poetry` for Python deps; `ruff` + `pytest`.
- Hardware-in-the-loop tests later; a **printer/MQTT simulator** early so the orchestrator
  can be developed without a printer always attached.

## What we are explicitly NOT adding
- No cloud backend / accounts — local-first.
- No custom slicer.
- No proprietary AMS protocol emulation.
