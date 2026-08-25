# Server — the HTTP layer

How a request becomes a response: `routes/` → `Depends` → an app's `service.py` → its
`view.py` → JSON → the frontend's generated TypeScript. The structural rules are in
[00-architecture.md](00-architecture.md); this is the HTTP surface specifically.

## The shape of a handler

```python
# routes/printers.py
router = APIRouter(prefix="/api/printers", tags=["printers"])


@router.get("/{printer_id}")
async def get_printer(brain: BrainDep, printer_id: str) -> PrinterState:
    printer = brain.printers.get(printer_id)
    if printer is None:
        raise NotFoundError(f"unknown printer {printer_id!r}")
    return PrinterState.from_printer(printer)
```

Four things are happening, and each replaces something you would otherwise write by hand:

| Written | Replaces |
|---|---|
| `brain: BrainDep` | Middleware that hangs a service off `req` |
| `printer_id: str` | Reading and coercing a path param |
| `-> PrinterState` | `res.json(...)`, plus the OpenAPI response schema |
| `raise NotFoundError(...)` | `res.status(404).json({...})` |

A request body works the same way: annotate it and validation is done.

```python
@router.post("")
async def create_spool(brain: BrainDep, body: SpoolCreate) -> Spool: ...
```

`body: SpoolCreate` **is** the validator. A malformed body 422s before the handler runs, with a
per-field error report. There is deliberately no `validateRequest`-style middleware: FastAPI
derives the request schema from that annotation, and a validator hidden in middleware would be
invisible to the schema generator — the generated TypeScript would degrade to `any`.

## Dependencies (`system/middlewares/`)

`Depends` is the seam that let the routes split at all. Every handler used to be a closure over
a `_brain()` local inside one 445-line `create_app`, and a closure cannot be moved to another
module.

| Dependency | Gives you | Raises |
|---|---|---|
| `BrainDep` | The running `Brain` | — |
| `SimOnlyDep` | The `Brain`, in simulate mode only | `409` otherwise |
| `require_printer(brain, id)` | — | `404` if unknown |
| `armed_orchestrator(brain, id)` | The printer's `Orchestrator` | `404` unknown / `409` nothing armed |

Declaring a precondition beats re-checking it: a handler taking `SimOnlyDep` cannot run against
real hardware, and that is visible in its signature rather than buried in its body.

These are FastAPI dependencies, **not** ASGI middleware. The difference matters: `add_middleware`
runs on every request, in order, and knows nothing about the route; `Depends` runs per route,
composes, and is typed. Only CORS is true middleware here.

## Errors

Routes raise typed errors; one handler in `system/infra/http/app.py` renders them.

| Raise | Status |
|---|---|
| `BadRequestError` | 400 |
| `NotFoundError` | 404 |
| `ConflictError` | 409 |
| `UnprocessableError` | 422 |

All descend from `HTTPError` → `AmsxError`. To add one, subclass `HTTPError` with a
`status_code`; the handler needs no change. `spools.py` does exactly that for a 502 when the
inventory store is unreachable.

The response body is FastAPI's own shape — `{"detail": "..."}` — so clients see no difference
from the `HTTPException` calls these replaced. An optional `expose` dict is merged in for
structured context.

Domain errors (`SwapFault`, `PauseValidationError`, `JobParseError`, `ClusterBusyError`) are
**not** HTTP errors. They are caught at the route boundary and translated, because a 3MF that
fails to parse is a 400 to the operator but a domain fact to the parser.

## Views

Response and request models live in each app's `view.py`, next to the logic that produces them.
Shapes belonging to no app — `Health`, `OkResponse`, `DeleteResult` — live in
`system/infra/http/view.py`.

A view is the **wire contract** and nothing else. It may know a domain object well enough to
convert one:

```python
@classmethod
def from_domain(cls, s: DomainSpool) -> Spool: ...
```

but the domain must never import a view. `types/` holds frozen dataclasses with no validation;
`view.py` holds Pydantic models that validate at the edge. That split is deliberate — it's the
same instinct as not running zod on objects that never left your process.

## Routers and `/docs`

One module per resource, each exposing `router`. `routes/__init__.py` collects them into `ALL`,
in the order they appear in `/docs`. Mounting happens in `system/infra/http/app.py`.

Every router sets `tags=[...]`, which turns `/docs` from a flat list of 20 operations into
collapsible per-resource sections, and groups the generated TypeScript client the same way:

| Tag | Ops | | Tag | Ops |
|---|---|---|---|---|
| `printers` | 3 | | `prompts` | 2 |
| `jobs` | 4 | | `loadout` | 2 |
| `spools` | 4 | | `sim` | 2 |
| `health` · `orchestrator` · `modules` | 1 each | | | |

Three views of the same schema are served: **`/docs`** (Swagger UI — interactive, with a
*Try it out* button that fires real requests), **`/redoc`** (read-only, better for reading down
the list), and **`/openapi.json`** (the raw schema).

`routes/sim` is deliberately **not** in `ALL`. It is mounted separately, only when the Brain is
in simulate mode, so a real deployment has no route that can fake a printer pause.

## The generated contract

TypeScript types are generated, never written:

```bash
cd frontend && npm run gen:api
```

That dumps the schema (`scripts/dump_openapi.py`, which imports the app directly — no running
server, no ports) and runs `openapi-typescript` over it into `frontend/api/types.generated.ts`.

**Change a `view.py` and you must regenerate.** The generated file is committed, so a stale one
shows up as a diff. `dump_openapi.py` never starts the Brain — the lifespan never runs — so
codegen is deterministic and works in CI.

This is why the annotation is the validator rather than a middleware: the annotations *are* the
contract, and the frontend's types are downstream of them.

## Adding an endpoint

1. Add the response model to the owning app's `view.py`.
2. Add the handler to `routes/<resource>.py` — take `BrainDep`, annotate the return type.
3. If the resource is new, create the module and add its `router` to `ALL`.
4. `uv run pytest && uv run lint-imports`.
5. `cd frontend && npm run gen:api`, and commit the regenerated types.

## See also

- [00-architecture.md](00-architecture.md) — the folder architecture and layer contracts
- [frontend/01-api-layer.md](../frontend/01-api-layer.md) — the consuming side of this contract
