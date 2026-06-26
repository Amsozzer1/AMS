# Plan: In-AMS Spool CRUD (create / edit / delete spools without leaving the app)

## Why

Today the operator can only *read* the Spoolman inventory and assign spools to modules.
When Spoolman is empty, every colour in a job shows as a "gap" and the operator has to leave
AMS for Spoolman's own UI to add spools. This plan adds create / edit / delete of spools
through AMS-X (proxying to the user's Spoolman), so the whole loadout can be built in-app.

## Global Constraints (bind every task — copy verbatim into reviewer prompts)

1. **CRUD writes are FOREGROUND, not SOFT.** The existing read/poll methods (`list_spools`,
   `loaded_in`, `match`, `set_module`, `consume`) are SOFT — they swallow errors and return
   empty/None so the swap path never breaks. The NEW methods (`create_spool`, `update_spool`,
   `delete_spool`) are user-initiated actions where the operator is waiting on the result, so
   they MUST surface failure: do NOT wrap them in `_soft`. A missing spool raises `KeyError`;
   any other store/transport failure propagates. The API layer maps those to HTTP status.
2. **Do not change the user's Spoolman.** We only call its documented REST API
   (`POST/PATCH/DELETE /spool`, `POST /filament`, `POST/GET /vendor`). No schema migrations,
   no config changes, no writes to the cloned `Spoolman/` reference dir (gitignored).
3. **`ams_module` convention is unchanged:** spool→module lives in Spoolman `extra.ams_module`
   as a JSON-encoded string (`json.dumps(module_id or "")`), decoded with `json.loads`. Reuse
   the existing `MODULE_FIELD = "ams_module"` constant and `_spool()` decoder in
   `inventory/spoolman.py`. When creating a spool with a module, set it in the POST `extra`
   directly — no separate `set_module` round-trip.
4. **`color_hex` formats:** our `Spool.color_hex` is bare 6-hex `RRGGBB` UPPERCASE (no `#`).
   Spoolman's filament `color_hex` is also bare hex (6–8 chars, no `#`). On the wire strip any
   leading `#` and send `RRGGBB`. The frontend `<input type="color">` yields `#rrggbb`; strip it.
5. **The SpoolStore Protocol is the only seam the Brain/API depend on.** Every method added to
   the Protocol is mirrored in BOTH `FakeSpoolStore` (in-memory, for tests/sim) and
   `SpoolmanStore` (real httpx). Tests for the Protocol-level behaviour use `FakeSpoolStore`.
6. **No new heavy deps.** stdlib + existing `httpx` / `pydantic` / `fastapi` only.

## Shared design decisions (made up-front; implementers follow, don't re-litigate)

- **Spool-centric, not filament-centric.** The operator thinks in spools ("a red PLA spool").
  `create_spool` takes filament attributes and creates-or-reuses the underlying Spoolman
  `filament` record under the hood, then creates the `spool`. No separate filament/vendor CRUD
  surface in v0.
- **Filament reuse is EXACT-match only** (no fuzzy colour reuse — that would mis-attach spools).
  Reuse an existing filament only when material + `color_hex` (uppercase compare) + vendor_id +
  name all match exactly; otherwise create a new filament.
- **Density defaults by material** (g/cm³), diameter always `1.75`:
  `PLA 1.24, PETG 1.27, ABS 1.04, ASA 1.07, TPU 1.21, PC 1.20, PA 1.14, NYLON 1.14, PVA 1.23,
  HIPS 1.04`; default `1.24` for anything else (case-insensitive lookup on the material string).
- **`SpoolSpec`** (new frozen dataclass in `types.py`) is the create payload:
  `material: str`, `color_hex: str | None = None`, `name: str | None = None`,
  `vendor: str | None = None`, `initial_g: float = 1000.0`, `module: ModuleId | None = None`,
  `location: str | None = None`.
- **Update** changes only `remaining_g`, `location`, `archived` (each optional / "leave alone"
  when `None`). Module (re)assignment stays on the existing `set_module` / loadout PUT seam —
  do NOT add module to `update_spool`.
- **Delete is a HARD delete** (`DELETE /spool/{id}`). Archiving is reachable via
  `update_spool(archived=True)`.
- **Error contract:** missing spool → `KeyError(spool_id)`; other failures propagate
  (`httpx.HTTPStatusError` etc.). API maps: `KeyError` → 404, anything else → 502.

---

## Task 1 — Backend store: create / update / delete on the SpoolStore seam

**Files:** `server/src/amsx/types.py`, `server/src/amsx/inventory/__init__.py`,
`server/src/amsx/inventory/spoolman.py`, `server/tests/` (new test module).

### 1a. `types.py` — add `SpoolSpec`

```python
@dataclass(frozen=True)
class SpoolSpec:
    """Operator's request to create one spool (AMS resolves/creates the Spoolman filament)."""
    material: str
    color_hex: str | None = None        # bare 6-hex RRGGBB (no '#'); upper/lower accepted
    name: str | None = None
    vendor: str | None = None           # vendor display name; created-or-reused
    initial_g: float = 1000.0
    module: ModuleId | None = None
    location: str | None = None
```

### 1b. `inventory/__init__.py` — Protocol + FakeSpoolStore

Add to the `SpoolStore` Protocol (after `consume`):
```python
async def create_spool(self, spec: SpoolSpec) -> Spool: ...
async def update_spool(
    self, spool_id: str, *,
    remaining_g: float | None = None,
    location: str | None = None,
    archived: bool | None = None,
) -> Spool: ...
async def delete_spool(self, spool_id: str) -> None: ...
```
Import `SpoolSpec` from `..types`. Update `__all__` is not required (only `FakeSpoolStore`,
`SpoolStore` are exported today — leave as is).

`FakeSpoolStore` (in-memory, never raises on transport — it has none):
- Give it a monotonic id counter (start spool ids + filament ids from where seeded data leaves
  off, or a simple `self._next = 1` bumped past any seeded numeric ids; ids are strings).
- `create_spool(spec)`: synthesize a `Spool(id=<new>, filament_id=<new>, material=spec.material,
  color_hex=spec.color_hex.upper() if set else None, name=spec.name, remaining_g=spec.initial_g,
  module=spec.module, archived=False)`, store it, return it.
- `update_spool(spool_id, ...)`: `KeyError(spool_id)` if absent; else `dataclasses.replace` only
  the provided (non-None) fields; store + return the new Spool.
- `delete_spool(spool_id)`: `KeyError(spool_id)` if absent; else `del`.

### 1c. `inventory/spoolman.py` — real implementation

Add a module-level material→density map and `_DIAMETER = 1.75` (values from "Shared design
decisions"). Add a `_strip_hash(hex)` helper (return `None` for falsy, else `value.lstrip("#")`).

`create_spool(self, spec)` — NOT soft (let errors propagate):
1. **vendor_id**: if `spec.vendor` truthy → `GET /vendor`, find first whose `name` matches
   case-insensitively; if none, `POST /vendor {"name": spec.vendor}` and take `id`. Else `None`.
2. **filament_id**: `GET /filament` with `params={"material": spec.material}` (only when material
   set). From the results, reuse the first whose `color_hex` (uppercase, `_strip_hash`) ==
   `spec.color_hex` uppercased AND `vendor.id` == vendor_id AND `name` == `spec.name` (treat
   missing/None on both sides as equal). If none match, `POST /filament` with
   `{"name": spec.name, "vendor_id": vendor_id, "material": spec.material,
     "color_hex": _strip_hash(spec.color_hex), "density": <density for material>,
     "diameter": 1.75}` (drop None-valued keys) and take `id`.
3. **spool**: `POST /spool` with `{"filament_id": <int>, "initial_weight": spec.initial_g,
   "remaining_weight": spec.initial_g, "location": spec.location or self._cfg.active_location,
   "extra": {MODULE_FIELD: json.dumps(spec.module or "")}}` (drop None location). `raise_for_status`.
4. Return `self._spool(resp.json())` (the POST returns the full Spool with nested filament).

`update_spool(self, spool_id, *, remaining_g=None, location=None, archived=None)` — NOT soft:
- Build body from only the non-None args: `remaining_weight`, `location`, `archived`.
- `PATCH /spool/{spool_id}` with that body. If the response is 404, raise `KeyError(spool_id)`.
  Otherwise `raise_for_status()` then return `self._spool(resp.json())`.

`delete_spool(self, spool_id)` — NOT soft:
- `DELETE /spool/{spool_id}`. 404 → `KeyError(spool_id)`; else `raise_for_status()`; return None.

(Map 404→KeyError by checking `resp.status_code == 404` before `raise_for_status`.)

### 1d. Tests (`server/tests/test_inventory_crud.py`)

- FakeSpoolStore: create returns a Spool with the spec's fields + a fresh id; it then appears in
  `list_spools`; update changes only the named fields and raises `KeyError` on a missing id;
  delete removes it and raises `KeyError` on a missing id.
- SpoolmanStore: drive it against a mocked transport (`httpx.MockTransport` handing the
  `AsyncClient` canned responses) — assert the request method/URL/body for: create with a NEW
  filament+vendor (POST /vendor, POST /filament, POST /spool), create REUSING an existing exact
  filament (no POST /filament), update (PATCH body has only the changed keys), delete (DELETE),
  and that a 404 PATCH/DELETE raises `KeyError`. Build the store with a `SpoolmanConfig` whose
  `base_url` is any value; inject the `MockTransport` into its `httpx.AsyncClient` (the simplest
  way: let `SpoolmanStore.__init__` accept an optional `transport` kwarg passed through to
  `AsyncClient`, defaulting to None — a small, test-only seam that does not change prod behaviour).

**Acceptance:** `cd server && uv run pytest -q` green; `uv run ruff check` + `uv run ruff format
--check` clean.

---

## Task 2 — API: spool CRUD + module-list endpoints

**Files:** `server/src/amsx/api/__init__.py`, `server/tests/` (extend API tests).

Add (near the existing spool endpoints):

- `GET /api/modules` → `[{"id", "cluster_id", "filament_index"}]` from `brain.config.modules`
  (so the frontend add-spool form has a module dropdown without a printer context).
- `POST /api/spools` — body parsed into a `SpoolSpec`. Accept a JSON object with keys matching
  `SpoolSpec` (material required; others optional). Returns the created spool dict (the existing
  `_spool_dict`). On `Exception` → 502 with the message; missing material / bad body → 422 (let
  FastAPI/pydantic validate via a small `pydantic.BaseModel` request model `SpoolCreate` mirroring
  `SpoolSpec`, then build the `SpoolSpec` from it).
- `PATCH /api/spools/{spool_id}` — body `SpoolUpdate` model (`remaining_g`, `location`,
  `archived`, all optional). Calls `update_spool`. `KeyError` → 404; other `Exception` → 502.
  Returns the updated spool dict.
- `DELETE /api/spools/{spool_id}` — calls `delete_spool`. `KeyError` → 404; other → 502.
  Returns `{"ok": true, "id": spool_id}`.

Keep `_spool_dict` as the single serializer. Do NOT make these endpoints SOFT — surface 502 so the
UI can show a real error (per Global Constraint 1).

**Tests:** use FastAPI `TestClient` with a `Brain` whose `store` is a `FakeSpoolStore` (follow the
existing API test setup). Cover: POST creates and the spool then appears in `GET /api/spools`;
PATCH changes weight; PATCH/DELETE on an unknown id → 404; DELETE removes it; `GET /api/modules`
returns the configured ids.

**Acceptance:** `cd server && uv run pytest -q` green; ruff clean.

---

## Task 3 — Frontend: spool management UI

**Files:** `frontend/lib/api.ts`, `frontend/app/components/SpoolInventory.tsx`,
`frontend/app/globals.css` (styles only).

`lib/api.ts`:
- Types `SpoolCreate` (`material: string; color_hex?: string; name?: string; vendor?: string;
  initial_g?: number; module?: string; location?: string`), `SpoolUpdate`
  (`remaining_g?: number; location?: string; archived?: boolean`), and `ModuleInfo`
  (`id: string; cluster_id: string; filament_index: number | null`).
- Fns: `listModules()`, `createSpool(body)`, `updateSpool(id, body)`, `deleteSpool(id)` — mirror
  the existing fetch-helper style (POST/PATCH/DELETE; throw `ApiError` with the server detail).

`SpoolInventory.tsx` — extend the existing read-only panel into a manager:
- Keep the polling list. Add an "Add spool" form (toggle/disclosure): material text, colour
  `<input type="color">`, optional name + vendor, initial grams (default 1000), module
  `<select>` populated from `listModules()`. Submit → `createSpool` → refetch.
- Per row: an edit affordance to change remaining grams + archive, a module `<select>` (assign via
  the existing loadout PUT is per-printer — instead drive module here through `createSpool`/edit;
  for an existing spool, reuse the loadout seam is out of scope — keep module assignment to the
  existing mapping/loadout panels). Concretely for v0: per-row actions = **edit remaining grams**,
  **archive** (`updateSpool({archived:true})`), and **delete** (`deleteSpool`, with a confirm).
- All writes show inline busy/error state and refetch on success. Empty/Spoolman-down states stay
  calm (existing behaviour). Strip the `#` from the colour input before sending.
- Styles: add to `globals.css` following the existing `.spool-*` / `.mapping-*` conventions; do
  not restyle unrelated components.

**Acceptance:** `cd frontend && npm run lint` (or the repo's lint script) clean; `npx tsc --noEmit`
passes. (No e2e here — backend tests cover behaviour; this task is UI wiring.)

---

## Out of scope (parked — do NOT build)

- Vendor/filament management screens (spool-centric create covers the need).
- Runout→backup-spool, colours>modules (separate edge-case backlog).
- Bulk import / barcode scan.
