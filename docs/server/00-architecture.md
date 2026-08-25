# Server — architecture

The Brain: a FastAPI app plus an async orchestrator that rides Bambu's own filament-change
routine over MQTT. This document is the **folder architecture** — what each package is for,
where a new thing goes, and the rules the layout enforces. The domain model it implements is
[10-domain-model.md](../10-domain-model.md); the swap sequence is [02-architecture.md](../02-architecture.md).

## Root layout

```
server/
├── amsx/           the package (this document)
├── config/         ams.example.json · ams.sim.json · ams.local.json (gitignored)
├── tests/          pytest — outside the package, so tests never ship in the wheel
├── scripts/        run-by-hand drivers: dump_openapi.py, check_*.py (live hardware)
└── pyproject.toml  deps, tool config, and the import-linter contracts
```

There is no `src/`. The src-layout exists to force imports to resolve against the *installed*
package so packaging bugs surface in tests — but `amsx` is installed editable and ships in
Docker, never to PyPI, so that guarantee was never being collected. It was one directory level
for nothing.

## The stack

Read top to bottom. **Each layer may import anything below it and nothing above it.**

| Layer | Package | Holds |
|---|---|---|
| 1 | `system/infra/http/app.py` | `create_app` — mounts the routers, CORS, lifespan, error handler |
| 2 | `routes/` | One module per resource, each an `APIRouter` |
| 3 | `system/middlewares/` | The `Depends` providers routes ask for by name |
| 4 | `system/brain.py` | Composition root — builds and wires every concrete class, once |
| 5 | `apps/` | The domain: printer · orchestration · job · module · inventory · prompt |
| 6 | `system/infra/mqtt/` · `system/infra/ftps/` · `libs/` | Adapters to the outside world |
| 7 | `events/` | `EventBus` + typed event payloads |
| 8 | `types/` | Value objects, ids, wire shapes, and **every seam** (`protocols.py`) |
| 9 | `enums/` · `errors/` · `config/` · `utils/` | Leaves. Import nothing from `amsx` |

This is not a convention — `import-linter` fails the build on a violation. Run it:

```bash
cd server && uv run lint-imports
```

Three contracts are enforced ([pyproject.toml](../../server/pyproject.toml)):

1. **Nothing imports upward** — the table above, as a layers contract.
2. **The kernel stays dependency-free** — `enums`, `errors`, `config`, `utils` are independent.
3. **Orchestration depends on seams, never implementations** — `apps.orchestration` may not
   import `apps.printer`, `system.*`, `libs`, or `routes`. This is what keeps the state machine
   testable against fakes, and it is why 138 tests run in under 3 seconds with no printer, no
   broker, and no network.

> Note the split inside `system/infra/http`: `app.py` mounts the routers so it sits at the very
> top, while `view.py` holds shapes the routes import so it sits below them. Same folder,
> opposite ends of the stack — `infra/` is grouped **by protocol, not by altitude**.

## The rules

**1. `__init__.py` is the door.** A package's `__init__.py` contains re-exports and nothing
else — no classes, no functions. Code lives in named siblings. A consumer writes
`from amsx.apps.printer import Printer` and learns nothing about which file it came from. This
is the same rule as the frontend's `index.ts`, and it is plain Python: `asyncio/__init__.py`
and `fastapi/__init__.py` both define zero classes.

**2. Imports are absolute.** Always `from amsx.types import Spool`, never `from ..types import`.
A relative import silently changes meaning the moment its file moves to a different depth, which
turns every refactor into a hazard. Absolute imports also read like the frontend's `@` aliases.

**3. Every seam lives in `types/protocols.py`.** All six — `Module`, `PrinterControl`,
`PrinterLink`, `FtpClient`, `PrinterDriver`, `SpoolStore` — in one file, so "what can I swap
out, and what would I have to implement?" is one file rather than a hunt. Each package that
implements one re-exports it, so it still reads beside its implementations.

**4. Protocols are structural.** An implementation satisfies a `Protocol` by having the right
methods, not by inheriting. `ManualModule` names no base class at all and still satisfies
`Module`. Never add a base class to "implement" a protocol.

**5. Errors are typed, not status codes.** A route raises `NotFoundError("unknown printer")`,
not `HTTPException(status_code=404, ...)`. The status code lives with the error type, and the
domain stays free of FastAPI imports.

**6. Stubs carry `@todo`.** Never a hand-written `raise NotImplementedError`. See
[rules/02-stubs.md](../rules/02-stubs.md).

**7. Unverified hardware facts are marked.** A payload we have not confirmed against a real
printer carries `# PHASE-0: verify` and a pointer at the open question. We never fabricate a
"confirmed" payload. When a live check settles one, the finding replaces the comment.

## What is an app

An `app` is one domain concern. Six exist: `printer`, `orchestration`, `job`, `module`,
`inventory`, `prompt`. Each has the same shape:

```
apps/printer/
├── __init__.py    re-exports only — the door
├── service.py     the logic
├── view.py        its wire shapes (Pydantic response/request models)
└── drivers.py     extra modules as the app needs them
```

`service.py` is domain logic and knows nothing about HTTP. `view.py` is the only place in an app
that imports Pydantic. Apps are siblings and may import each other — the job's plan feeds the
inventory resolver — so `apps` is one layer rather than an independence contract. The single
exception is `orchestration`, which contract #3 pins to the seams.

## Where things live

| Thing | Home | Test |
|---|---|---|
| Domain logic for one concern | `apps/<name>/service.py` | Does it survive with no HTTP? |
| A response or request body | `apps/<name>/view.py` | Does it cross the network? |
| A shape belonging to no app | `system/infra/http/view.py` | `Health`, `OkResponse`, `DeleteResult` |
| An HTTP handler | `routes/<resource>.py` | One file per resource, not per route |
| Something every route needs | `system/middlewares/` | Is it a `Depends` provider? |
| A value object crossing layers | `types/` | Does more than one layer name it? |
| A swappable interface | `types/protocols.py` | Always. No exceptions |
| A closed set of states | `enums/` | Is it a `StrEnum`? |
| An exception | `errors/` | Domain → `domain.py`, HTTP → `http.py` |
| A third-party client | `libs/<vendor>/` | Would it exist without this project? |
| A protocol adapter | `system/infra/<protocol>/` | Named by wire protocol, not by caller |
| Wiring two concrete things together | `system/brain.py` | Is it construction, not behaviour? |
| A constant used by one module | beside its only caller | Never hoist it to a shared `consts/` |

That last row is deliberate. Every module-level constant in this codebase is either private
(`_PAUSE_RE`) or bound to a single caller (`PLATE_GCODE_PATH`). A global `consts/` would
separate each one from the only function that reads it.

## Simulate mode

The whole stack runs with no printer on the LAN. `SimulatedPrinterLink` and `SimulatedFtpClient`
satisfy the same protocols as the real adapters, and `ManualModule` puts a human where a motor
will go. This is why the tests need no hardware.

```bash
cd server
AMSX_SIMULATE=1 AMSX_CONFIG=config/ams.sim.json uv run amsx
```

The `sim` router — which injects a filament-change pause and trips the printer's sensor — is
**mounted only in simulate mode**. A real deployment does not merely guard those endpoints; it
does not serve them. `simulate=True` exposes 16 paths, `simulate=False` exposes 14.

## Commands

All from `server/`.

```bash
uv run amsx                  # start (simulate mode, 127.0.0.1:8000)
AMSX_RELOAD=1 uv run amsx    # + hot reload
uv run pytest                # 138 tests, ~3s, no hardware
uv run ruff check . && uv run ruff format .
uv run lint-imports          # the three contracts above
uv run python scripts/dump_openapi.py    # regenerate the frontend's contract
```

`python -m amsx` does not work — the entrypoint is `python -m amsx.system`. Use `uv run amsx`.

## Target tree

```
amsx/
├── system/
│   ├── __main__.py            entrypoint + logging setup
│   ├── brain.py               composition root
│   ├── middlewares/           context.py (BrainDep) · guards.py
│   └── infra/
│       ├── http/              app.py (create_app) · view.py (shared acks)
│       ├── mqtt/              bus.py (MqttBus) · link.py (PrinterLink impls)
│       └── ftps/              tls.py (_ImplicitFTPTLS) · client.py
├── routes/                    health · printers · jobs · prompts · orchestrator
│                              modules · spools · loadout · sim
├── apps/
│   ├── printer/               service · drivers · view
│   ├── orchestration/         service (the state machine) · view
│   ├── job/                   service (3MF parser) · view
│   ├── module/                service (ManualModule, Cluster) · view
│   ├── inventory/             service · resolver · view
│   └── prompt/                service (PromptBroker) · view
├── libs/spoolman/             client.py
├── events/                    EventBus + typed payloads
├── types/                     ids · wire · filament · spool · swap · protocols
├── enums/                     printer · module · swap
├── errors/                    base · domain · http
├── config/                    schema · loader
└── utils/                     todo
```

## See also

- [01-http-layer.md](01-http-layer.md) — routes, views, `Depends`, errors, and the generated contract
- [10-domain-model.md](../10-domain-model.md) — the classes this structure implements
- [rules/01-separation-of-concerns.md](../rules/01-separation-of-concerns.md) — why the layering is enforced
