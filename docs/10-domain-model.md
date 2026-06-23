# 10 — Domain / Class Model (design)

> **Design-level class model, not code.** Pseudo-signatures describe the *shape* of the
> server (the "Brain"). It realises the decisions in [02-architecture.md](02-architecture.md)
> (single-brain, Option A, hybrid trigger, ESP32 clusters) and reuses the `Module` contract
> from [06-module-interface.md](06-module-interface.md) and the gcode facts in
> [09-filament-change-protocol.md](09-filament-change-protocol.md).

## Layers (dependencies point downward)

```
  ┌─────────────────────────────────────────────────────────────┐
  │ ORCHESTRATION   Orchestrator · SwapStateMachine · SwapContext │
  ├─────────────────────────────────────────────────────────────┤
  │ JOB             Job · JobParser · SwapPlan · PlannedSwap      │
  ├──────────────────────────────┬──────────────────────────────┤
  │ PRINTER  Printer · PrinterState│ MODULE  Module · Cluster ·   │
  │          · PrinterDriver(impl) │         ModuleRegistry       │
  ├──────────────────────────────┴──────────────────────────────┤
  │ TRANSPORT       MqttBus · PrinterLink · ClusterLink · FtpClient│
  ├─────────────────────────────────────────────────────────────┤
  │ INVENTORY (later)  Spool · SpoolmanClient                     │
  ├─────────────────────────────────────────────────────────────┤
  │ CROSS-CUTTING   Brain (root) · Config · EventBus              │
  └─────────────────────────────────────────────────────────────┘
```

The **single-brain rule** maps directly onto these types: only `Orchestrator` (and the
`Brain` it lives in) makes decisions; everything else acts, reports, or stores state.

---

## Cross-cutting

### `Brain`  — application root (one per install; runs on the CasaOS host)
```
Brain:
    config        : Config
    bus           : MqttBus                 # our own broker (Mosquitto)
    printers      : map<PrinterId, Printer>
    clusters      : map<ClusterId, Cluster>
    modules       : ModuleRegistry          # flat view across clusters
    orchestrators : map<PrinterId, Orchestrator>   # one per active job
    spoolman      : SpoolmanClient?         # later

    start()                  # connect bus, load config, bring printers/clusters online
    submit_job(printer, 3mf) -> Orchestrator   # the front-end entry point
```

### `Config` — declarative wiring (YAML/TOML)
```
Config:
    printers : list<{ id, model, serial, access_code, ip }>
    clusters : list<{ id, mqtt_topic, module_ids }>
    modules  : list<{ id, cluster_id, filament_index?, spool_ref? }>
    hub      : { per_printer topology }     # mostly informational
```

### `EventBus` — internal pub/sub so reports become typed events
Carries `PauseEvent`, `SensorEvent`, `ModuleEvent`, `FaultEvent` from transport up to the
`Orchestrator`. (May simply be the `MqttBus` with typed wrappers.)

---

## Transport layer (non-sentient plumbing)

```
MqttBus:                       # our broker; printers AND clusters speak to it
    publish(topic, payload)
    subscribe(topic, handler)

PrinterLink:                   # one per printer; local LAN MQTT (TLS + access code)
    printer_id : PrinterId
    request(payload)           # device/{serial}/request
    on_report(handler)         # device/{serial}/report  (full + deltas)

ClusterLink:                   # one per ESP32 cluster (WiFi → MQTT)
    cluster_id : ClusterId
    send(module_id, command)   # "feed/retract/stop/enable"
    on_status(handler)         # acks, sensor states, faults; safe-stop on disconnect

FtpClient:                     # LAN file upload (FTPS) of the sliced job
    upload(printer, file) -> remote_path
```

---

## Printer domain

### `Printer` — live model + authoritative truth for one machine
```
Printer:
    id            : PrinterId
    driver        : PrinterDriver        # model-specific (below)
    state         : PrinterState         # cached, delta-updated
    link          : PrinterLink

    connect()                  # pull FULL state once, then apply deltas
    on_report(r)               # update state; emit PauseEvent / SensorEvent on changes
    # high-level actions delegate to driver:
    send_job(file) ; start_print(path) ; drive_change_step(step) ; resume()
```

### `PrinterState` — the cached snapshot (value-ish, mutated by deltas)
```
PrinterState:
    stage          : enum(IDLE, PRINTING, PAUSED, ERROR, FINISHED)
    pause_reason   : PauseReason?        # change vs user vs error (if the report exposes it)
    progress       : { layer?, percent?, line? }
    filament_sensor: bool                # printer's own present-sensor
    loaded_filament: FilamentRef?        # ← Pi-AUTHORITATIVE: what the Brain believes is loaded
    raw            : dict                 # last full report, for fields we don't model yet
```
> `loaded_filament` is the **single source of truth** (single-brain). The printer's report
> is reconciled against it, never blindly trusted.

### `PrinterDriver` — interface; hides X1/P1 vs A1 (Option A: ride Bambu's routine)
```
interface PrinterDriver:
    send_job(file)            -> remote_path     # via FtpClient
    start_print(path)
    pause_state()             -> PauseReason?
    filament_present()        -> bool
    # drive Bambu's OWN change routine over MQTT — we never author hotend gcode:
    routine_unload()
    routine_extrude()
    routine_confirm_resume()

X1P1Driver  implements PrinterDriver     # X1/P1 first
A1Driver    implements PrinterDriver      # later; AMS-Lite feed path differs
```

---

## Job domain (hybrid: plan from file)

### `Job` → `JobParser` → `SwapPlan`
```
Job:
    file        : path            # the uploaded sliced .gcode.3mf
    printer_id  : PrinterId

JobParser:
    parse(job)  -> SwapPlan       # unzip → Metadata/plate_1.gcode → scan M400 U1 / M1020 S<n>

SwapPlan:
    swaps : list<PlannedSwap>     # ordered; index 0..k-1

PlannedSwap:
    seq            : int          # change #k (matches the k-th pause)
    filament_index : int          # from M1020 S<n>  → "which color is next"
    tag            : str          # our injected marker for pause-validation
    layer?         : int          # position hint, if available
```
> The `SwapPlan` is what makes the Brain the **source of truth for what comes next**. We also
> author the change-gcode, so each pause is tagged → `Orchestrator` can tell our pauses apart
> from stray user pauses.

---

## Module domain (non-sentient actuators)

### `Module` — see [06-module-interface.md](06-module-interface.md) for the full contract
```
interface Module:                 # ManualModule (v0, human) | HardwareModule (motor)
    id, spool, state
    feed/retract(mm) ; start_feed/start_retract/stop() ; has_filament() ; home/abort()
    emits: MOVE_COMPLETE | FILAMENT_PRESENT | FILAMENT_ABSENT | FAULT
```

### `Cluster` — one ESP32 driving ≤16 modules, one-at-a-time
```
Cluster:
    id       : ClusterId
    link     : ClusterLink
    modules  : list<Module>        # HardwareModule wrap drivers behind this link
    active   : ModuleId?           # enforce "one module moves at a time"
    # routes Module calls to ESP32 commands; disables idle modules
```

### `ModuleRegistry` — resolves "which module" for a swap
```
ModuleRegistry:
    by_id(ModuleId)            -> Module
    for_filament_index(int)    -> Module       # config map now; Spoolman match later
    for_material(MaterialRef)  -> Module        # later (inventory-driven)
```

---

## Orchestration (the only sentient part)

### `Orchestrator` — ties plan + live events + module actions for one print
```
Orchestrator:
    printer   : Printer
    plan      : SwapPlan
    registry  : ModuleRegistry
    sm        : SwapStateMachine
    cursor    : int = 0            # next expected PlannedSwap.seq

    run()                          # start print, then react to events
    on(PauseEvent e):              # ← the hybrid trigger
        if not validate(e): handle_exception(e); return     # not our tagged pause
        swap = plan.swaps[cursor]
        sm.execute(SwapContext(printer, registry.for_filament_index(swap.filament_index)))
        cursor += 1
    on(FaultEvent) / on(disconnect): safe_hold(); alert()
```

### `SwapStateMachine` — the heart (see swap sequence in [02](02-architecture.md))
```
SwapState = WATCHING → UNLOADING → SELECTING → FEEDING → SENSING → RESUMING → WATCHING
                                        ↘ FAULT (from any) ↘

SwapStateMachine.execute(ctx):
    UNLOADING : printer.driver.routine_unload() ; ctx.old_module.retract until hub clear
    SELECTING : ctx.next_module = registry.for_filament_index(...)
    FEEDING   : ctx.next_module.start_feed()
    SENSING   : poll printer.filament_present() (MQTT) → stop() on trip; timeout → FAULT
    RESUMING  : printer.driver.routine_confirm_resume()
```

### `SwapContext` — per-swap working state
```
SwapContext:
    printer, old_module, next_module, planned_swap, started_at, retries
```

---

## Inventory (later)

```
Spool:          { id, material, color, remaining_g, module_id? }
SpoolmanClient: list_spools() ; spool_for(module_id) ; module_for_material(m)   # REST
```
When present, `ModuleRegistry.for_material()` and `Printer.loaded_filament` enrich from here.

---

## Value objects & enums
```
PrinterId, ClusterId, ModuleId : stable string ids
FilamentRef    : { index, material?, color?, spool_id? }
PauseReason    : enum(CHANGE, USER, ERROR, UNKNOWN)
MoveResult     : { ok, reason?, moved_mm? }
ModuleState    : IDLE | FEEDING | RETRACTING | FAULT | EMPTY
SwapState      : WATCHING | UNLOADING | SELECTING | FEEDING | SENSING | RESUMING | FAULT
```

## Key relationships (multiplicity)
```
Brain 1──* Printer        Brain 1──* Cluster        Cluster 1──≤16 Module
Printer 1──1 PrinterState Printer 1──1 PrinterDriver
Orchestrator 1──1 Printer  Orchestrator 1──1 SwapPlan  SwapPlan 1──* PlannedSwap
PlannedSwap *──1 Module (resolved via ModuleRegistry by filament_index)
Module *──1 Cluster        Module 0..1──1 Spool (later)
```

## A swap, traced through the objects
1. `PrinterLink.on_report` → `Printer` sees `stage=PAUSED` → emits `PauseEvent`.
2. `Orchestrator.on(PauseEvent)` → `validate()` against `plan.swaps[cursor].tag`.
3. `SwapStateMachine`: `printer.driver.routine_unload()` + `old_module.retract()`.
4. `registry.for_filament_index(swap.filament_index)` → `next_module`.
5. `next_module.start_feed()`; poll `printer.filament_present()` → `stop()` on trip.
6. `printer.driver.routine_confirm_resume()`; `cursor++`; back to `WATCHING`.

## Deferred / open (tracked in [05-open-questions.md](05-open-questions.md))
- `A1Driver` specifics (#10/#11); exact `PrinterDriver` routine payloads (#1, Phase 0).
- Whether `PauseEvent` carries `pause_reason`/`progress` for richer `validate()` (#3, #29).
- `ModuleRegistry.for_material` + `Spool*` wiring (Phase 4).
- Concurrency when M×N: arbitration if two `Orchestrator`s want the same `Module` (#18).
