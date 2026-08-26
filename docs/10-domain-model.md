# 10 — Domain / Class Model

> **The classes, as they exist.** This document describes *what each type is and what it owns*.
> The **folder** architecture — which package a thing goes in and the import contracts that
> enforce it — is [server/00-architecture.md](server/00-architecture.md). The swap sequence is
> [02-architecture.md](02-architecture.md); the `Module` contract is
> [06-module-interface.md](06-module-interface.md); the gcode facts are
> [09-filament-change-protocol.md](09-filament-change-protocol.md).

## The one rule

**Only `Orchestrator` decides. Everything else acts, reports, or stores state.**

Every other shape in this document follows from that. A module moves filament and reports its
own sensor; a printer caches state and emits events; a link moves bytes; the `Brain` builds
objects and wires them together. None of them chooses anything.

---

## The seams — `types/protocols.py`

RULE 1 says a layer depends on the layer below through a **named seam**. All six seams live in
one file so *"what can I swap out, and what would I have to implement?"* is one file rather than
a hunt.

Every one is a **structural** `Protocol`. An implementation satisfies it by having the right
methods, not by inheriting. `ManualModule` names no base class at all and still satisfies
`Module`. That is what lets v0 (a human) become Phase 1 (a motor) as a drop-in swap, and what
lets the whole test suite run with no printer, no broker, and no network.

| Seam | Answers | Real | Simulated / v0 |
|---|---|---|---|
| `Module` | how do I move filament? | *(HardwareModule, Phase 1)* | `ManualModule` |
| `PrinterControl` | what does the orchestrator need from a printer? | `Printer` | any fake |
| `PrinterLink` | how do bytes reach one printer? | `MqttPrinterLink` | `SimulatedPrinterLink` |
| `PrinterDriver` | what does an unload look like on *this* model? | `X1P1Driver`, `A1Driver` | — |
| `FtpClient` | how does the sliced file get there? | `FtpsClient` | `SimulatedFtpClient` |
| `SpoolStore` | what spools exist? | `SpoolmanStore` | `FakeSpoolStore` |

```
Module          feed/retract(mm) ; start_feed/start_retract/stop()
                has_filament() ; abort()          # LOCAL sensor only

PrinterControl  loaded_filament                   # Pi-authoritative
                filament_present()
                routine_unload() ; routine_extrude() ; routine_confirm_resume()
                send_job(file) ; start_print(path)

PrinterLink     request(payload) ; on_report(handler)

PrinterDriver   request_unload() / request_extrude() / request_confirm_resume()
                request_start_print(path) -> Report      # returns payloads, never sends
                parse_pause_reason(report) ; parse_filament_present(report)

FtpClient       upload(printer, file) -> remote_path

SpoolStore      list_spools() ; get_spool() ; loaded_in(module) ; set_module()
                match(material, color) ; consume(spool, grams) ; create/update/delete
```

> **`PrinterControl` is why orchestration is testable.** The `Orchestrator` is typed against
> `PrinterControl`, not `Printer` — so `apps.orchestration` never imports `apps.printer`, and
> `import-linter` fails the build if it tries. The state machine has no idea MQTT exists.

> **`PrinterDriver` returns payloads; it does not send them.** The driver knows *what an unload
> looks like on this model*; the `Printer` owns sequencing and state; the `PrinterLink` owns the
> wire. Three responsibilities, three types.

---

## Cross-cutting

### `Brain` — composition root (`system/brain.py`)

One per install, on the CasaOS host. It **builds and wires every concrete class, once** — and
then gets out of the way.

```
Brain:
    config        : Config
    events        : EventBus
    prompts       : PromptBroker
    printers      : dict<PrinterId, Printer>
    clusters      : dict<ClusterId, Cluster>
    registry      : ModuleRegistry?
    orchestrators : dict<PrinterId, Orchestrator>
    store         : SpoolStore          # property; setter rebuilds `resolver`
    resolver      : Resolver
    assignment    : dict<PrinterId, dict<int, ProposedRow>>   # operator's colour→module proposal
    confirmed     : set<PrinterId>

    start() / stop()
    arm_job(printer, file)   -> Orchestrator   # parse + arm, NO push/start  ← primary path
    start_armed(printer)                       # FTPS push + start, after operator confirms
    submit_job(printer, file)-> Orchestrator   # arm_job + start_armed (hardware-unverified)
```

**The Brain is not a dispatcher.** It subscribes to exactly one event — `FinishedEvent`, to
consume spool grams when a print ends. Every swap-relevant event goes straight from `Printer`
to `Orchestrator` over the bus; the Brain is never on that path.

`arm_job` is the FTPS-free path and the one that works today: the operator starts the print
themselves, and the Brain owns the loop from the first pause onward. It also **detaches the
previous orchestrator** before arming a new one — a stale subscriber otherwise hears the same
pause and runs the swap twice (observed live, 2026-06-25).

### `EventBus` + typed events (`events.py`)

A minimal async pub/sub keyed by event type, stdlib only, so every layer may import it. The
printer layer turns raw MQTT reports into these; the `Orchestrator` subscribes.

```
PauseEvent     printer_id, reason, tag?, layer?, line?   # `line` = mc_print_line_number (#17)
SensorEvent    printer_id, filament_present
ModuleEvent    module_id, kind, state?
FaultEvent     source, detail
FinishedEvent  printer_id                                # → Brain consumes spool grams (SOFT)

EventBus:  subscribe(type, handler) ; unsubscribe(type, handler) ; publish(event)
```

`publish` awaits all matching handlers and **lets a handler's exception surface** — the single
brain must see its own failures. `unsubscribe` exists so re-arming a printer can tear down the
old orchestrator's subscription.

### `Config` — declarative wiring (`config/`)

```
Config:
    bus      : BusConfig
    printers : list<PrinterConfig>     # id, model, serial, access_code, ip
    clusters : list<ClusterConfig>     # id, module_ids
    modules  : list<ModuleConfig>      # id, cluster_id, filament_index?, spool_ref?
    spoolman : SpoolmanConfig?
```

---

## Printer app (`apps/printer/`)

### `Printer` — live model and authoritative truth for one machine

Satisfies `PrinterControl`. Owns **sequencing** of the Option-A change routine; the payloads
live in the driver, the wire lives in the link.

```
Printer:
    id, link, driver, bus, ftp?, state

    connect()      # register handler, then pull FULL state once
    on_report(r)   # full on first, deltas after; emits PauseEvent / SensorEvent on changes
```

### `PrinterState` — the cached snapshot

```
PrinterState:
    stage           : PrinterStage      # IDLE | PRINTING | PAUSED | ERROR | FINISHED
    pause_reason    : PauseReason?
    progress        : { layer?, percent?, line? }
    filament_sensor : bool              # the printer's OWN sensor
    loaded_filament : FilamentRef?      # ← Pi-AUTHORITATIVE
    raw             : dict              # last full report, for fields we don't model yet
```

> `loaded_filament` is **never set from a report.** Only the Orchestrator sets it, on a
> successful swap. The printer's own claim is reconciled against ours, never trusted over it —
> the single-brain rule showing up as a field.

### `PrinterDriver` implementations

`X1P1Driver` (primary) and `A1Driver` (AMS-Lite feed path differs). Both pure payload builders:
give them a request, get back a dict. No I/O, so both are exhaustively testable.

---

## Orchestration app (`apps/orchestration/`)

The only sentient package, and the only one `import-linter` pins to the seams — it may not
import `apps.printer`, `system.*`, `libs`, or `routes`.

### `Orchestrator` — one per active print

```
Orchestrator:
    printer  : PrinterControl        # the SEAM, not `Printer`
    plan     : SwapPlan              # handed in; the Orchestrator never parses
    registry : ModuleRegistry
    bus      : EventBus
    sm       : SwapStateMachine
    cursor   : int = 0               # next expected PlannedSwap.seq
    held     : bool                  # safe-hold latch
    alerts   : list<str>

    subscribe() / unsubscribe()      # PauseEvent · SensorEvent · FaultEvent
    on_pause(e)   # validate against plan → run swap → cursor++
    on_sensor(e)  # forward into the sensing loop (closes the loop)
    on_fault(e)   # safe-hold + alert, never a swap
```

**The plan arrives finished.** `Brain.arm_job` calls `JobParser().parse(...)` and passes the
result in. The orchestrator conducts; it does not compose.

Two guards worth knowing:

- **`_swap_lock`** — serialises swap execution so two pauses can never run concurrently for one
  printer.
- **`_last_accepted_line`** — the gcode line of the last accepted pause, a lower bound for the
  next one. Combined with the ordinal cursor this is the open-#17 guard that confirms an
  untagged Bambu pause really is the k-th planned change. When the guard can't be applied, the
  swap still runs but an alert records that the loop ran **unguarded**.

### `SwapStateMachine` — the heart

```
WATCHING → UNLOADING → SELECTING → FEEDING → SENSING → RESUMING → WATCHING
                            ↘  FAULT (reachable from any step)  ↙
```

`execute(ctx)` returns `WATCHING` on success and raises `SwapFault` (after landing in `FAULT`)
on any failure, so the orchestrator gets a specific reason to alert on. `busy` is observable, so
a stray pause mid-swap can never double-trigger. `note_sensor()` lets a pushed `SensorEvent`
satisfy the sensing loop as well as polling.

### `SwapContext` — per-swap working state

```
SwapContext:
    printer, old_module, next_module?, planned_swap
    retract_mm, sense_timeout_s, sense_poll_s, retries
```

---

## Job app (`apps/job/`)

Pure parsing — no printer, no hardware, no network.

```
Job:         file, printer_id

JobParser:   parse(job) -> SwapPlan
             # unzip 3MF → Metadata/plate_1.gcode → scan top-to-bottom
             # one PlannedSwap per `M400 U1`, filament index from the governing `M1020 S<n>`

SwapPlan:    swaps  : list<PlannedSwap>
             base   : FilamentColor?          # what's loaded at layer 0
             colors : list<FilamentColor>     # the job's full palette, for the operator UI

PlannedSwap: seq, filament_index, tag, layer?, line?, material?, color_hex?
```

`JobParseError` on an unsliced project 3MF — only a *sliced* 3MF carries the gcode we parse.

---

## Module app (`apps/module/`)

### `ManualModule` — the v0 implementation

Satisfies `Module`. Every motion call becomes a **prompt to a human**, awaited. The prompter is
injectable (an async callable), so tests auto-answer and the API can surface it as a real
operator prompt. Non-sentient and near-stateless: it tracks `id` and `state`, nothing else.

### `ModuleRegistry` — resolves "which module"

```
ModuleRegistry:
    by_id(module_id)          -> Module
    for_filament_index(index) -> Module    # config map now; Spoolman match later
```

This is the `PlannedSwap → Module` edge. The plan says "filament index 3 next"; the registry
turns 3 into an object. The Brain injects a **resolver** that prefers the operator's confirmed
colour→module assignment and falls back to this static map.

### `Cluster` — the one-at-a-time interlock

```
Cluster:
    id, modules, active : ModuleId?
    move(module, motion) -> T      # acquires the single active slot, runs, releases
```

`move()` takes a **zero-arg factory**, not an awaitable, so a rejected move never leaves a
dangling coroutine. A second module trying to move while one is active raises
`ClusterBusyError` — the orchestrator decides what to do; motion never silently overlaps.

> ⚠️ **`active` is scoped per `Cluster`, not globally.** Two clusters means two active slots and
> two modules genuinely moving at once.
>
> Note also that `Cluster`'s interlock is currently justified by the **hub** constraint (one
> filament in the line, which is *per printer*) while the class is named for the **ESP32**
> grouping (shared step/dir bus, which is *per cluster*). Today those coincide — one printer,
> one cluster — so the interlock is correct. They diverge at M×N: a cluster feeding two printers
> would be over-restricted, and two modules in *different* clusters feeding the *same* printer
> would collide at the hub with nothing to stop them. Tracked as part of
> [#18](05-open-questions.md).

---

## Inventory app (`apps/inventory/`)

No longer "later" — the resolver runs on every `arm_job`.

```
Resolver:      propose(plan) -> dict<filament_index, ProposedRow>
ProposedRow:   index, material, color_hex, grams, module?, spool_id?, status: loaded|gap

FakeSpoolStore   in-memory, satisfies SpoolStore
SpoolmanStore    libs/spoolman — REST, and a SOFT dependency
```

**Spoolman is soft.** A store that cannot reach Spoolman returns empty/None and logs; it never
raises into the swap path. A swap must not fail because inventory is down.

---

## Prompt app (`apps/prompt/`)

The v0 human-in-the-loop bridge — the money-shot interaction.

```
PendingPrompt:  id, module_id, message, future
PromptBroker:   prompter_for(module_id) -> Prompter    # injected into ManualModule
                ask(module_id, message) -> str          # blocks the swap
                answer(prompt_id, text)                 # releases it
```

`ManualModule`'s async prompter is wired to `PromptBroker.ask`, which parks on a future until
the operator answers over HTTP. The swap loop genuinely blocks on a human — which is exactly
what a motor will do later, and why the seam doesn't change when the motor arrives.

---

## Transport (`system/infra/`)

```
MqttBus              publish(topic, payload) ; subscribe(topic, handler)
MqttPrinterLink      real; device/{serial}/request + /report, TLS + access code
SimulatedPrinterLink same Protocol, no broker
FtpsClient           implicit-TLS FTPS upload of the sliced 3MF
SimulatedFtpClient   same Protocol, no network
```

Grouped **by wire protocol, not by caller**. There is no `ClusterLink` yet — every module is a
`ManualModule`, so nothing needs a cluster transport. It appears when the ESP32 does.

---

## Value objects & enums

```
PrinterId, ClusterId, ModuleId : str aliases          types/ids.py
Report, ReportHandler                                 types/wire.py
FilamentRef    { index, material?, color?, spool_id? }
FilamentColor  { index, material?, color_hex?, grams? }
MoveResult     { ok, reason?, moved_mm? }
Spool, SpoolSpec

PrinterStage   IDLE | PRINTING | PAUSED | ERROR | FINISHED
PauseReason    CHANGE | USER | ERROR | UNKNOWN
ModuleState    IDLE | FEEDING | RETRACTING | FAULT | EMPTY
SwapState      WATCHING | UNLOADING | SELECTING | FEEDING | SENSING | RESUMING | FAULT
```

Errors are **typed, not status codes**: `PauseValidationError`, `SwapFault`, `JobParseError`,
`ClusterBusyError` (domain) and `BadRequestError`, `NotFoundError`, `ConflictError`,
`UnprocessableError` (HTTP).

---

## Relationships

```
Brain 1──* Printer            Brain 1──* Cluster         Brain 1──* Orchestrator (per active job)
Brain 1──1 ModuleRegistry     Brain 1──1 EventBus        Brain 1──1 PromptBroker
Brain 1──1 SpoolStore         Brain 1──1 Resolver

Cluster 1──≤16 Module         Module *──1 Cluster        Module 0..1──1 Spool

Printer 1──1 PrinterState     Printer 1──1 PrinterDriver Printer 1──1 PrinterLink
Orchestrator 1──1 PrinterControl   ← the seam, never the concrete Printer
Orchestrator 1──1 SwapPlan    SwapPlan 1──* PlannedSwap
PlannedSwap *──1 Module       ← resolved via ModuleRegistry by filament_index
```

`Printer` and `Module` never reference each other. A module has no idea a printer exists — which
is what makes `ManualModule` and a future `HardwareModule` interchangeable.

---

## A swap, traced through the objects

1. `MqttPrinterLink` receives a report → `Printer.on_report` sees `stage=PAUSED` → publishes
   `PauseEvent` on the `EventBus`.
2. `Orchestrator._on_event` → `on_pause`. If `sm.busy`, this is a stray pause → safe-hold.
3. `_validate(event)` against `plan.swaps[cursor]` — tag, ordinal cursor, and the line guard.
   Failure raises `PauseValidationError` → safe-hold + alert.
4. Under `_swap_lock`: resolve `next_module` via the injected resolver
   (`for_filament_index`, or the operator's confirmed assignment).
5. `SwapStateMachine.execute(ctx)`:
   `routine_unload()` + `old_module.retract(retract_mm)` → select → `next_module.start_feed()`
   → poll `filament_present()` (or await a pushed `SensorEvent`) → `stop()` on trip →
   `routine_confirm_resume()`.
6. `cursor += 1`, back to `WATCHING`. On `FINISH`, `FinishedEvent` → `Brain._on_finished`
   consumes spool grams.

Every module motion in step 5 goes through `Cluster.move()`, so two modules can never move on
one cluster at once.

---

## Simulate mode

`SimulatedPrinterLink` + `SimulatedFtpClient` + `ManualModule` satisfy the same protocols as the
real adapters, so the entire stack runs with no printer on the LAN and the whole test suite runs
in seconds. This is not a test harness bolted on — it is what the seams are *for*.

```bash
cd server && AMSX_SIMULATE=1 AMSX_CONFIG=config/ams.sim.json uv run amsx
```

---

## Deferred / open

Tracked in [05-open-questions.md](05-open-questions.md).

- No `HardwareModule` and no `ClusterLink` — Phase 1, when the ESP32 exists.
- `ModuleRegistry.for_material()` — inventory-driven selection (Phase 4).
- `A1Driver` specifics (#10/#11); exact `PrinterDriver` payloads still `# PHASE-0: verify` (#1).
- Whether `PauseEvent` carries enough for richer validation (#3, #29).
- Concurrency at M×N: arbitration when two `Orchestrator`s want the same `Module`, **and** the
  cluster-vs-hub scoping noted under `Cluster` above (#18).
