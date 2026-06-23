# 05 — Open Questions & Assumptions to Validate

Living list. Each item: what's unknown, why it matters, when we resolve it.

## A. MQTT / printer control (Phase 0 — keystone)
1. **Exact unload/extrude/confirm/resume payloads** to drive Bambu's change routine over MQTT
   (Option A)? *(blocks everything)*
2. **Which report field** carries the **filament-present sensor** state, and how reliably
   does it update?
3. Is the **`M400 U1` pause** cleanly observable in the report stream in real time, and can
   we tell it apart from other pauses / read print progress to match it to the plan?
4. Does the printer **stay healthy** through a server-paced swap, or does it time out /
   cancel if the pause runs long?
5. Are X1/P1 and A1 payloads different enough to need separate drivers (assumed yes)?
29. **⛔ Does external-spool multicolor actually pause-and-prompt** on a real print (the
    `M400 U1` "No-AMS" preset)? *Top spike item — if false, redesign trigger.* See
    [09-filament-change-protocol.md](09-filament-change-protocol.md).

## A2. Resume state (Option A — mostly Bambu's job, but watch these)
30. **Temperature on long pauses** — does the nozzle drop to standby; re-heat-and-wait
    needed? *(v0 scoped to same-material/multi-color to delete this variable.)*
31. **Ooze/blob vs swap speed** — how bad are transitions at human (v0) pace vs motorized?
32. **Purge / color bleed** — is the routine's purge enough, or do we add an extrude step?
33. **Filament-position desync** — confirm riding the routine keeps the extruder's count
    correct (we never double-retract / fight its moves).

## B. Mechanical / hub
6. **Does a full module retract reliably clear the shared hub line** so the next feed
   doesn't collide? *(load-bearing for the whole hub design)*
7. Hub geometry: pure passive Y/funnel, or does it need anti-backflow / a converging guide?
8. Filament **tip shape after retract** — Bambu toolhead cuts at the extruder; in
   external-spool mode is there a clean cut, or do we get stringing/blobs that jam the hub?
9. Feed/retract **length calibration** per module (distance module-exit → hub → printer
   inlet → sensor).

## C. A1 tension (from the "mix/both" decision)
10. The **A1 AMS Lite is push-to-extruder with no central hub** — does the shared-hub model
    even apply to A1, or does A1 need a fundamentally different feed topology?
11. Can the A1 run a comparable **external-spool** flow at all, given its different feed path?

## D. Module hardware
12. Motor **torque & gear** sizing to push/retract through a multi-meter PTFE path without
    grinding filament.
13. ~~**Module bus** choice~~ → **DECIDED: ESP32-per-cluster over WiFi/MQTT.** Wired
    USB/serial or CAN/RS-485 remain fallbacks only if WiFi proves flaky.
14. Per-module **sensor** type (presence vs motion/encoder) and whether we need both.
15. ~~Per-module MCU vs clustered~~ → **DECIDED: ~1 ESP32 per ~16 modules**, one TMC2209 per
    module, one-motor-at-a-time multiplexing. (Pin/enable scheme pinned at H1.)
16. **Spool back-spin on retract** — enclosure contains tangles but doesn't remove slack;
    needs light rewind tension + short retract. Prototype on the one-module rig. *(was #4)*

## E. Orchestration / software
17. ~~Which filament is needed at each change~~ → **RESOLVED.** The sliced 3MF
    (`Metadata/plate_1.gcode`) encodes each change as `M400 U1` with `M1020 S<n>` giving the
    filament index, in order. Server builds the ordered plan; we author tagged pauses for
    validation. Full detail in [09-filament-change-protocol.md](09-filament-change-protocol.md).
18. **Concurrency** when M×N: arbitration if two printers want the same module / a module is
    busy.
24. **Sliced vs unsliced input** — leaning **require a *sliced* 3MF** (only it carries the
    gcode we parse). Accepting unsliced project 3MF/STL would require OrcaSlicer-headless
    (#28). Confirm we're happy mandating sliced for v0/v1.
25. **LAN job upload:** confirm the file-transfer path (FTPS?) **and** whether a sliced job
    can be uploaded/started over **MQTT**. *(Phase 0 software)*
28. **Who slices a raw 3MF in LAN mode?** Likely Bambu *cloud*, which LAN mode lacks — so
    unsliced input ⇒ *we* slice (OrcaSlicer-headless). Only relevant if we accept unsliced.
26. **Multi-printer MQTT:** our own broker + per-printer client; keep N connections healthy
    (reconnect, auth, heartbeat) — and the module ESP32s share the same broker.
27. **Front-end stack:** React vs Svelte vs Vue for the dashboard; how live state streams
    (websocket from FastAPI).

## F. Inventory (Phase 4+)
19. Spoolman as **source of truth** for module↔spool, or mirror into our own config?
20. Handling **partial spools / runout mid-print** — fail, or hot-swap to another module of
    the same material?

## G. Naming / scope
21. Real project name (placeholder: **AMS-X**).
22. Open-source it? License? (Spoolman/Bambu community context suggests yes.)

---

### Resolved so far
- ✅ **Single-brain principle:** the **Pi is the only sentient node** and the single source
  of truth (incl. *what filament is loaded in each printer*). Modules/printers are
  non-sentient — they act, report, and may throw errors; the **Pi handles all exceptions**.
- ✅ **Module is stateless/dumb:** tracks nothing (no filament-left), decides nothing — just
  push/pull filament through PTFE → Y-connector → printer external input.
- ✅ Target: X1/P1 **and** A1 via abstraction (X1/P1 first).
- ✅ Routing: our **own per-printer hub** (dumb buffer / Y-connector, not Bambu's AMS hub);
  connect directly to the printer; one filament in the line at a time.
- ✅ Clean tip: non-issue for initial scope; **optional cutter + recovery routine** later.
- ✅ Trigger model: **hybrid** — parse 3MF for the plan (server = source of truth) +
  **MQTT pause events** as the trigger.
- ✅ Server **owns the job**: 3MF upload → parse → LAN push → start → drive swaps. No
  custom slicer (OrcaSlicer-headless only as a fallback).
- ✅ Multi-printer: **own MQTT manager**, printer-as-class, full-state-on-connect +
  incremental deltas.
- ✅ Input format: **sliced 3MF** (carries `plate_1.gcode`). Unsliced ⇒ OrcaSlicer-headless
  (#28); leaning "require sliced" for v0/v1.
- ✅ **#17 RESOLVED** — filament identity comes from the parsed gcode (`M400 U1` + `M1020
  S<n>`); see [09-filament-change-protocol.md](09-filament-change-protocol.md).
- ✅ **Option A LOCKED** — ride Bambu's own change routine; never author hotend gcode. We own
  filament logistics to the sensor; Bambu owns hotend physics.
- ✅ **Pause validation** — act only on pauses matched to the plan (we author tagged pauses);
  everything else is an exception (single-brain).
- ✅ **Cluster control DECIDED** — ESP32 (or Pico W) per ~16 modules over WiFi/MQTT; one
  TMC2209 per module; one-motor-at-a-time; wall-powered 24V; no batteries; common-ground.
- ✅ **Brain ≠ necessarily a Pi** — any always-on host can be the brain (modules are network
  devices); Pi recommended.
- ✅ First milestone: **MQTT-only spike**, no hardware.
- ✅ **v0 = "human is the module"** — software-only full loop; a `Module` class exists but
  a human fulfills it (no hardware). See roadmap.
