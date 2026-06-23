# 07 — v0 Plan (concrete, build-ready, recordable)

> v0 is **not** a throwaway "smallest thing." It is the **real architecture, built thin**:
> the actual classes, interfaces, and structure we keep — just with a **human standing in
> for the module hardware** and only one material change to prove. Everything here is built
> on the skeleton from [02-architecture.md](02-architecture.md) and [06](06-module-interface.md),
> so nothing is rebuilt later.

## v0 definition of done (the money shot)

> A real multi-color print runs on a real printer. At the color change, the **server**
> (running on the Pi) detects the pause over MQTT, **prompts the human** ("module 2: feed"),
> the human swaps filament, the printer sensor trips, and the **server resumes the print** —
> all driven by a job the server itself parsed and started. **Zero module hardware.**

## Three principles for v0

1. **Real architecture, thin slice.** Use the real `Printer`, `Module`, `Orchestrator`
   classes from day one. The only thing "fake" is the actuator (`ManualModule`).
2. **Exploration spikes are separate from the app.** When we're *discovering* MQTT payloads
   we write throwaway scripts. Once known, the *finding* goes into the real app. We never
   ship the throwaway.
3. **Scope v0 to same-material, multi-*color* (e.g. all PLA).** This deletes the
   temperature-change variable so v0 isolates mechanics + protocol. Mixed-material is later.

---

## v0 sub-steps

Each step: **Goal → Approach → Architecture it introduces → Done when → Record** (the
YouTube beat). Steps are ordered; a ⛔ marks a go/no-go gate.

### v0.0 — Bench & project setup
- **Goal:** a clean, presentable starting point on the Pi.
- **Approach:** Pi imaged and on the LAN; printer in **LAN mode** with serial + access code
  in hand; a known **multi-color test model** sliced to a 3MF; empty repo skeleton
  (`server/`, `docs/`, config).
- **Architecture:** repo layout + config file (printer serial/access code, test paths).
- **Done when:** `hello` server runs on the Pi and is reachable over LAN.
- **Record:** "What we're building and why Bambu's 4-slot limit needs beating."

### v0.1 — Talk to the printer (no cloud) ⛔
- **Goal:** prove we can reach the printer's **local MQTT** broker.
- **Approach:** connect (TLS, access code), subscribe to the report topic, print the stream.
- **Architecture:** `MqttConnection` (one per printer); config-driven.
- **Done when:** live report messages stream in from a real printer over the LAN.
- **Record:** "Talking to a Bambu printer with no internet."

### v0.2 — The keystone spike (GO / NO-GO for the whole project) ⛔
- **Goal:** confirm the load-bearing MQTT + protocol assumptions.
- **Approach:** throwaway scripts / a hand-sliced **No-AMS `M400 U1`** 2-color test print to:
  - **(a)** confirm **external-spool multicolor actually pauses-and-prompts** (`M400 U1`) on a
    real print — *the top item; if false, redesign trigger;*
  - **(b)** find the **filament-present sensor** field and watch it change by hand;
  - **(c)** **drive Bambu's change routine** — unload / extrude / **confirm / resume** — over
    MQTT (Option A);
  - **(d)** observe the **pause event** in the report stream and whether we can tell it apart
    / read progress to match it to the plan.
- **Architecture:** none yet — exploration. Output is the **MQTT command/field reference**
  (a doc), feeding v0.4/v0.5. Cross-ref [09-filament-change-protocol.md](09-filament-change-protocol.md).
- **Done when:** all four demonstrated from a script. **If (a) or (c) fails, stop and
  redesign before going further.**
- **Record:** "The make-or-break test: can we even control this thing?"

### v0.3 — Printer state model
- **Goal:** a live, authoritative in-memory model of the printer.
- **Approach:** `Printer` class — empty → **full state on connect** → **incremental deltas**
  from the report stream. Pi tracks **what it believes is loaded** (source of truth).
- **Architecture:** `Printer` (state) over `MqttConnection` (transport); printer-abstraction
  interface stubbed (`X1P1Driver` first).
- **Done when:** the state object reflects reality and updates live as the printer changes.
- **Record:** "Giving the server a real-time picture of the printer."

### v0.4 — Job in: parse + start a print
- **Goal:** the server owns the job.
- **Approach:** upload a **3MF** to the server; **parse** it into a material-change **plan**;
  push it to the printer over **LAN (FTPS)**; **start** the print via MQTT.
- **Architecture:** `JobParser` (3MF → plan), `FilePush` (FTPS), `Printer.start_print()`.
  Resolve #17 minimally here (e.g. the UI/CLI confirms which module = which planned change).
- **Done when:** the server starts a real multi-color print that it parsed itself.
- **Record:** "Drag in a file, the server prints it — no Bambu cloud."

### v0.5 — The `Module` interface + `ManualModule`
- **Goal:** the contract from [06](06-module-interface.md), human-backed.
- **Approach:** implement `Module` with `ManualModule` — `start_feed()`/`stop()`/`retract()`
  become **prompts** to the human (terminal first, web later).
- **Architecture:** `Module` interface + `ManualModule` impl. Orchestrator depends only on
  the interface (so Phase 1's `HardwareModule` drops in unchanged).
- **Done when:** the server can issue feed/retract requests that appear as human prompts and
  wait for confirmation.
- **Record:** "I am the robot: standing in for hardware we haven't built."

### v0.6 — The orchestrator: full loop ⛔ (v0 exit)
- **Goal:** tie it all together for one unattended-except-the-human swap.
- **Approach:** `Orchestrator` state machine — watch print → **pause event (MQTT)** →
  pick module from **plan** → `ManualModule` prompt → human swaps → **printer sensor trips
  (MQTT)** → `Printer.resume()`. Handle the obvious failures (sensor never trips → re-prompt;
  printer faults → alert).
- **Architecture:** `Orchestrator` over `Printer` + `Module`; the closed loop lives here.
- **Done when:** **a multi-color print completes** with the human as the module, end to end.
- **Record:** "It works: a color change, fully driven by the server."

---

## Parallel track — Hardware on-ramp (for a hardware beginner)

These run **alongside** the software v0 (they don't block it) so that by the time v0.6 is
done, you're ready to build a real `HardwareModule` with confidence — and each is a tidy
episode. **No integration with the printer yet — pure learning on the bench.**

| Step | Goal | You'll learn | Done when |
|------|------|--------------|-----------|
| H0 | Pi GPIO basics | Wiring, power, not frying things | Blink an LED from the Pi |
| H1 | Spin a stepper | Driver wiring (e.g. ULN2003/A4988/TMC2209), step/dir, current | Motor turns both ways on command |
| H2 | Read a sensor | Digital input, debouncing | Pi prints "filament present / absent" |
| H3 | Move filament | Drive gear + PTFE, steps-per-mm feel | Push/pull filament a measured distance through a tube |

**Bridge:** H1–H3 together = everything `HardwareModule` needs. Phase 1 is then "wrap H1–H3
in the `Module` interface and delete `ManualModule` from the loop."

---

## What we need from you before building (prerequisites)
- A printer in **LAN mode**; its **serial + access code**.
- A **Raspberry Pi** (model TBD) on the same network.
- A **same-material multi-color test model**, sliced with the **No-AMS / `M400 U1`** preset
  to a **sliced 3MF** (small, fast, obvious color changes).
- For the hardware track: a stepper + driver + a filament sensor + PTFE + a drive gear
  (cheap "starter" parts are fine; we pick exact parts at H1).

## v0 risks / gates (in order)
1. ⛔ **v0.2** — if MQTT can't do unload/load/sensor/pause, the whole approach changes.
2. **#28** — if our test 3MF needs slicing in LAN mode, we need OrcaSlicer-headless earlier.
3. **#17** — the plan→module mapping; v0.4 uses the simplest possible version.
4. Printer tolerating a human-paced pause without canceling (observed at v0.6).

## Architecture changes this plan implies (vs current docs)
- None structural — v0 *instantiates* the existing architecture. It does pin down: the
  class boundaries (`MqttConnection` / `Printer` / `JobParser` / `FilePush` / `Module` /
  `Orchestrator`), and confirms `ManualModule` and `HardwareModule` share one interface.
