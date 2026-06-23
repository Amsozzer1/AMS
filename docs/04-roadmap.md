# 04 — Roadmap & Execution

Phased so the **riskiest assumption is tested first** and **no hardware is built until the
software thesis holds**. Each phase has an explicit exit gate.

---

## Phase 0 — MQTT control spike  ⟵ *first milestone, no hardware*

**Goal:** prove the keystone assumptions from a laptop against a real printer.

- Connect to the printer's **local MQTT** broker (LAN mode, serial + access code, TLS).
- Read and decode the **report stream**; locate the **filament-present sensor** field and
  watch it change when filament is inserted/removed by hand.
- Trigger an **unload** and a **load/resume** of the **external spool** over MQTT and
  observe the printer obey.
- Observe a **pause / filament-change** event appear in the stream during a real print.

**Exit gate (go/no-go for the whole project):**
> From a script, we can (a) read the filament sensor state changing, (b) command
> unload→load, and (c) detect a pause event — all over MQTT.

If this fails, stop and redesign before spending on hardware.

**Deliverables:** a throwaway spike script + a written **MQTT command/field reference**
(actual payloads that worked) feeding into the printer-abstraction design.

**Parallel software (no hardware, can run alongside Phase 0):**
- **3MF parse spike** — open a sliced 3MF and extract the material-change sequence.
- **LAN job push spike** — upload a sliced job to the printer (FTPS) and start it via MQTT.
- **Multi-printer state model** — printer-as-class: full-state-on-connect + incremental
  deltas, tested against one real printer's report stream.

---

## Phase 0.5 — v0: "human is the module"  ⟵ *full loop, still no hardware*

**Goal:** prove the **whole orchestration loop** end-to-end with a human standing in for the
module hardware. This validates the event model and the `Module` interface before we build
any motor.

- Server **loads a job**, **starts the print**, and watches it over MQTT.
- Print **stops at a material change**; printer **auto-ejects** the filament.
- Server **fires an event**: "module *k* is requested to do *Y*" (retract / feed).
- A **`Module` class** exists in software, fulfilled by a **`ManualModule`** implementation
  — i.e. it prompts the **human**, who physically swaps the filament.
- Human feeds the new filament → **printer sensor trips** → server **resumes** the print.

**Key design artifact:** the **`Module` interface** (same contract for `ManualModule` now
and `HardwareModule` later). *To be drafted as a design doc next — see note below.*

**Exit gate:** with a human as the module, the server drives a real multi-color print
through ≥1 material change unattended-except-for-the-human-swap.

**This phase is broken into concrete, build-ready sub-steps (v0.0–v0.6) with a parallel
hardware on-ramp in → [07-v0-plan.md](07-v0-plan.md).**

---

## Phase 1 — One real module, one swap

**Goal:** drop a motor in where the human stood — **same `Module` interface**, new
`HardwareModule` implementation.

- Single motorized **module** (likely Pi-GPIO/step-dir direct, or one RP2040 — skip the
  bus for now). `HardwareModule` implements the interface validated in v0.
- Orchestrator unchanged from v0 — it only knows the `Module` interface, not the actuator.
- Direct module → printer path (hub optional/trivial with one module).

**Exit gate:** one unattended material swap mid-print completes reliably (retract → feed →
sensor → resume) ≥ N times in a row.

---

## Phase 2 — N modules + hub

**Goal:** turn it into a real multi-material system.

- **Hub/manifold** with multiple module leads into one PTFE path.
- **Module bus** (CAN or RS-485) + per-module addressing, homing, jam/feed detection.
- Validate the **"full retract clears the shared line"** assumption under real conditions.
- Orchestrator handles **module selection** (still fixed-order or simple mapping).
- **Failure handling**: feed timeout, incomplete retract, mid-swap fault, MQTT drop.

**Exit gate:** a multi-color print using **≥3 modules** completes unattended through the hub.

---

## Phase 3 — Printer abstraction breadth (A1)

**Goal:** deliver on the "mix/both" decision.

- Implement the **A1 driver** behind the same interface.
- Resolve the **A1 hub-less push-feed** tension (see open questions) — A1 may need a
  different feed topology than the X1/P1 hub.

**Exit gate:** the same orchestrator drives a swap on both an X1/P1 and an A1.

---

## Phase 4 — Inventory (Spoolman)

**Goal:** modules become tracked, selectable inventory.

- Integrate **Spoolman** over REST; map **module ↔ spool**.
- Orchestrator **selects the module** holding the material the swap needs (not fixed order).
- Track remaining weight / material type; surface low-filament warnings.

**Exit gate:** a print pulls a material the server **chose from Spoolman**, not a hard-coded slot.

---

## Phase 5 — Scale: shelf + M×N

**Goal:** the long-term vision.

- **Shelf-scale** storage (e.g. ~30 modules in an IKEA unit) on the module bus.
- **Pool sharing:** M modules serving **N printers** — routing/arbitration so a module
  feeds whichever printer needs it (mechanical routing here is a hard, separate problem).
- Web UI for inventory, module map, manual control, swap history.

**Exit gate:** more than one printer draws from the shared module pool in one session.

---

## Sequencing principles
- **Software before hardware**; **one before many**; **X1/P1 before A1**; **fixed-order
  before inventory-driven**; **one printer before many**.
- Every phase ends in a **demonstrable, unattended capability**, not just code.
- Keep a **printer/MQTT simulator** so orchestrator work isn't blocked on hardware.

## Current position
**Phase: pre-0 (docs).** Next concrete action when green-lit: scope the Phase 0 spike
(what printer is available, enable LAN mode, gather serial + access code).
