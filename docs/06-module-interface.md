# 06 — The `Module` Interface (Design)

> **This is a design contract, not an implementation.** It defines what every module must
> be able to do, so the orchestrator can stay identical whether a **human** (`ManualModule`,
> v0) or a **motor** (`HardwareModule`, Phase 1+) is behind it. No application code is being
> written; the pseudo-signatures below are the *shape* of the contract.

## Design principles

1. **One contract, swappable actuator.** The orchestrator only ever talks to a `Module`. It
   must not know or care whether a stepper or a person performs the motion.
2. **The module is non-sentient and stateless.** It moves filament and reports its own local
   sensor — nothing more. It **tracks nothing** (no filament-remaining, no history; that's
   the Pi's / Spoolman's job) and **decides nothing**. It does **not** read the *printer's*
   filament sensor — that lives on the printer and is read by the orchestrator over MQTT.
   The most a module does on its own is **throw an error back to the Pi**; the Pi handles it.
   This split keeps the closed loop (feed-until-the-printer-sees-it) in the orchestrator,
   where both signals are visible, and follows the **single-brain principle**
   ([02-architecture.md](02-architecture.md)).
   Physically a module is just: stepper → drive gear → PTFE → into a Y-connector
   (N PTFE in → 1 PTFE out) → the printer's **external-spool input** (not Bambu's hub).
3. **Two motion styles, because we need both:**
   - **Bounded move** (`feed(mm)` / `retract(mm)`) — for "retract a known distance to clear
     the hub," where there's no sensor to stop against.
   - **Continuous move** (`start_feed()` / `stop()`) — for "feed until the *printer* sensor
     trips," where the orchestrator watches MQTT and halts the module.
4. **Async + event-driven.** A move may take seconds (or, for `ManualModule`, as long as a
   human takes). Calls return when the action completes or faults; modules also emit events.
5. **Identity is data, not behavior.** Which spool/material a module holds is config
   (later: Spoolman), not part of the motion contract.

## Responsibilities (what a module owns)

| Owns | Does **not** own |
|------|------------------|
| Feeding / retracting its filament | Reading the printer's filament sensor (orchestrator, via MQTT) |
| Its **local** filament-present sensor | Deciding *when* to swap (orchestrator) |
| Reporting motion done / faulted | Knowing the print plan (orchestrator) |
| Reporting "I'm empty" | Talking to the printer at all |
| Its address / id | The hub (passive) |

## The interface (pseudo-contract)

```
interface Module:

    # ---- identity / config (data) ----
    id            : ModuleId          # stable address on the bus
    spool         : SpoolRef | None   # what's loaded (Spoolman id later)
    state         : ModuleState       # see state machine below

    # ---- bounded motion (no external feedback) ----
    feed(mm: float, speed: float?)    -> MoveResult   # advance toward hub/printer
    retract(mm: float, speed: float?) -> MoveResult   # pull back toward spool

    # ---- continuous motion (orchestrator closes the loop) ----
    start_feed(speed: float?)         -> None         # begin advancing, run until stop()
    start_retract(speed: float?)      -> None
    stop()                            -> None         # halt current motion

    # ---- sensing ----
    has_filament()                    -> bool         # LOCAL sensor at the module exit

    # ---- lifecycle / safety ----
    home()                            -> MoveResult?  # optional reference (hardware)
    abort()                           -> None         # hard stop + go to FAULT-safe

    # ---- events the module EMITS (orchestrator subscribes) ----
    on(event)  where event in:
        MOVE_COMPLETE        # bounded move finished
        FILAMENT_PRESENT     # local sensor: filament detected
        FILAMENT_ABSENT      # local sensor: ran out / removed  -> "need a new spool?"
        FAULT                # jam / stall / timeout
```

```
MoveResult  = { ok: bool, reason?: str, moved_mm?: float }
ModuleState = IDLE | FEEDING | RETRACTING | FAULT | EMPTY
SpoolRef    = { material, color, spoolman_id?, ... }   # later
```

## State machine

```
        ┌───────────────────────────── abort()/FAULT ──────────────┐
        ▼                                                           │
     [IDLE] ──start_feed()/feed()──► [FEEDING] ──stop()/done──► [IDLE]
        │                               │                          ▲
        │                          FILAMENT_ABSENT                 │
        │                               ▼                          │
        ├──start_retract()/retract()─► [RETRACTING] ──stop()/done──┘
        │
        └── FILAMENT_ABSENT ──► [EMPTY]  (alert user: replace spool)
```

`FAULT` is reachable from any motion state (jam/stall/timeout). Recovery is the
orchestrator's job (retry, alert, or cutter routine later).

## How the two implementations honor the contract

### `ManualModule` (v0 — the human is the module)
- `start_feed()` → **prompt the user**: "Insert filament from module *k* and start
  feeding." Returns immediately; the human is now feeding.
- orchestrator watches the **printer** sensor over MQTT; when it trips, calls `stop()` →
  **prompt**: "Stop — filament detected."
- `retract(mm)` → **prompt**: "Pull filament from module *k* back ~X cm," wait for "done."
- `has_filament()` → either a real cheap sensor, or the user answers a prompt.
- Emits `FILAMENT_ABSENT` when the user says the spool is empty.
- **Why this matters:** it lets us build and prove the *entire* orchestrator + event flow
  with zero motor hardware. v0 runs on this.

### `HardwareModule` (Phase 1+ — stepper + driver)
- `feed(mm)` / `retract(mm)` → step count = mm × steps-per-mm; run the **stepper** via its
  **driver** (e.g. TMC2209 / A4988 / ULN2003) from the Pi (directly or via a small MCU).
- `start_feed()` / `stop()` → run / halt the motor continuously.
- `has_filament()` → read the **local presence sensor** at the module exit.
- `FAULT` → driver stall detection (e.g. TMC StallGuard) or motion-vs-sensor mismatch.
- **Same method names, same events.** The orchestrator code does not change from v0.

## Where it sits in the system

```
Orchestrator ── Module (interface)
                  ├── ManualModule   (v0: prompts a human)
                  └── HardwareModule  (Pi → driver → stepper + local sensor)

Orchestrator ── Printer (abstraction, MQTT)   ← reads the PRINTER filament sensor here
```

The orchestrator runs the swap by combining the two: drive the `Module` mechanically, watch
the `Printer` sensor over MQTT, and decide when each step is done.

## Explicitly NOT the module's job (single-brain principle)
- Tracking **how much filament is left** — Pi / Spoolman.
- Knowing **what material** it holds beyond a config label — Pi / Spoolman.
- **Handling its own faults** — it reports; the Pi decides what to do.
- Knowing anything about the **print, the plan, or the printer**.

## Open within this contract (to settle when we build it)
- Exact **continuous-vs-bounded** usage per swap step (which steps need sensor-closed-loop
  vs a calibrated distance) — pins down during v0.
- Whether `ManualModule` needs a real local sensor or can rely on user prompts in v0.
- Steps-per-mm **calibration** per module (Phase 1).
- The concrete **command/event transport** to `HardwareModule` (GPIO direct vs MCU over
  CAN/RS-485) — see [05-open-questions.md](05-open-questions.md) #13/#15. The interface is
  deliberately transport-agnostic.
