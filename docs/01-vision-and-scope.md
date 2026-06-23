# 01 — Vision & Scope

## The problem

Bambu Lab printers are excellent, but their multi-material story is closed and capped:

- The stock **AMS holds 4 spools**. With the AMS Hub you can chain up to **4 units (16
  slots)** — and that's the ceiling.
- Adding capacity means buying more proprietary AMS units; the system is **logged behind
  Bambu's own AMS firmware/protocol**.
- For anyone running a print farm or doing high-color / many-material work, 16 slots is
  limiting, and every slot is locked to Bambu's hardware and pricing.

There is no official path to "I have 30 spools on a shelf and any of them can feed any of
my printers."

## The idea

Don't fight Bambu's AMS protocol — **route around it.**

Bambu printers can already print from an **external spool** (no AMS), using their built-in
**filament-present sensor** at the toolhead/extruder. A human running external-spool
multi-color simply swaps filament by hand at each pause. **AMS-X automates that human.**

- Each spool sits in a **module** with a stepper motor that can **feed** filament toward
  the printer or **retract** it back onto the module.
- A **central server** (Raspberry Pi class) watches the printer over **MQTT**. When the
  print pauses for a material change, the server:
  1. commands the printer/active module to **unload** (retract spent filament clear of the
     shared path),
  2. commands the **next module to feed** its filament forward,
  3. waits for the printer's **filament sensor** to detect presence,
  4. sends the **load / resume** command over MQTT, and printing continues.
- Because "a slot" is just "a module the server can drive," the system is **expandable to
  N modules** — far past 16.

## Why this works (the thesis)

> Anything a person can do to an external-spool Bambu print by hand at a pause, a server +
> a motor + a sensor handshake can do automatically and repeatably.

The entire project lives or dies on whether the printer's **unload / load / resume** and
**filament-sensor state** are controllable/observable over MQTT. That's why **Phase 0 is a
pure MQTT spike** before any hardware exists (see [04-roadmap.md](04-roadmap.md)).

## Goals

**v1 (prove the thesis)**
- Automate a single end-to-end material swap on one printer, server-driven, over MQTT.
- Printer-abstraction layer so X1/P1 and A1 can be added without rewrites.

**v2 (make it a system)**
- N modules feeding one printer through a shared hub/manifold.
- Reliable swap orchestration driven by live MQTT pause events.
- Per-module addressing, homing, jam/feed detection.

**Long term**
- **Spoolman integration** — every module maps to a tracked spool; inventory, material
  type, remaining weight, and pick logic live there.
- **Shelf-scale storage** — e.g. an IKEA unit holding ~30 modules.
- **M modules × N printers** — a shared filament pool any printer in the farm can draw from.

## Non-goals (for now)

- Reverse-engineering or emulating Bambu's proprietary AMS protocol. We use external-spool
  mode on purpose.
- Replacing the slicer or its tool-change logic. We rely on the slicer to insert pauses at
  material changes.
- A polished consumer product / enclosure design. v1 is a functional rig.
- Closed-loop color calibration, purge optimization, etc. — downstream concerns.

## Success criteria

| Milestone | "Done" looks like |
|-----------|-------------------|
| Phase 0 (MQTT spike) | From a laptop, trigger unload → load on a real printer and read the filament-present sensor state changing — no hardware. |
| v1 | One motorized module + server completes one unattended material swap mid-print. |
| v2 | A multi-color print with ≥3 distinct modules completes unattended through the hub. |
| Long term | A print pulls a material the server *selected from Spoolman inventory*, across more than one printer. |

## Naming

"AMS-X" is a placeholder (X = eXpandable / eXternal). Open to a real name later; doesn't
affect design.
