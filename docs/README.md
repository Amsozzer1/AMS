# AMS-X — Open Modular Filament System for Bambu Lab Printers

> Working name. An expandable, multi-printer Automatic Material System that bypasses
> the 4-slot limit of Bambu's stock AMS by automating the "external spool" swap over MQTT.

## One paragraph

Bambu Lab printers cap multi-material printing at the stock AMS's 4 slots (and 4 AMS
units / 16 slots with the hub). **AMS-X** sidesteps that ceiling entirely. Instead of
speaking the proprietary AMS protocol, it runs the printer in **external-spool mode** and
automates what a human would otherwise do by hand: when the print pauses for a material
change, a central server retracts the spent filament back into its module and feeds the
next module's filament forward until the printer's filament sensor trips — then resumes
the print over MQTT. Each **module** is one motorized spool holder; modules are unbounded
(N slots), share a single physical path into the printer via a **hub/manifold**, and can
eventually be pooled across many printers (M modules × N printers) with **Spoolman** for
inventory.

## The documents

| Doc | What it covers |
|-----|----------------|
| [01-vision-and-scope.md](01-vision-and-scope.md) | The problem, the idea, goals, non-goals, success criteria |
| [02-architecture.md](02-architecture.md) | System components, the swap sequence, control planes, key assumptions |
| [03-tech-stack.md](03-tech-stack.md) | Languages, protocols, hardware, libraries — and why |
| [04-roadmap.md](04-roadmap.md) | Phased execution plan, starting with the MQTT-only spike |
| [05-open-questions.md](05-open-questions.md) | Unresolved decisions and assumptions to validate |
| [06-module-interface.md](06-module-interface.md) | The `Module` contract — one interface, human or motor behind it |
| [07-v0-plan.md](07-v0-plan.md) | Concrete, build-ready v0 — sub-steps, hardware on-ramp, gates |
| [08-hardware.md](08-hardware.md) | Full hardware shopping list — buy-now vs later, per-module BOM |
| [09-filament-change-protocol.md](09-filament-change-protocol.md) | How multicolor-no-AMS slicing works, the gcode encoding, and how #17 is resolved |
| [10-domain-model.md](10-domain-model.md) | The server's class/domain model — Brain, Printer, Job, Module, Orchestrator |

## Working rules

The rules Claude operates under. Indexed from [CLAUDE.md](../CLAUDE.md), loaded every session.

| Rule | What it covers |
|-----|----------------|
| [rules/00-user-decides.md](rules/00-user-decides.md) | ⛔ The user decides, Claude builds — nothing is acted on without explicit approval |
| [rules/01-separation-of-concerns.md](rules/01-separation-of-concerns.md) | ⛔ One job per file; depend on seams so decisions stay reversible |
| [rules/02-stubs.md](rules/02-stubs.md) | Unfinished work carries `@todo`, never a hand-written `NotImplementedError` |

## Server

| Doc | What it covers |
|-----|----------------|
| [server/00-architecture.md](server/00-architecture.md) | Package architecture — the layer stack, the `__init__`-as-door rule, where things live |
| [server/01-http-layer.md](server/01-http-layer.md) | `routes/`, views, `Depends`, typed errors, and the generated contract |

## Frontend

| Doc | What it covers |
|-----|----------------|
| [frontend/00-architecture.md](frontend/00-architecture.md) | Folder architecture — views, `_components`, `_helpers`, the index-as-door rule |
| [frontend/01-api-layer.md](frontend/01-api-layer.md) | The `api/` module, the transport seam, and generated types |

## Workflow

| Doc | What it covers |
|-----|----------------|
| [superpowers/README.md](superpowers/README.md) | The spec → plan → execute → archive loop, the pinned plugin, and the plan lifecycle |

## Locked decisions (so far)

1. **Target printers:** X1/P1 **and** A1 — via a printer-abstraction layer. X1/P1 first.
2. **Filament routing:** our **own per-printer hub** (a dumb buffer / Y-connector, *not*
   Bambu's AMS hub) — connect directly to the printer, one filament in the line at a time.
3. **Trigger model: hybrid** — server parses the **sliced 3MF** for the material-change
   **plan** (server = source of truth) and uses **live MQTT pause events** (`M400 U1`) as the
   trigger. Pauses are **validated against the plan** (we author tagged pauses); unmatched
   pauses are exceptions, never swaps.
4. **#17 resolved** — multicolor-no-AMS is a real workflow; the sliced 3MF (`plate_1.gcode`)
   encodes each change (`M400 U1`) and its filament index (`M1020 S<n>`). See
   [09](09-filament-change-protocol.md).
5. **Option A (LOCKED): ride Bambu's own change routine** — we never author hotend gcode.
   We own *filament logistics* up to the printer's sensor; Bambu owns *hotend physics*
   (temp/load/purge/resume) and we drive its routine over MQTT.
6. **Server owns the job** — user uploads a sliced 3MF; server parses, pushes over **LAN**,
   starts it, drives the swaps. No custom slicer (OrcaSlicer-headless only if input unsliced).
7. **Multi-printer** via our **own MQTT broker**; each printer is a class with
   full-state-on-connect + incremental delta updates.
8. **Brain hosts everything** — server, web UI, MQTT broker. **For now the brain is the
   user's existing CasaOS device** (Docker-native; no GPIO needed since modules are
   network devices over WiFi/MQTT). A Pi is an optional alternative, not required.
9. **Cluster control (DECIDED):** **ESP32 (or Pico W) per ~16 modules** over **WiFi → MQTT**
   (same bus as printers). One **TMC2209 driver per module**; **one module moves at a time**
   → cheap pins/power/heat. Wall-powered **24V**, no batteries.
10. **`Module` is one interface, swappable actuator** — `ManualModule` (human, v0) and
    `HardwareModule` (stepper + driver, later) honor the same contract. A module's job ends
    at "filament at the printer's sensor / removed past the hub."
11. **First milestone:** **MQTT control spike** (v0.2) — confirm no-AMS multicolor pauses,
    drive resume, read sensor. Then **v0: human-is-the-module** full loop.

## Status

📄 **Docs / design phase.** No application code is being written yet. Implementation
starts only when a specific piece is explicitly green-lit.
