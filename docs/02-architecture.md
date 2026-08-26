# 02 — Architecture

## System at a glance

```
                    ┌────────────────────────────────────────────────┐
                    │     Brain (Pi, or any always-on host)          │
                    │                                                 │
 Spoolman (later) ◄►│ Orchestrator ─ Printer Abstraction ─ MQTT Broker│
                    └────────┬───────────────┬────────────────┬───────┘
                             │ MQTT (WiFi)    │ MQTT (TLS,LAN) │ MQTT (WiFi)
                             ▼                ▼                ▼
                   [ESP32 cluster ctrl] [Bambu Printer]  [ESP32 cluster ctrl]
                      │ step/dir+enable        ▲              │
              ┌───────┼───────┐                │       ┌──────┼──────┐
              ▼       ▼       ▼                │       ▼      ▼      ▼
           [drv+mot][drv+mot]… (×16)           │     (more modules…)
              │       │       │                │
            [Module][Module]…                  │
              └───────┴────┬──────┘            │
                           ▼                   │
                     [ HUB (Y-connector) ]==PTFE==► printer external input
                     one filament in the line at a time
```
*Everything — printers AND module clusters — speaks **MQTT to the brain's broker**. One bus.*

## Core design principle — the single brain

**The Raspberry Pi is the only "sentient" node in the system.** Every other part —
modules, hub, even the printer — is a **non-sentient actuator/reporter** that does exactly
what it's told.

- Modules and printers may **throw an error/status back** to the Pi, but they never *decide*
  anything. The Pi **handles every exception** and owns every decision.
- The Pi is the **single source of truth.** Notably, the Pi is authoritative about **which
  filament is currently loaded into each printer.** The printer *reports* its state, but its
  report is **not** the source of truth — the Pi reconciles it against what it knows it did.
- This keeps all logic in one place (testable, swappable actuators) and means hardware can
  stay dumb and cheap.

## Core design principle — Option A: ride the printer's own change routine (LOCKED)

We **never author custom hotend gcode.** We use Bambu's existing manual external-spool
filament-change flow and automate the human steps over MQTT. Full detail and the gcode
encoding are in [09-filament-change-protocol.md](09-filament-change-protocol.md). The
boundary this creates:

| **We own — filament logistics** | **Bambu owns — hotend physics** |
|---|---|
| Remove old filament past the hub; feed the right new filament to the printer's entry/sensor; pick which module, when | Temperature, retract-from-melt-zone, load-to-nozzle, purge, wipe, reposition, resume |

**A module's job literally ends at "filament present at the printer's sensor / removed past
the hub."** Temperature, purge, and nozzles never cross that boundary. *Cost we accept:* we
depend on Bambu's routine existing and being drivable over MQTT (a v0.2 spike item).

## Components

### 1. Module (one per spool)
The atomic unit. "A slot" = "a module the server can drive."
- Holds one spool.
- **Stepper motor + drive gear** to feed filament toward the hub or retract onto the spool.
- Short PTFE lead from the module to the hub.
- (Likely) a **filament-present / motion sensor** at the module exit so the server knows
  filament actually moved and cleared the module.
- Has an **address** on the module bus so the server can target it individually.
- *Detailed mechanical design is deferred — see [05-open-questions.md](05-open-questions.md).*

**Module is an interface, not (yet) hardware.** The server talks to a `Module` **class**;
the actuator behind it is swappable:
- **`ManualModule`** (v0) — fulfilled by a **human**. The server fires a request event and a
  person performs the feed/retract. *No hardware exists yet — this is how v0 runs.*
- **`HardwareModule`** (Phase 1+) — a real motor implementing the **same** contract.

The orchestrator only knows the `Module` interface, so v0 → Phase 1 is a drop-in swap of
the implementation. *The detailed `Module` interface is the next design artifact to draft.*

### 2. Hub (our own per-printer buffer — NOT Bambu's AMS hub)
One hub **per printer**. We connect **directly to the printer**, bypassing Bambu's AMS hub
entirely. Our hub's only job: **ensure one filament is in the line at a time** — it's a
merge/buffer point, not a smart device.
- Can be trivially passive: e.g. a **Y-connector** (N PTFE leads in → 1 PTFE out → printer).
  For 2 modules it's literally a wye fitting.
- **Load-bearing assumption:** a full retract of the active module clears the shared line
  before the next module feeds, so two filaments never collide. *Low-stakes / deferred —
  if it ever bites, the fix is the optional cutter below, not a hub redesign.*
- A mechanical *selector* was considered and rejected for v1 — keep the hub dumb.

### 2b. Optional cutter (deferred — only if clean-tip becomes a real problem)
Not in initial scope. If retract/tip quality causes jams:
- A small cutter makes a **clean cut**, triggered **only** when retract is troublesome.
- Recovery routine: full retract → confirm printer drained → heat extruder → purge what we
  can → feed next clean filament.
- Vision (YOLO on the camera feed) is a far-future maybe; user-alert is the cheap fallback.

### 3. Central server (Raspberry Pi class) — the source of truth
The brain. It **owns the job**: the user uploads a 3MF to the server, the server parses it
to learn the material-change plan, **pushes the job to the printer over LAN**, starts it,
and then drives the swaps. Because the server sent the file, the server knows the file.

Logical pieces:

- **MQTT connection manager** — our **own** MQTT setup (not Bambu's cloud API, which won't
  hold multiple printers cleanly). Maintains a live connection to **every** printer.
- **Printer state model** — each printer is a **class instance**: starts empty → on connect
  **pulls full state once** → then applies **incremental delta updates** from the report
  stream. Front end reads this cached state; we never need to poll-refresh everything. The
  Pi also tracks **what filament it loaded** into the printer as the authoritative record;
  the printer's own report is cross-checked against it, not trusted blindly.
- **Printer abstraction** — hides X1/P1 vs A1 differences behind one seam, `PrinterControl`:
  `routine_unload()`, `routine_extrude()`, `routine_confirm_resume()`, `filament_present()`,
  `loaded_filament`, plus `send_job(file)` / `start_print(path)`. The orchestrator is typed
  against this seam, never the concrete `Printer` — see [10-domain-model.md](10-domain-model.md).
- **Job parser** — unzips a **sliced 3MF**, reads `Metadata/plate_1.gcode`, and builds the
  ordered **material-change plan** (each `M400 U1` pause + its `M1020 S<n>` filament index).
  See [09-filament-change-protocol.md](09-filament-change-protocol.md). No custom slicer;
  OrcaSlicer-headless only if an unsliced input ever needs slicing.
- **File push (LAN)** — uploads the sliced job to the printer locally (Bambu cloud is not
  used in LAN mode) and starts the print via MQTT. **We control the "Change filament G-code"
  preset, so we inject tagged/numbered pauses** the server can later recognize as its own.
- **Module bus driver** — sends high-level commands ("feed / retract / stop") to **ESP32
  cluster controllers** over MQTT; each ESP32 drives several module drivers (below).
- **Orchestrator** — the state machine that ties the parsed plan + live printer events to
  module actions (below).
- **Front end** — web UI showing live printer state + Spoolman inventory, and the upload
  point for the 3MF. (Note: *ComfyUI is not the right tool here — it's a node graph for AI
  image generation; we want a normal web frontend.* See [03-tech-stack.md](03-tech-stack.md).)

### 4. Cluster controller (ESP32, one per ~16 modules)
The hands of the brain. Modules don't each have a brain; a cluster shares one.
- An **ESP32** (or Pico W) per cluster, connected to the brain over **WiFi via MQTT** — the
  *same* bus the printers use. No USB tether; brain can be any always-on host.
- Drives the cluster's **TMC2209 driver per module** (one driver per motor).
- **One module moves at a time** (shared-line rule), so the controller uses a shared
  step/dir bus + per-module **enable** select — cheap on pins, power, and heat. Idle modules
  are **disabled** (de-energized).
- Non-sentient: it executes "feed/retract/stop" and reports back; the Pi decides everything.
- **Safe-failure:** on lost connection it **stops and holds**; the brain detects the dropout
  and **pauses the print + alerts**. (Few WiFi nodes total — ~1 ESP32 per 16 modules.)

### 5. Spoolman (later)
External open-source inventory service. Maps module ↔ spool, tracks material/weight,
and answers "which module holds the material this swap needs?"

## The swap sequence (the heart of the system)

**Hybrid model:** the **plan** (what material comes next, and in what order) comes from the
**server's parse of the 3MF**; the **trigger** ("act now") comes from a **live MQTT pause
event** (the `M400 U1` pause). Server knows *what*; printer tells it *when*.

**Pause validation (don't trust raw pauses):** the server only acts on a pause it can
**match to its own plan** — and because we authored the change-gcode, our pauses are
tagged/numbered. A random *user* pause carries no tag → handled as an exception (hold +
alert), never a swap. A state machine owns "am I mid-swap" so stray events can't
double-trigger. Detail in [09-filament-change-protocol.md](09-filament-change-protocol.md).

**Resume state is the printer's job (Option A):** steps 3 & 7 below are us *driving Bambu's
own change routine* over MQTT, not us managing temperature/purge. Our actions end at the
printer's sensor; Bambu handles load-to-nozzle, purge, and resume.

```
1. PRINTING                 server idle-watching MQTT report stream
        │
2. PAUSE  ◄── printer reports filament-change / pause over MQTT
        │
3. UNLOAD current
        ├─ printer: retract/unload command (external-spool) over MQTT
        └─ active module: retract filament onto spool until module sensor clears
                          AND shared hub line is clear   ◄── critical gate
        │
4. SELECT next module       (from the parsed 3MF plan; later: Spoolman material match)
        │
5. FEED next
        └─ next module: feed forward through hub → printer inlet
        │
6. SENSE                    poll printer filament-present sensor over MQTT
        ├─ tripped  → continue
        └─ timeout  → error / retry / alert  ◄── failure handling
        │
7. LOAD + RESUME
        └─ printer: load + resume print over MQTT
        │
8. PRINTING                 back to step 1
```

### Why hybrid (parse for the plan, MQTT for the trigger)
- **Plan from 3MF:** the server parses the uploaded file, so it knows the full material-
  change sequence ahead of time and can pick the right module (and later pre-stage / match
  by Spoolman material). The server is the source of truth.
- **Trigger from MQTT:** the printer remains the authority on *when* a pause actually
  happens, so we don't have to predict Z-height/line timing or stay perfectly in sync with
  progress.
- We rely on the slicer to insert the pauses at tool changes; we do **not** build our own
  slicer. Server only *reads* the file.
- Open: whether the MQTT pause carries any "which filament" hint, or whether the plan's
  ordering alone maps each pause → the correct module (see open question #17).

## Control planes

| Plane | Transport | Direction | Carries |
|-------|-----------|-----------|---------|
| Printer control | **MQTT** (local broker, TLS, access code) | server ⇄ printer | status/report in; gcode/commands out |
| Job upload | **LAN file transfer** (e.g. FTPS on the printer) | server → printer | the sliced 3MF job before starting a print |
| Module control | **module bus** (TBD: CAN / RS-485 / I²C / GPIO step-dir) | server → modules | feed/retract length, home, addressing |
| Module feedback | same bus | modules → server | sensor state, motion confirm, faults |
| Inventory (later) | HTTP/REST | server ⇄ Spoolman | spool ↔ module map, material, weight |

## Key assumptions (must hold; validated in Phase 0 / early v1)

1. **MQTT can drive external-spool unload / load / resume** on the target printer.
2. **MQTT exposes the filament-present sensor state** in the report stream.
3. **A pause/filament-change event is observable** over MQTT in real time.
4. **A full module retract clears the shared hub line** before the next feed.
5. **The printer tolerates the swap timing** (won't fault/cancel while the server works).

6. **The server can push the job to the printer over LAN** (file transfer) and start it.
7. **The 3MF is parseable** into a reliable material-change plan without our own slicer.

Assumptions 1–3 are exactly what the Phase 0 spike exists to confirm. If any of 1–3 fail,
the approach needs rethinking before any hardware is built. 6–7 are software-only and can
be validated alongside Phase 0.

## Failure modes to design for (later)
- Feed succeeds at module but filament never reaches the printer sensor (jam in hub).
- Retract incomplete → collision on next feed.
- Printer cancels/faults mid-swap.
- Server ↔ printer MQTT disconnect during a swap.
- Wrong module fed (inventory mismatch).
