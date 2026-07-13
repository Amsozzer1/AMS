# AMS-X — Open Modular Filament System for Bambu Lab Printers

> An expandable, multi-printer Automatic Material System that breaks past the 16-slot
> ceiling of Bambu's stock AMS by driving the external-spool filament swap over **local
> MQTT** — no cloud, no proprietary AMS protocol.

Bambu Lab printers cap multi-material printing at the AMS's 4 slots (16 with the hub), and
every slot is locked to Bambu's hardware. AMS-X routes around that limit instead of fighting
it. The printer runs in its native **external-spool mode**, and a central server automates
exactly what a person would do by hand at each material change: retract the spent filament,
feed the next one until the printer's filament sensor trips, and resume the print. Because a
"slot" is just "a module the server can drive," capacity is unbounded — dozens of spools,
poolable across many printers.

The design documents are the source of truth for intent and rationale — start at
[docs/README.md](docs/README.md).

---

## How it works

AMS-X never authors hotend G-code. It drives Bambu's own filament-change routine over MQTT
and owns only the filament logistics up to the printer's sensor. This keeps a clean boundary:

| AMS-X owns — filament logistics | Bambu owns — hotend physics |
|---|---|
| Which module, when; retract spent filament clear of the shared path; feed the next filament to the printer's inlet/sensor | Temperature, retract-from-melt-zone, load-to-nozzle, purge, wipe, resume |

The swap is driven by a **hybrid trigger**: the server parses the uploaded sliced 3MF into an
ordered material-change *plan* (it is the source of truth for *what comes next*), while a live
MQTT pause event is the *trigger* for *when to act*. Because the server also authors the
change G-code, every planned pause is tagged — a stray user pause is handled as an exception,
never mistaken for a swap.

```
  PRINTING ──▶ PAUSE (MQTT) ──▶ UNLOAD current ──▶ SELECT next module ──▶ FEED
                                                                            │
     PRINTING ◀── LOAD + RESUME (MQTT) ◀── SENSE (filament sensor trips) ◀──┘
```

A **`Module`** is one interface with a swappable actuator behind it: today a `ManualModule`
prompts a human to perform the swap; a `HardwareModule` (motorized) drops into the same
contract later without touching the orchestrator.

---

## Architecture

A **single brain** is the only decision-making node. Every other part — the printer, the
modules, the future ESP32 cluster controllers — is a non-sentient actuator that acts and
reports; the brain handles every exception and is authoritative about which filament is loaded
where.

```
        ┌────────────────────────── Brain — single source of truth ──────────────────────────┐
        │  async Orchestrator · Printer state model · Job/3MF parser · Module registry         │
        │  MQTT broker (Mosquitto) · Inventory (Spoolman) · FastAPI + REST                      │
        └──────┬──────────────────────────┬───────────────────────────────────┬───────────────┘
  local MQTT + │ FTPS (LAN)    local MQTT │                          WiFi → MQTT │  (planned)
               ▼                          ▼                                      ▼
        Bambu printer               Operator UI                        ESP32 cluster controller
    (external-spool mode)       (Next.js dashboard)              one TMC2209 driver per module,
                                                                     one module moves at a time
```

The server is layered so dependencies point downward — orchestration → job → printer/module →
transport → inventory — with a small typed domain model at the core. The full class model is
documented in [docs/10-domain-model.md](docs/10-domain-model.md).

---

## Repository layout

This is a monorepo. Each area has its own README with deeper detail.

| Path | What it is |
|---|---|
| [server/](server/) | The Brain — Python (FastAPI + async orchestrator + MQTT). Package layout mirrors the domain model. |
| [frontend/](frontend/) | Operator UI — a thin Next.js/React client that talks only to the Brain's REST API. |
| [firmware/](firmware/) | ESP32 cluster-controller firmware (PlatformIO). Planned — Phase 1+ hardware track. |
| [hardware/](hardware/) | CAD, wiring, and BOM for the modules / hub / clusters. |
| [deploy/](deploy/) | Docker Compose for the CasaOS host (Brain + Mosquitto broker). |
| [docs/](docs/) | Design docs: vision, architecture, protocol, domain model, roadmap, hardware. |
| [spikes/](spikes/) | Throwaway hardware-verification scripts (MQTT control, 3MF parse, FTPS). Not shipped. |

---

## Tech stack

| Layer | Choices |
|---|---|
| **Server** | Python 3.11+, FastAPI, `asyncio`, paho-mqtt, Pydantic. Tooling: **uv** (env/deps), **Ruff** (lint + format), **ty** (types), **pytest**. |
| **Frontend** | Next.js 15 (App Router), React 19, TypeScript. No UI kit or data library — a hand-built design system and a tiny polling hook. |
| **Transport** | Local MQTT (TLS, LAN mode) for printer + cluster control; FTPS for LAN job upload; HTTP/REST for Spoolman inventory. |
| **Firmware** | ESP32 / Arduino via PlatformIO; TMC2209 stepper drivers (planned). |
| **Deploy** | Docker Compose on a CasaOS host — Brain plus a self-hosted Mosquitto broker. |

Rationale for each choice lives in [docs/03-tech-stack.md](docs/03-tech-stack.md).

---

## Running it locally

The server runs in **simulate mode by default** — a built-in printer, FTP, and inventory
simulator let the entire swap loop run end to end with no hardware.

**Brain (server):**

```bash
cd server
uv sync --extra dev          # create .venv + install deps
AMSX_PORT=9001 uv run amsx   # starts the API in simulate mode on :9001
```

**Operator UI (frontend):**

```bash
cd frontend
npm install
npm run dev                  # http://localhost:9000 (defaults to the Brain on :9001)
```

**Exercise the swap loop with no printer** — upload a sliced `.gcode.3mf` in the UI, confirm
the colour→module mapping, then drive the simulator through a swap:

```bash
curl -X POST 'http://127.0.0.1:9001/api/printers/{id}/sim/pause'          # raise a swap prompt
# press-and-hold "mark done" in the Action Console, then:
curl -X POST 'http://127.0.0.1:9001/api/printers/{id}/sim/sensor?present=true'  # resume
```

**Quality gates:**

```bash
cd server && uv run ruff check . && uv run ty check && uv run pytest
```

---

## Current status

Software-complete for v0; the protocol thesis is verified on real hardware; motorized module
hardware is the next physical build.

**Proven and built**

- **Protocol confirmed live on a real Bambu A1** over local MQTT: external-spool unload,
  resume, filament-sensor read, and external-filament read/write. The X1/P1 driver is
  implemented behind the same interface, with wire payloads pending on-hardware verification.
- **Full v0 orchestration loop**, end to end: parse a sliced 3MF → push it to the printer over
  FTPS → start the print → detect the pause over MQTT → prompt the operator (human-as-module)
  → sensor trips → resume — all from a job the server itself parsed and started.
- **Inventory**: Spoolman integration (soft-failing HTTP client), spool CRUD, a Bambu-Studio-
  style colour→module mapping/resolver, and automatic spool-weight consumption on finish.
- **Operator UI**: a live printer dashboard, 3MF job intake, the swap-loop status strip, and a
  hold-to-confirm "Action Console" for the human swap prompt.
- **Simulator-first**: the whole system runs standalone with no printer, backed by ~4,000
  lines of server code and 130+ tests.

**Not yet built** — the motorized `HardwareModule` and its ESP32 cluster firmware, the
N-module hub, and live X1/P1 verification. These are Phase 1+ on the roadmap.

The phased plan (riskiest assumption first; no hardware until the software thesis holds) is in
[docs/04-roadmap.md](docs/04-roadmap.md), with the concrete v0 build in
[docs/07-v0-plan.md](docs/07-v0-plan.md).

---

## Project conventions

- **Simulator-first development.** Orchestration is built and tested against a printer/MQTT
  simulator; real hardware is validated at explicit keystone spikes.
- **Loud stubs.** Every not-yet-implemented function is marked with an `@todo` decorator that
  fails loudly and is greppable in one place — never a silent placeholder. See
  [CLAUDE.md](CLAUDE.md).
- **Local-first and secret-safe.** The only secrets are printer access codes/serials; they
  stay out of git via `.gitignore` plus a **gitleaks** pre-commit hook. See
  [SECURITY.md](SECURITY.md).

---

## License

To be determined — tracked as open question #22 in
[docs/05-open-questions.md](docs/05-open-questions.md).
