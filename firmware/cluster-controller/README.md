# cluster-controller — ESP32 firmware (scaffold)

The non-sentient "hands" of the Brain. One ESP32 per cluster drives up to ~16 modules
(one **TMC2209** per module), enforcing **one motor moving at a time** (shared step/dir +
per-module enable). Talks to the Brain over **WiFi → MQTT**. Background: [docs/02](../../docs/02-architecture.md),
[docs/08](../../docs/08-hardware.md).

## Contract (mirror of the server-side `Module` calls)
Receives high-level commands over MQTT and reports status — it never decides anything:
- commands: `feed(mm)`, `retract(mm)`, `start_feed`, `start_retract`, `stop`, `enable(module)`
- reports: `move_complete`, `filament_present/absent`, `fault`
- **safe-failure:** on lost connection → **stop and hold**.

## Layout (PlatformIO)
- `src/` — firmware entrypoint (`setup()`/`loop()`) — empty scaffold
- `lib/` — testable components (motion, mqtt, sensors) — added during the H-track
- `include/` — shared headers

## Build (later)
```bash
pio run                 # build
pio run -t upload       # flash
pio device monitor      # serial
```
> Not implemented yet. Firmware begins on the **hardware on-ramp (H1–H3)** in
> [docs/07-v0-plan.md](../../docs/07-v0-plan.md), after the v0 software loop works with a human.
