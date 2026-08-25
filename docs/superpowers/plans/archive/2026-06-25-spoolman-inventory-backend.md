> ## ✅ COMPLETED — archived
> Implemented by `45b5363..966a4f7` on `main` (Tasks 1–5, plus the resolver/API/orchestration
> follow-ons). Kept as a historical record of what was decided and why — **not** a to-do list.
> Current truth lives in the code and `git log`, not here. See ../../README.md for the lifecycle.

# Spoolman Inventory — Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Give the Brain color-aware swaps — read a sliced job's color plan, resolve each color to a loaded module via a (soft) Spoolman inventory, expose a mapping/assignment API, sync the printer's external-spool filament, and decrement usage.

**Architecture:** A new `amsx.inventory` package wraps Spoolman behind a `SpoolStore` Protocol (`SpoolmanStore` real + `FakeSpoolStore` for tests). `job/` gains a color-plan parser. `A1Driver`/`Printer` gain `vt_tray` read+write. A `Resolver` pre-fills an index→module mapping that the operator confirms over a proxy API. Spoolman is a SOFT dependency — its absence never blocks printing.

**Tech Stack:** Python 3.11, FastAPI, asyncio, httpx (new), defusedxml (new), pydantic, paho-mqtt, pytest, ruff.

## Global Constraints

- Every not-yet-implemented function uses the `@todo` decorator from `amsx.utils` — never a hand-written `raise NotImplementedError`. This plan implements everything; do not leave stubs.
- `ruff check src/ tests/` must pass; `pytest -q` must pass after every task.
- Spoolman is a **SOFT** dependency: any Spoolman/network error degrades gracefully (log + return empty/None), it never raises out to the print/swap path.
- Spool `extra` field values are **JSON-encoded strings** on the wire: read with `json.loads`, write with `json.dumps` (e.g. `extra={"ams_module": "\"m2\""}`).
- `vt_tray` write (confirmed live A1): `ams_filament_setting`, `ams_id=255`, `tray_id=254`, `slot_id=0`, `tray_color` = 8-hex `RRGGBBAA` UPPERCASE. Read back to confirm (A1 NACKs nothing).
- Color hex in our types is **6-hex `RRGGBB` UPPERCASE, no alpha**. Convert at the Spoolman/`vt_tray` boundaries.
- Parse 3mf XML with **`defusedxml`** (never stdlib `xml.etree`) — uploaded files are untrusted (XXE / billion-laughs). Metadata parsing is best-effort: any parse failure degrades to index-only.
- Commit after every task with a `feat(...)`/`test(...)` message ending with the repo's `Co-Authored-By` trailer.

---

### Task 1: Config + inventory value objects + color-plan types

**Files:**
- Modify: `server/src/amsx/config/__init__.py` (add `SpoolmanConfig`, `Config.spoolman`)
- Modify: `server/src/amsx/types.py` (add `Spool`, `FilamentColor`; extend `PlannedSwap`, `SwapPlan`)
- Test: `server/tests/test_types_config.py`

**Interfaces:**
- Produces:
  - `SpoolmanConfig(base_url: str = "http://localhost:7912/api/v1", active_location: str | None = None, timeout: float = 5.0, enabled: bool = True)`; `Config.spoolman: SpoolmanConfig`.
  - `Spool(id: str, filament_id: str, material: str | None, color_hex: str | None, name: str | None, remaining_g: float | None, module: ModuleId | None, archived: bool = False)` (frozen). `color_hex` is 6-hex UPPERCASE.
  - `FilamentColor(index: int, material: str | None, color_hex: str | None, grams: float | None)` (frozen).
  - `PlannedSwap` gains `material: str | None = None`, `color_hex: str | None = None`.
  - `SwapPlan` gains `base: FilamentColor | None = None` and `colors: list[FilamentColor] = field(default_factory=list)` (distinct used filaments, base first).

- [x] **Step 1: Write the failing test**

```python
# server/tests/test_types_config.py
from amsx.config import Config, SpoolmanConfig, load_config
from amsx.types import Spool, FilamentColor, PlannedSwap, SwapPlan


def test_spoolman_config_defaults():
    c = Config()
    assert c.spoolman.base_url == "http://localhost:7912/api/v1"
    assert c.spoolman.enabled is True
    assert c.spoolman.active_location is None


def test_spool_and_color_value_objects():
    s = Spool(id="7", filament_id="3", material="PLA", color_hex="FF0000",
              name="Red", remaining_g=412.0, module="m2")
    assert s.module == "m2" and s.archived is False
    fc = FilamentColor(index=5, material="PLA", color_hex="FF0000", grams=1.14)
    assert fc.index == 5


def test_plan_carries_colors():
    plan = SwapPlan(
        swaps=[PlannedSwap(seq=1, filament_index=5, tag="swap-001", layer=2,
                           line=10, material="PLA", color_hex="FF0000")],
        base=FilamentColor(index=1, material="PLA", color_hex="FFFFFF", grams=0.36),
        colors=[FilamentColor(1, "PLA", "FFFFFF", 0.36), FilamentColor(5, "PLA", "FF0000", 1.14)],
    )
    assert plan.swaps[0].color_hex == "FF0000"
    assert plan.base.color_hex == "FFFFFF"
    assert len(plan.colors) == 2
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_types_config.py -v`
Expected: FAIL (ImportError: cannot import name `SpoolmanConfig` / `Spool`).

- [x] **Step 3: Implement the types**

In `server/src/amsx/types.py`, add to the value-objects section:

```python
@dataclass(frozen=True)
class Spool:
    """One physical spool from the inventory (Spoolman), flattened for the Brain.

    `color_hex` is 6-hex RRGGBB UPPERCASE (no alpha). `module` is which AMS module it's loaded
    in (from Spoolman's `extra.ams_module`), or None if not loaded.
    """

    id: str
    filament_id: str
    material: str | None = None
    color_hex: str | None = None
    name: str | None = None
    remaining_g: float | None = None
    module: ModuleId | None = None
    archived: bool = False


@dataclass(frozen=True)
class FilamentColor:
    """One filament used by a job: the slicer index + its colour/material + grams used."""

    index: int
    material: str | None = None
    color_hex: str | None = None
    grams: float | None = None
```

Extend `PlannedSwap` (add two fields after `line`):

```python
    material: str | None = None
    color_hex: str | None = None
```

Extend `SwapPlan`:

```python
    base: "FilamentColor | None" = None
    colors: list["FilamentColor"] = field(default_factory=list)
```

In `server/src/amsx/config/__init__.py`, add:

```python
class SpoolmanConfig(BaseModel):
    enabled: bool = True
    base_url: str = "http://localhost:7912/api/v1"
    active_location: str | None = None  # if set, only spools in this Spoolman location are "in the AMS"
    timeout: float = 5.0
```

and add to `Config`: `spoolman: SpoolmanConfig = Field(default_factory=SpoolmanConfig)`.

- [x] **Step 4: Run tests to verify they pass**

Run: `cd server && uv run pytest tests/test_types_config.py -v && uv run ruff check src/ tests/`
Expected: PASS, lint clean.

- [x] **Step 5: Commit**

```bash
git add server/src/amsx/types.py server/src/amsx/config/__init__.py server/tests/test_types_config.py
git commit -m "feat(types): Spool/FilamentColor inventory value objects + SpoolmanConfig"
```

---

### Task 2: `SpoolStore` Protocol + `FakeSpoolStore`

**Files:**
- Create: `server/src/amsx/inventory/__init__.py`
- Test: `server/tests/test_inventory_fake.py`

**Interfaces:**
- Consumes: `Spool` (Task 1), `ModuleId`.
- Produces — the `SpoolStore` Protocol:
  ```python
  async def list_spools(self, *, include_archived: bool = False) -> list[Spool]: ...
  async def get_spool(self, spool_id: str) -> Spool | None: ...
  async def loaded_in(self, module_id: ModuleId) -> Spool | None: ...
  async def set_module(self, spool_id: str, module_id: ModuleId | None) -> None: ...
  async def match(self, material: str | None, color_hex: str | None) -> list[Spool]: ...
  async def consume(self, spool_id: str, grams: float) -> None: ...
  async def ensure_module_field(self) -> None: ...
  ```
  and `FakeSpoolStore(spools: list[Spool] | None = None)` implementing it in-memory (used by every other task's tests).

- [x] **Step 1: Write the failing test**

```python
# server/tests/test_inventory_fake.py
import pytest
from amsx.inventory import FakeSpoolStore, SpoolStore
from amsx.types import Spool

pytestmark = pytest.mark.asyncio


def _store():
    return FakeSpoolStore([
        Spool(id="1", filament_id="10", material="PLA", color_hex="FFFFFF", name="White", remaining_g=900, module="m1"),
        Spool(id="2", filament_id="11", material="PLA", color_hex="FF0000", name="Red", remaining_g=400, module="m2"),
        Spool(id="3", filament_id="12", material="PLA", color_hex="FF0000", name="Red2", remaining_g=50, module=None),
    ])


async def test_is_a_spoolstore():
    assert isinstance(_store(), SpoolStore)


async def test_loaded_in_and_set_module():
    s = _store()
    assert (await s.loaded_in("m2")).id == "2"
    await s.set_module("3", "m3")
    assert (await s.loaded_in("m3")).id == "3"
    await s.set_module("2", None)
    assert await s.loaded_in("m2") is None


async def test_match_by_material_and_color():
    s = _store()
    reds = await s.match("PLA", "FF0000")
    assert {sp.id for sp in reds} == {"2", "3"}


async def test_consume_decrements():
    s = _store()
    await s.consume("2", 100)
    assert (await s.get_spool("2")).remaining_g == 300
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_inventory_fake.py -v`
Expected: FAIL (module `amsx.inventory` not found).

- [x] **Step 3: Implement the Protocol + fake**

```python
# server/src/amsx/inventory/__init__.py
"""inventory — spool catalog behind a SpoolStore seam (SpoolmanStore real, FakeSpoolStore tests).

The Brain depends ONLY on `SpoolStore`. Spoolman is a SOFT dependency: a real store that can't
reach Spoolman returns empty/None and logs, never raising into the swap path.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Protocol, runtime_checkable

from ..types import ModuleId, Spool

__all__ = ["SpoolStore", "FakeSpoolStore"]


@runtime_checkable
class SpoolStore(Protocol):
    async def list_spools(self, *, include_archived: bool = False) -> list[Spool]: ...
    async def get_spool(self, spool_id: str) -> Spool | None: ...
    async def loaded_in(self, module_id: ModuleId) -> Spool | None: ...
    async def set_module(self, spool_id: str, module_id: ModuleId | None) -> None: ...
    async def match(self, material: str | None, color_hex: str | None) -> list[Spool]: ...
    async def consume(self, spool_id: str, grams: float) -> None: ...
    async def ensure_module_field(self) -> None: ...


class FakeSpoolStore:
    """In-memory SpoolStore for tests and the simulate path."""

    def __init__(self, spools: list[Spool] | None = None) -> None:
        self._by_id: dict[str, Spool] = {s.id: s for s in (spools or [])}

    async def list_spools(self, *, include_archived: bool = False) -> list[Spool]:
        return [s for s in self._by_id.values() if include_archived or not s.archived]

    async def get_spool(self, spool_id: str) -> Spool | None:
        return self._by_id.get(spool_id)

    async def loaded_in(self, module_id: ModuleId) -> Spool | None:
        return next((s for s in self._by_id.values() if s.module == module_id), None)

    async def set_module(self, spool_id: str, module_id: ModuleId | None) -> None:
        s = self._by_id.get(spool_id)
        if s is not None:
            self._by_id[spool_id] = replace(s, module=module_id)

    async def match(self, material: str | None, color_hex: str | None) -> list[Spool]:
        out = []
        for s in self._by_id.values():
            if material and s.material != material:
                continue
            if color_hex and (s.color_hex or "").upper() != color_hex.upper():
                continue
            out.append(s)
        return out

    async def consume(self, spool_id: str, grams: float) -> None:
        s = self._by_id.get(spool_id)
        if s is not None and s.remaining_g is not None:
            self._by_id[spool_id] = replace(s, remaining_g=max(s.remaining_g - grams, 0.0))

    async def ensure_module_field(self) -> None:
        return None
```

- [x] **Step 4: Run tests + lint**

Run: `cd server && uv run pytest tests/test_inventory_fake.py -v && uv run ruff check src/`
Expected: PASS, clean.

- [x] **Step 5: Commit**

```bash
git add server/src/amsx/inventory/__init__.py server/tests/test_inventory_fake.py
git commit -m "feat(inventory): SpoolStore protocol + FakeSpoolStore"
```

---

### Task 3: `SpoolmanStore` (httpx) — the real, soft inventory

**Files:**
- Create: `server/src/amsx/inventory/spoolman.py`
- Modify: `server/pyproject.toml` (add `httpx` dependency)
- Test: `server/tests/test_inventory_spoolman.py`

**Interfaces:**
- Consumes: `SpoolStore` shape (Task 2), `Spool`, `SpoolmanConfig`.
- Produces: `SpoolmanStore(cfg: SpoolmanConfig)` implementing `SpoolStore`. Maps Spoolman JSON →
  `Spool` (`material`/`color_hex` from the nested `filament`, `module` from `extra.ams_module`
  JSON-decoded). All HTTP wrapped: on any error → log + empty/None (SOFT).

- [x] **Step 1: Add the dependency**

In `server/pyproject.toml` add `"httpx>=0.27"` to `[project].dependencies`, then:

Run: `cd server && uv sync`

- [x] **Step 2: Write the failing test (httpx MockTransport — no live Spoolman)**

```python
# server/tests/test_inventory_spoolman.py
import json
import httpx
import pytest
from amsx.config import SpoolmanConfig
from amsx.inventory.spoolman import SpoolmanStore

pytestmark = pytest.mark.asyncio

SPOOL_JSON = {
    "id": 2, "archived": False, "remaining_weight": 400.0,
    "filament": {"id": 11, "material": "PLA", "color_hex": "FF0000", "name": "Red"},
    "extra": {"ams_module": json.dumps("m2")},
}


def _store(handler) -> SpoolmanStore:
    s = SpoolmanStore(SpoolmanConfig(base_url="http://x/api/v1"))
    s._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://x/api/v1")
    return s


async def test_list_maps_filament_and_module():
    def handler(req):
        assert req.url.path.endswith("/spool")
        return httpx.Response(200, json=[SPOOL_JSON])
    spools = await _store(handler).list_spools()
    assert len(spools) == 1
    s = spools[0]
    assert s.id == "2" and s.material == "PLA" and s.color_hex == "FF0000"
    assert s.module == "m2" and s.remaining_g == 400.0


async def test_set_module_patches_extra_json_encoded():
    seen = {}
    def handler(req):
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={**SPOOL_JSON, "extra": {"ams_module": json.dumps("m3")}})
    await _store(handler).set_module("2", "m3")
    assert seen["body"]["extra"]["ams_module"] == json.dumps("m3")


async def test_errors_are_soft():
    def handler(req):
        raise httpx.ConnectError("down")
    assert await _store(handler).list_spools() == []          # no raise
    assert await _store(handler).loaded_in("m2") is None
```

- [x] **Step 3: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_inventory_spoolman.py -v`
Expected: FAIL (module not found).

- [x] **Step 4: Implement `SpoolmanStore`**

```python
# server/src/amsx/inventory/spoolman.py
"""SpoolmanStore — SpoolStore over a (user-run, external) Spoolman REST instance.

SOFT by contract: every call wraps HTTP and on ANY error logs + returns empty/None so the swap
path never breaks because the inventory service is down. Spool `extra` values are JSON-encoded
strings on the wire (we json.loads/json.dumps the `ams_module` key).
"""

from __future__ import annotations

import json
import logging

import httpx

from ..config import SpoolmanConfig
from ..types import ModuleId, Spool

log = logging.getLogger("amsx.inventory")
MODULE_FIELD = "ams_module"


class SpoolmanStore:
    def __init__(self, cfg: SpoolmanConfig) -> None:
        self._cfg = cfg
        self._client = httpx.AsyncClient(base_url=cfg.base_url, timeout=cfg.timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    def _spool(self, j: dict) -> Spool:
        fil = j.get("filament") or {}
        extra = j.get("extra") or {}
        module = None
        raw = extra.get(MODULE_FIELD)
        if isinstance(raw, str) and raw:
            try:
                module = json.loads(raw) or None
            except ValueError:
                module = raw or None
        color = fil.get("color_hex")
        return Spool(
            id=str(j["id"]),
            filament_id=str(fil.get("id", "")),
            material=fil.get("material"),
            color_hex=color.upper() if isinstance(color, str) else None,
            name=fil.get("name"),
            remaining_g=j.get("remaining_weight"),
            module=module,
            archived=bool(j.get("archived")),
        )

    async def list_spools(self, *, include_archived: bool = False) -> list[Spool]:
        params: dict[str, object] = {"allow_archived": str(include_archived).lower()}
        if self._cfg.active_location:
            params["location"] = self._cfg.active_location
        try:
            r = await self._client.get("/spool", params=params)
            r.raise_for_status()
            return [self._spool(j) for j in r.json()]
        except Exception:  # SOFT
            log.warning("Spoolman list_spools failed (soft)", exc_info=True)
            return []

    async def get_spool(self, spool_id: str) -> Spool | None:
        try:
            r = await self._client.get(f"/spool/{spool_id}")
            r.raise_for_status()
            return self._spool(r.json())
        except Exception:
            log.warning("Spoolman get_spool failed (soft)", exc_info=True)
            return None

    async def loaded_in(self, module_id: ModuleId) -> Spool | None:
        return next((s for s in await self.list_spools() if s.module == module_id), None)

    async def set_module(self, spool_id: str, module_id: ModuleId | None) -> None:
        body = {"extra": {MODULE_FIELD: json.dumps(module_id or "")}}
        try:
            r = await self._client.patch(f"/spool/{spool_id}", json=body)
            r.raise_for_status()
        except Exception:
            log.warning("Spoolman set_module failed (soft)", exc_info=True)

    async def match(self, material: str | None, color_hex: str | None) -> list[Spool]:
        # Spoolman matches colour perceptually via color_similarity_threshold; we then keep only
        # spools of those filaments. SOFT.
        params: dict[str, object] = {}
        if material:
            params["material"] = material
        if color_hex:
            params["color_hex"] = color_hex
            params["color_similarity_threshold"] = 20
        try:
            r = await self._client.get("/filament", params=params)
            r.raise_for_status()
            ids = {str(f["id"]) for f in r.json()}
        except Exception:
            log.warning("Spoolman match failed (soft)", exc_info=True)
            return []
        return [s for s in await self.list_spools() if s.filament_id in ids]

    async def consume(self, spool_id: str, grams: float) -> None:
        try:
            r = await self._client.put(f"/spool/{spool_id}/use", json={"use_weight": grams})
            r.raise_for_status()
        except Exception:
            log.warning("Spoolman consume failed (soft)", exc_info=True)

    async def ensure_module_field(self) -> None:
        try:
            r = await self._client.get("/field/spool")
            r.raise_for_status()
            if any(f.get("key") == MODULE_FIELD for f in r.json()):
                return
            await self._client.post(
                f"/field/spool/{MODULE_FIELD}",
                json={"name": "AMS Module", "field_type": "text"},
            )
        except Exception:
            log.warning("Spoolman ensure_module_field failed (soft)", exc_info=True)
```

- [x] **Step 5: Run tests + lint, commit**

Run: `cd server && uv run pytest tests/test_inventory_spoolman.py -v && uv run ruff check src/`
Expected: PASS.

```bash
git add server/src/amsx/inventory/spoolman.py server/tests/test_inventory_spoolman.py server/pyproject.toml server/uv.lock
git commit -m "feat(inventory): SpoolmanStore httpx client (soft) with extra.ams_module mapping"
```

---

### Task 4: Color-plan parser in `job/`

**Files:**
- Modify: `server/src/amsx/job/__init__.py` (parse metadata; attach colours; base)
- Modify: `server/pyproject.toml` (add `defusedxml` — XXE-safe XML parsing)
- Test: `server/tests/test_job_colorplan.py`

**Interfaces:**
- Consumes: `JobParser`, `SwapPlan`, `PlannedSwap`, `FilamentColor`.
- Produces: `JobParser.parse` now returns a `SwapPlan` whose `swaps[k].material/color_hex` and
  `base`/`colors` are populated from the 3mf metadata. Helper `JobParser._color_plan(zf) ->
  tuple[FilamentColor | None, list[FilamentColor], list[tuple[int, str, str]]]` (base, distinct
  colours, ordered changes as `(index, material, color_hex)`). Counts validated against the
  `M400 U1` pauses; on mismatch the colour fields stay `None`.

- [x] **Step 1: Write the failing test**

```python
# server/tests/test_job_colorplan.py
import json, zipfile
from pathlib import Path
from amsx.job import Job, JobParser

PLATE = (
    "; layer num/total_layer_count: 1/3\n"
    "M1020 S0\n"
    "G1 Z0.2\n"
    "; layer num/total_layer_count: 2/3\n"
    "M400 U1\n"          # one change @ layer 2
    "G1 Z0.4\n"
)
CUSTOM_GCODE = (
    '<?xml version="1.0"?><custom_gcodes_per_layer><plate><plate_info id="1"/>'
    '<layer top_z="0.4" type="2" extruder="5" color="#FF0000" gcode="tool_change"/>'
    '<mode value="MultiAsSingle"/></plate></custom_gcodes_per_layer>'
)
SLICE_INFO = (
    '<plate><metadata key="index" value="1"/>'
    '<filament id="1" type="PLA" color="#FFFFFF" used_g="0.36"/>'
    '<filament id="5" type="PLA" color="#FF0000" used_g="1.14"/></plate>'
)


def _mk(tmp_path: Path) -> Path:
    p = tmp_path / "two.gcode.3mf"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("Metadata/plate_1.gcode", PLATE)
        zf.writestr("Metadata/custom_gcode_per_layer.xml", CUSTOM_GCODE)
        zf.writestr("Metadata/filament_sequence.json", json.dumps({"plate_1": {"sequence": [1, 5]}}))
        zf.writestr("Metadata/slice_info.config", SLICE_INFO)
    return p


def test_colorplan_base_and_change(tmp_path):
    plan = JobParser().parse(Job(file=_mk(tmp_path), printer_id="p1"))
    assert len(plan) == 1
    assert plan.base.index == 1 and plan.base.color_hex == "FFFFFF" and plan.base.grams == 0.36
    assert plan.swaps[0].color_hex == "FF0000" and plan.swaps[0].material == "PLA"
    assert plan.swaps[0].filament_index == 5
    assert {c.color_hex for c in plan.colors} == {"FFFFFF", "FF0000"}


def test_colorplan_absent_degrades(tmp_path):
    # No custom_gcode/slice_info -> colours None, plan still parses by M400 U1.
    p = tmp_path / "bare.gcode.3mf"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("Metadata/plate_1.gcode", "M1020 S0\nM400 U1\n")
    plan = JobParser().parse(Job(file=p, printer_id="p1"))
    assert plan.swaps[0].color_hex is None and plan.base is None
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_job_colorplan.py -v`
Expected: FAIL (plan has no `.base`, colour fields None / AttributeError).

- [x] **Step 3: Implement the color-plan parse**

First add the XXE-safe XML dep: add `"defusedxml>=0.7"` to `server/pyproject.toml` `[project].dependencies` and run `cd server && uv sync`. Then in `server/src/amsx/job/__init__.py` add imports and helpers, and weave colours into the result.

```python
import json, re, zipfile
from defusedxml.ElementTree import fromstring as _xml_fromstring  # XXE / billion-laughs safe
from amsx.types import FilamentColor, PlannedSwap, PrinterId, SwapPlan

CUSTOM_GCODE_PATH = "Metadata/custom_gcode_per_layer.xml"
FILAMENT_SEQ_PATH = "Metadata/filament_sequence.json"
SLICE_INFO_PATH = "Metadata/slice_info.config"
_HEX_RE = re.compile(r"#?([0-9A-Fa-f]{6})")


def _hex6(s: str | None) -> str | None:
    m = _HEX_RE.search(s or "")
    return m.group(1).upper() if m else None


def _slice_info_map(zf: zipfile.ZipFile) -> dict[int, tuple[str | None, str | None, float | None]]:
    """index -> (material, color_hex, grams) from slice_info.config <filament id type color used_g>."""
    try:
        root = _xml_fromstring(zf.read(SLICE_INFO_PATH).decode("utf-8", "replace"))
    except Exception:  # best-effort: missing/malformed/hostile XML -> degrade to index-only
        return {}
    out: dict[int, tuple[str | None, str | None, float | None]] = {}
    for fil in root.iter("filament"):
        try:
            idx = int(fil.get("id", ""))
        except ValueError:
            continue
        grams = fil.get("used_g")
        out[idx] = (fil.get("type"), _hex6(fil.get("color")), float(grams) if grams else None)
    return out


def _changes(zf: zipfile.ZipFile) -> list[tuple[int, str | None]]:
    """Ordered (extruder_index, color_hex) per tool_change from custom_gcode_per_layer.xml."""
    try:
        root = _xml_fromstring(zf.read(CUSTOM_GCODE_PATH).decode("utf-8", "replace"))
    except Exception:  # best-effort: missing/malformed/hostile XML -> degrade
        return []
    out: list[tuple[int, str | None]] = []
    for layer in root.iter("layer"):
        if layer.get("gcode") == "tool_change":
            try:
                out.append((int(layer.get("extruder", "")), _hex6(layer.get("color"))))
            except ValueError:
                continue
    return out


def _base_index(zf: zipfile.ZipFile) -> int | None:
    try:
        seq = json.loads(zf.read(FILAMENT_SEQ_PATH).decode("utf-8", "replace"))
        plate = next(iter(seq.values()))
        return int(plate["sequence"][0])
    except (KeyError, ValueError, StopIteration, IndexError, TypeError):
        return None
```

Then change `JobParser.parse` to open the zip once, build the swap plan from the gcode (existing
`_plan_from_gcode`), and enrich it:

```python
    def parse(self, job: Job) -> SwapPlan:
        path = Path(job.file)
        gcode = self._read_plate_gcode(path)
        plan = self._plan_from_gcode(gcode, source=str(path))
        try:
            with zipfile.ZipFile(path) as zf:
                info = _slice_info_map(zf)
                changes = _changes(zf)
                base_idx = _base_index(zf)
        except zipfile.BadZipFile:
            return plan
        # Bind colours to pauses by ORDERED POSITION; only if counts line up.
        swaps = plan.swaps
        if changes and len(changes) == len(swaps):
            swaps = [
                PlannedSwap(
                    seq=s.seq, filament_index=idx, tag=s.tag, layer=s.layer, line=s.line,
                    material=(info.get(idx) or (None, None, None))[0],
                    color_hex=color or (info.get(idx) or (None, None, None))[1],
                )
                for s, (idx, color) in zip(swaps, changes, strict=True)
            ]
        base = None
        if base_idx is not None and base_idx in info:
            mat, col, grams = info[base_idx]
            base = FilamentColor(base_idx, mat, col, grams)
        colors = [FilamentColor(i, m, c, g) for i, (m, c, g) in info.items()]
        return SwapPlan(swaps=swaps, base=base, colors=colors)
```

(Keep `_plan_from_gcode` as-is; the colour binding replaces each `PlannedSwap` with a coloured copy.)

- [x] **Step 4: Run tests + the existing parser tests + lint**

Run: `cd server && uv run pytest tests/test_job_parser.py tests/test_job_colorplan.py -v && uv run ruff check src/`
Expected: PASS (existing parser tests still green — they have no metadata so colours stay None).

- [x] **Step 5: Commit**

```bash
git add server/src/amsx/job/__init__.py server/tests/test_job_colorplan.py
git commit -m "feat(job): parse 3mf colour plan (custom_gcode_per_layer + filament_sequence + slice_info)"
```

---

### Task 5: `vt_tray` driver read/write

**Files:**
- Modify: `server/src/amsx/printer/drivers/__init__.py` (A1Driver: `parse_external_filament`, `request_set_external_filament`; add the two methods to the `PrinterDriver` Protocol with safe defaults on X1P1)
- Modify: `server/src/amsx/printer/__init__.py` (`Printer.read_external_filament`, `Printer.set_external_filament`)
- Test: `server/tests/test_vt_tray.py`

**Interfaces:**
- Consumes: `Report`, `A1Driver`.
- Produces:
  - `A1Driver.parse_external_filament(report) -> tuple[str | None, str | None]` → `(material, color_hex6)` from `print.vt_tray`.
  - `A1Driver.request_set_external_filament(material, color_hex, *, tray_info_idx="GFL04", tmin=190, tmax=240) -> Report` → the confirmed `ams_filament_setting` payload (`ams_id=255, tray_id=254, slot_id=0`, `tray_color` = `color_hex.upper()+"FF"`).
  - `Printer.read_external_filament() -> tuple[str | None, str | None]` (from cached `state.raw`).
  - `Printer.set_external_filament(material, color_hex) -> None` (sends via link).

- [x] **Step 1: Write the failing test**

```python
# server/tests/test_vt_tray.py
from amsx.printer.drivers import A1Driver


def test_parse_external_filament():
    rpt = {"print": {"vt_tray": {"tray_type": "PLA", "tray_color": "FF0000FF"}}}
    assert A1Driver().parse_external_filament(rpt) == ("PLA", "FF0000")


def test_set_external_filament_payload():
    pr = A1Driver().request_set_external_filament("PLA", "ff0000")["print"]
    assert pr["command"] == "ams_filament_setting"
    assert pr["ams_id"] == 255 and pr["tray_id"] == 254 and pr["slot_id"] == 0
    assert pr["tray_color"] == "FF0000FF"   # RRGGBBAA uppercase
    assert pr["tray_type"] == "PLA"
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_vt_tray.py -v`
Expected: FAIL (no `parse_external_filament`).

- [x] **Step 3: Implement on A1Driver**

```python
    _VT_TRAY = "vt_tray"

    def parse_external_filament(self, report: Report) -> tuple[str | None, str | None]:
        blob = report.get(self._PRINT_KEY)
        vt = blob.get(self._VT_TRAY) if isinstance(blob, dict) else None
        if not isinstance(vt, dict):
            return None, None
        color = vt.get("tray_color")
        hex6 = color[:6].upper() if isinstance(color, str) and len(color) >= 6 else None
        return vt.get("tray_type"), hex6

    def request_set_external_filament(
        self, material: str | None, color_hex: str | None, *,
        tray_info_idx: str = "GFL04", tmin: int = 190, tmax: int = 240,
    ) -> Report:
        rgba = ((color_hex or "FFFFFF").upper()[:6]) + "FF"
        return {"print": {
            "sequence_id": self._next_seq(),
            "command": "ams_filament_setting",
            "ams_id": 255, "tray_id": 254, "slot_id": 0,
            "tray_info_idx": tray_info_idx, "setting_id": "",
            "tray_color": rgba, "tray_type": material or "PLA",
            "nozzle_temp_min": tmin, "nozzle_temp_max": tmax,
        }}
```

Add to the `PrinterDriver` Protocol the two method signatures, and give `X1P1Driver` safe defaults
(`return None, None` / `return {"print": {}}`) so it satisfies the contract without claiming support.

In `server/src/amsx/printer/__init__.py`:

```python
    def read_external_filament(self) -> tuple[str | None, str | None]:
        return self.driver.parse_external_filament({"print": self.state.raw.get("print", {})})

    async def set_external_filament(self, material: str | None, color_hex: str | None) -> None:
        await self.link.request(self.driver.request_set_external_filament(material, color_hex))
```

- [x] **Step 4: Run tests + lint, commit**

Run: `cd server && uv run pytest tests/test_vt_tray.py tests/test_printer_state.py -v && uv run ruff check src/`

```bash
git add server/src/amsx/printer/ server/tests/test_vt_tray.py
git commit -m "feat(printer): vt_tray external-filament read + ams_filament_setting write (A1, confirmed)"
```

---

### Task 6: Resolver — best-effort index→module proposal

**Files:**
- Create: `server/src/amsx/inventory/resolver.py`
- Test: `server/tests/test_resolver.py`

**Interfaces:**
- Consumes: `SpoolStore`, `SwapPlan`, `FilamentColor`.
- Produces: `Resolver(store: SpoolStore)` with
  `async def propose(self, plan: SwapPlan) -> dict[int, ProposedRow]` keyed by filament index
  (base + each change). `ProposedRow(index, material, color_hex, grams, module: ModuleId | None,
  spool_id: str | None, status: str)` where `status ∈ {"loaded","gap"}` — `module/spool_id` set when
  a loaded spool matches, else `gap`.

- [x] **Step 1: Write the failing test**

```python
# server/tests/test_resolver.py
import pytest
from amsx.inventory import FakeSpoolStore
from amsx.inventory.resolver import Resolver
from amsx.types import FilamentColor, Spool, SwapPlan, PlannedSwap

pytestmark = pytest.mark.asyncio


async def test_propose_matches_loaded_and_flags_gap():
    store = FakeSpoolStore([
        Spool(id="1", filament_id="10", material="PLA", color_hex="FFFFFF", module="m1"),
        Spool(id="2", filament_id="11", material="PLA", color_hex="FF0000", module="m2"),
    ])
    plan = SwapPlan(
        swaps=[PlannedSwap(seq=1, filament_index=5, tag="t", layer=2, line=1,
                           material="PLA", color_hex="0000FF")],   # blue: not loaded -> gap
        base=FilamentColor(1, "PLA", "FFFFFF", 0.3),
        colors=[FilamentColor(1, "PLA", "FFFFFF", 0.3), FilamentColor(5, "PLA", "0000FF", 1.0)],
    )
    rows = await Resolver(store).propose(plan)
    assert rows[1].status == "loaded" and rows[1].module == "m1"   # base white -> m1
    assert rows[5].status == "gap" and rows[5].module is None       # blue -> gap
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_resolver.py -v`
Expected: FAIL (module not found).

- [x] **Step 3: Implement the resolver**

```python
# server/src/amsx/inventory/resolver.py
"""Resolver — best-effort pre-fill of index→module from the loaded inventory. NOT authoritative;
the operator confirms/overrides the mapping. No auto-assignment guarantees, no delta-sync."""

from __future__ import annotations

from dataclasses import dataclass

from ..types import FilamentColor, ModuleId, SwapPlan
from . import SpoolStore


@dataclass(frozen=True)
class ProposedRow:
    index: int
    material: str | None
    color_hex: str | None
    grams: float | None
    module: ModuleId | None
    spool_id: str | None
    status: str  # "loaded" | "gap"


class Resolver:
    def __init__(self, store: SpoolStore) -> None:
        self._store = store

    async def propose(self, plan: SwapPlan) -> dict[int, ProposedRow]:
        rows: dict[int, ProposedRow] = {}
        colors = list(plan.colors) or [
            FilamentColor(s.filament_index, s.material, s.color_hex, None) for s in plan.swaps
        ]
        for fc in colors:
            matches = await self._store.match(fc.material, fc.color_hex)
            loaded = next((s for s in matches if s.module is not None), None)
            rows[fc.index] = ProposedRow(
                index=fc.index, material=fc.material, color_hex=fc.color_hex, grams=fc.grams,
                module=loaded.module if loaded else None,
                spool_id=loaded.id if loaded else None,
                status="loaded" if loaded else "gap",
            )
        return rows
```

- [x] **Step 4: Run tests + lint, commit**

Run: `cd server && uv run pytest tests/test_resolver.py -v && uv run ruff check src/`

```bash
git add server/src/amsx/inventory/resolver.py server/tests/test_resolver.py
git commit -m "feat(inventory): Resolver best-effort index->module proposal"
```

---

### Task 7: Brain wiring + proxy API (the frontend contract)

**Files:**
- Modify: `server/src/amsx/brain.py` (build the store; `ensure_module_field` + `set_external_filament` on swap; arm produces a proposal; consume on finish)
- Modify: `server/src/amsx/api/__init__.py` (proxy endpoints)
- Test: `server/tests/test_api_inventory.py`

**Interfaces:**
- Consumes: `SpoolStore`, `SpoolmanStore`, `FakeSpoolStore`, `Resolver`, `Brain`.
- Produces — the **API contract the frontend plan consumes**:
  - `GET /api/spools` → `[{id, filament_id, material, color_hex, name, remaining_g, module, archived}]`
  - `GET /api/printers/{id}/loadout` → `[{module, spool: <spool|null>}]` for each configured module
  - `PUT /api/printers/{id}/loadout?module=m2&spool_id=7` → `{ok: true}`
  - `GET /api/printers/{id}/job/assignment` → `{rows: [{index, material, color_hex, grams, module, spool_id, status}], confirmed: bool}`
  - `POST /api/printers/{id}/job/assignment` body `{index: module}` → `{ok: true}` (writes `set_module` for gap rows where a spool was chosen; binds index→module on the orchestrator)
  - `Brain.store: SpoolStore`, `Brain.resolver: Resolver`, `Brain.assignment: dict[PrinterId, dict[int, ModuleId]]`.

- [x] **Step 1: Write the failing test (FakeSpoolStore injected)**

```python
# server/tests/test_api_inventory.py
import json
from fastapi.testclient import TestClient
from amsx.api import create_app
from amsx.brain import build_brain
from amsx.inventory import FakeSpoolStore
from amsx.types import Spool


def _client():
    brain = build_brain(simulate=True)
    brain.store = FakeSpoolStore([
        Spool(id="1", filament_id="10", material="PLA", color_hex="FFFFFF", name="White", remaining_g=900, module="m1"),
    ])
    app = create_app(brain)
    return TestClient(app)


def test_list_spools_endpoint():
    with _client() as c:
        r = c.get("/api/spools")
        assert r.status_code == 200
        assert r.json()[0]["color_hex"] == "FFFFFF"


def test_set_loadout_endpoint():
    with _client() as c:
        r = c.put("/api/printers/sim-x1/loadout", params={"module": "m2", "spool_id": "1"})
        assert r.status_code == 200
        lo = {row["module"]: row for row in c.get("/api/printers/sim-x1/loadout").json()}
        assert lo["m2"]["spool"]["id"] == "1"
```

(If the simulate printer id differs, read it from `GET /api/printers` first — keep the assertion on whatever id the sim config yields.)

- [x] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_api_inventory.py -v`
Expected: FAIL (`brain.store` missing / 404 on `/api/spools`).

- [x] **Step 3: Implement brain store + endpoints**

In `brain.py`: in `__init__`, set `self.store`, `self.resolver`, `self.assignment = {}`. In `build_brain`/`_bring_up_*`, choose the store: `FakeSpoolStore()` when `simulate or not config.spoolman.enabled`, else `SpoolmanStore(config.spoolman)`; build `Resolver(self.store)`. In `start()`, `await self.store.ensure_module_field()`. Extend `arm_job` to also compute + cache the proposal (`self.assignment.setdefault(printer_id, {})`), and have the swap path call `printer.set_external_filament(material, color)` after a confirmed swap (wire in the orchestrator alert/consume hook is Task 8).

In `api/__init__.py` add the endpoints from the Interfaces block, serializing `Spool` via a small
`_spool_dict(s)` helper and reading the module list from `brain.config.modules`.

- [x] **Step 4: Run the full suite + lint**

Run: `cd server && uv run pytest -q && uv run ruff check src/ tests/`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add server/src/amsx/brain.py server/src/amsx/api/__init__.py server/tests/test_api_inventory.py
git commit -m "feat(api): spool inventory + loadout + job-assignment proxy endpoints"
```

---

### Task 8: Consume on finish + set external filament on swap

**Files:**
- Modify: `server/src/amsx/orchestration/__init__.py` (after a confirmed swap: set external filament; on plan done / FINISH: consume grams)
- Modify: `server/src/amsx/printer/__init__.py` (emit a `PrintFinished` signal, or reuse stage→FINISHED)
- Test: `server/tests/test_consume.py`

**Interfaces:**
- Consumes: `SpoolStore`, the per-printer `assignment` (index→module), `SwapPlan.colors` grams.
- Produces: on `gcode_state→FINISH`, for each used index with grams, `store.consume(spool_of(module), grams)` aggregated by spool. Best-effort, SOFT.

- [x] **Step 1: Write the failing test**

```python
# server/tests/test_consume.py
import pytest
from amsx.inventory import FakeSpoolStore
from amsx.types import Spool, FilamentColor, SwapPlan
# Construct the consume helper directly (pure function over store + plan + assignment).
from amsx.orchestration import consume_plan

pytestmark = pytest.mark.asyncio


async def test_consume_aggregates_by_spool():
    store = FakeSpoolStore([Spool(id="1", filament_id="10", material="PLA", color_hex="FFFFFF", remaining_g=1000, module="m1")])
    plan = SwapPlan(colors=[FilamentColor(1, "PLA", "FFFFFF", 4.0), FilamentColor(5, "PLA", "FFFFFF", 6.0)])
    # both indices mapped to m1 -> same spool -> 10g total
    await consume_plan(store, plan, assignment={1: "m1", 5: "m1"}, loaded={"m1": "1"})
    assert (await store.get_spool("1")).remaining_g == 990
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_consume.py -v`
Expected: FAIL (`consume_plan` not defined).

- [x] **Step 3: Implement `consume_plan` + wire FINISH**

```python
# in server/src/amsx/orchestration/__init__.py
async def consume_plan(store, plan, *, assignment: dict[int, str], loaded: dict[str, str]) -> None:
    """Aggregate the plan's per-index grams by spool and decrement each (best-effort, SOFT)."""
    grams_by_spool: dict[str, float] = {}
    for fc in plan.colors:
        module = assignment.get(fc.index)
        spool_id = loaded.get(module) if module else None
        if spool_id and fc.grams:
            grams_by_spool[spool_id] = grams_by_spool.get(spool_id, 0.0) + fc.grams
    for spool_id, grams in grams_by_spool.items():
        try:
            await store.consume(spool_id, grams)
        except Exception:  # SOFT
            pass
```

Wire the Brain so that when a printer's stage transitions to `FINISHED`, it calls `consume_plan`
with the armed plan, the confirmed `assignment`, and the current loadout (`{module: spool.id}` from
`store.list_spools()`).

- [x] **Step 4: Run tests + lint, commit**

Run: `cd server && uv run pytest tests/test_consume.py -q && uv run ruff check src/`

```bash
git add server/src/amsx/orchestration/__init__.py server/src/amsx/printer/__init__.py server/tests/test_consume.py
git commit -m "feat(orchestration): consume spool grams on finish; set external filament on swap"
```

---

### Task 9: Full-suite green + sim end-to-end guard

**Files:**
- Test: `server/tests/test_inventory_e2e_sim.py`

**Interfaces:**
- Consumes: everything above via `create_app(brain)` with a `FakeSpoolStore` and the simulate path.

- [x] **Step 1: Write the e2e sim test**

```python
# server/tests/test_inventory_e2e_sim.py
# Arm a two-colour sim job, GET the assignment proposal, POST a confirmation, assert the
# orchestrator binds index->module and a sim pause drives the mapped module. Build on the
# existing sim-hook tests in test_api.py (reuse their pattern for /sim/pause and /sim/sensor).
```

(Model this on the existing `test_api.py` sim-hook flow; assert `GET /job/assignment` returns one
`gap`/`loaded` row per colour and that confirming it makes `brain.assignment[printer]` map the
change index to the chosen module.)

- [x] **Step 2: Run the whole suite + lint**

Run: `cd server && uv run pytest -q && uv run ruff check src/ tests/`
Expected: ALL PASS, clean.

- [x] **Step 3: Commit**

```bash
git add server/tests/test_inventory_e2e_sim.py
git commit -m "test(inventory): sim end-to-end arm->assignment->confirm"
```

---

## Self-review notes (resolved)

- **Spec coverage:** §5 model mapping → Tasks 1-3; §6.2 colour plan → Task 4; §6.3 resolver → Task 6;
  §6.4 assignment + §8 API → Task 7; §6.5 consume → Task 8; §6.6 soft proxy/config → Tasks 3/7;
  §6.7 vt_tray → Task 5. Frontend (§9) is the companion plan.
- **Parked (NOT in this plan, by decision):** colours>modules reload (#17), gap-on-start policy (#22),
  in-AMS CRUD, runout→backup, standalone management screens.
- **Soft dependency:** every Spoolman call is wrapped; the swap path never raises on inventory errors.
- **Agent mapping:** Task 4 → `job-3mf`; Task 5 → `mqtt-bambu`; Tasks 2/3/6 → inventory (general-purpose);
  Tasks 7/8 → `orchestrator`; Task 1 is the shared foundation (do first). The frontend plan → `frontend`.
