"""api — FastAPI app: dashboard data, 3MF upload, live printer state, human-swap prompts.

The SPA front end consumes these endpoints (see the `frontend` agent). v0 runs in simulate
mode by default — no printer required — so `uv run amsx` starts and serves immediately.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from ..brain import Brain, build_brain
from ..events import PauseEvent, SensorEvent
from ..orchestration import Orchestrator
from ..printer import Printer
from ..types import PauseReason, Spool

log = logging.getLogger("amsx.api")

# Local-first dev: the SPA is served from a different port, so allow the dev origins.
# Override with AMSX_CORS_ORIGINS (comma-separated) when serving from elsewhere.
_DEFAULT_CORS = "http://localhost:3000,http://127.0.0.1:3000"


def _printer_state(printer: Printer) -> dict[str, Any]:
    s = printer.state
    loaded = s.loaded_filament
    return {
        "id": printer.id,
        "stage": str(s.stage),
        "pause_reason": str(s.pause_reason) if s.pause_reason is not None else None,
        "filament_sensor": s.filament_sensor,
        "progress": s.progress,
        "loaded_filament": (
            {"index": loaded.index, "material": loaded.material, "color": loaded.color}
            if loaded is not None
            else None
        ),
    }


def _is_connected(printer: Printer) -> bool:
    """True when the live transport is connected. SimulatedPrinterLink has no bus → always on."""
    bus = getattr(printer.link, "bus", None)
    if bus is None:  # simulator
        return True
    return bool(getattr(bus, "connected", False))


def _printer_detail(brain: Brain, printer: Printer) -> dict[str, Any]:
    """Everything we know about one printer: modeled state + identity + the full raw report.

    ``raw`` is the deep-merged snapshot of the printer's own report (temps, fans, wifi, ams,
    speeds, ipcam, etc.) — the complete picture for a detail view. The access code is never
    included.
    """
    cfg = next((p for p in brain.config.printers if p.id == printer.id), None)
    return {
        **_printer_state(printer),
        "serial": cfg.serial if cfg else printer.link.serial,
        "model": cfg.model if cfg else printer.driver.model,
        "ip": cfg.ip if cfg else None,
        "simulate": brain.simulate,
        "connected": _is_connected(printer),
        "seeded": printer._seeded,
        "raw": printer.state.raw,
    }


def _orchestrator_status(orch: Orchestrator) -> dict[str, Any]:
    """The live swap loop's state — what the dashboard (and the v0 test script) watch."""
    return {
        "armed": True,
        "printer_id": orch.printer_id,
        "cursor": orch.cursor,
        "total": len(orch.plan),
        "done": orch.done,
        "held": orch.held,
        "swap_state": str(orch.sm.state),
        "alerts": list(orch.alerts),
        "swaps": [
            {
                "seq": sw.seq,
                "filament_index": sw.filament_index,
                "tag": sw.tag,
                "current": i == orch.cursor,
            }
            for i, sw in enumerate(orch.plan.swaps)
        ],
    }


def create_app(brain: Brain | None = None, *, simulate: bool = True) -> FastAPI:
    """Build the app. Pass a pre-built `brain` (e.g. in tests); otherwise one is constructed
    from the resolved config on startup.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        b = brain or build_brain(simulate=simulate)
        await b.start()
        app.state.brain = b
        try:
            yield
        finally:
            await b.stop()

    app = FastAPI(title="AMS-X Brain", version="0.0.0", lifespan=lifespan)

    raw_origins = os.getenv("AMSX_CORS_ORIGINS", _DEFAULT_CORS)
    origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def _brain() -> Brain:
        return app.state.brain

    # Strong refs to fire-and-forget swap tasks so the loop can't GC them mid-swap.
    _bg_tasks: set[asyncio.Task] = set()

    @app.get("/health")
    async def health() -> dict[str, Any]:
        b = _brain()
        return {
            "ok": True,
            "simulate": b.simulate,
            "printers": list(b.printers),
            "modules": len(b._module_by_id),
        }

    @app.get("/api/printers")
    async def list_printers() -> list[dict[str, Any]]:
        return [_printer_state(p) for p in _brain().printers.values()]

    @app.get("/api/printers/{printer_id}")
    async def get_printer(printer_id: str) -> dict[str, Any]:
        printer = _brain().printers.get(printer_id)
        if printer is None:
            raise HTTPException(status_code=404, detail=f"unknown printer {printer_id!r}")
        return _printer_state(printer)

    @app.get("/api/printers/{printer_id}/detail")
    async def get_printer_detail(printer_id: str) -> dict[str, Any]:
        """Full per-printer view (modeled state + identity + complete raw report)."""
        b = _brain()
        printer = b.printers.get(printer_id)
        if printer is None:
            raise HTTPException(status_code=404, detail=f"unknown printer {printer_id!r}")
        return _printer_detail(b, printer)

    @app.post("/api/printers/{printer_id}/job")
    async def submit_job(printer_id: str, file: UploadFile, start: bool = True) -> dict[str, Any]:
        """Upload a sliced 3MF and arm the swap plan.

        ``start=true`` (default) also pushes (FTPS) + starts the print — the still-unverified
        v0.4 path. ``start=false`` ARMS ONLY: the operator starts the print themselves (Bambu
        Studio / SD) and the Brain owns the swap loop from the pause onward (no FTPS needed).
        """
        b = _brain()
        if printer_id not in b.printers:
            raise HTTPException(status_code=404, detail=f"unknown printer {printer_id!r}")
        log.info(
            "API: job upload received — printer=%s file=%r start=%s",
            printer_id,
            file.filename,
            start,
        )
        with tempfile.NamedTemporaryFile(delete=False, suffix=".gcode.3mf") as tmp:
            tmp.write(await file.read())
            saved = Path(tmp.name)
        try:
            run = b.submit_job(printer_id, saved) if start else b.arm_job(printer_id, saved)
            orch = await run
        except Exception as exc:  # parse/transport errors -> 400 for the UI
            # Log the FULL exception here — otherwise a failed upload/start is invisible on the
            # server (it only became a UI 400), which looked exactly like "it just hangs".
            log.exception("API: job submit FAILED for %s", printer_id)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        log.info("API: job accepted for %s (started=%s)", printer_id, start)
        return {
            "printer_id": printer_id,
            "filename": file.filename,
            "started": start,
            "planned_swaps": [
                {"seq": sw.seq, "filament_index": sw.filament_index, "tag": sw.tag}
                for sw in orch.plan.swaps
            ],
        }

    @app.post("/api/printers/{printer_id}/job/start")
    async def start_armed_job(printer_id: str) -> dict[str, Any]:
        """Push (FTPS) + start the job this printer is ALREADY armed with.

        The two-step flow: upload with ``?start=false`` to arm + propose the mapping, let the
        operator confirm it (POST ``/job/assignment``), then call this to start the held job
        WITHOUT re-arming (which would wipe the confirmed assignment). 409 if nothing is armed.
        """
        b = _brain()
        if printer_id not in b.printers:
            raise HTTPException(status_code=404, detail=f"unknown printer {printer_id!r}")
        try:
            await b.start_armed(printer_id)
        except KeyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:  # FTPS/start transport errors -> 400 for the UI
            log.exception("API: start_armed FAILED for %s", printer_id)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        log.info("API: armed job started for %s", printer_id)
        return {"printer_id": printer_id, "started": True}

    @app.get("/api/prompts")
    async def list_prompts() -> list[dict[str, Any]]:
        """Pending human-swap actions the orchestrator is waiting on."""
        return _brain().prompts.pending()

    @app.post("/api/prompts/{prompt_id}/answer")
    async def answer_prompt(prompt_id: str, response: str = "done") -> dict[str, Any]:
        if not _brain().prompts.answer(prompt_id, response):
            raise HTTPException(status_code=404, detail=f"unknown prompt {prompt_id!r}")
        return {"ok": True, "prompt_id": prompt_id}

    @app.get("/api/printers/{printer_id}/orchestrator")
    async def get_orchestrator(printer_id: str) -> dict[str, Any]:
        """The armed swap loop for this printer (cursor / held / swap_state / alerts).

        404 if the printer is unknown; ``{"armed": false}`` if no job has been submitted yet.
        """
        b = _brain()
        if printer_id not in b.printers:
            raise HTTPException(status_code=404, detail=f"unknown printer {printer_id!r}")
        orch = b.orchestrators.get(printer_id)
        if orch is None:
            return {"armed": False, "printer_id": printer_id}
        return _orchestrator_status(orch)

    # ---- spool inventory proxy endpoints ------------------------------------------------
    def _spool_dict(s: Spool) -> dict[str, Any]:
        return {
            "id": s.id,
            "filament_id": s.filament_id,
            "material": s.material,
            "color_hex": s.color_hex,
            "name": s.name,
            "remaining_g": s.remaining_g,
            "module": s.module,
            "archived": s.archived,
        }

    @app.get("/api/spools")
    async def list_spools(include_archived: bool = False) -> list[dict[str, Any]]:
        """List all spools from the inventory (Spoolman or fake)."""
        spools = await _brain().store.list_spools(include_archived=include_archived)
        return [_spool_dict(s) for s in spools]

    @app.get("/api/printers/{printer_id}/loadout")
    async def get_loadout(printer_id: str) -> list[dict[str, Any]]:
        """Current spool→module mapping for every configured module on this printer."""
        b = _brain()
        if printer_id not in b.printers:
            raise HTTPException(status_code=404, detail=f"unknown printer {printer_id!r}")
        rows = []
        for mc in b.config.modules:
            spool = await b.store.loaded_in(mc.id)
            rows.append({"module": mc.id, "spool": _spool_dict(spool) if spool else None})
        return rows

    @app.put("/api/printers/{printer_id}/loadout")
    async def set_loadout(printer_id: str, module: str, spool_id: str) -> dict[str, Any]:
        """Assign a spool to a module (writes `set_module` on the store)."""
        b = _brain()
        if printer_id not in b.printers:
            raise HTTPException(status_code=404, detail=f"unknown printer {printer_id!r}")
        await b.store.set_module(spool_id, module)
        return {"ok": True}

    @app.get("/api/printers/{printer_id}/job/assignment")
    async def get_assignment(printer_id: str) -> dict[str, Any]:
        """Current spool-assignment proposal for the armed job on this printer.

        Returns rows (one per filament index from the plan), each with the module/spool the
        resolver proposed. `confirmed` is True once the operator has POST-confirmed the mapping.
        Returns empty rows + confirmed=False when no job is armed.
        """
        b = _brain()
        if printer_id not in b.printers:
            raise HTTPException(status_code=404, detail=f"unknown printer {printer_id!r}")
        proposal = b.assignment.get(printer_id, {})
        rows = []
        for _idx, row in sorted(proposal.items()):
            rows.append(
                {
                    "index": row.index,
                    "material": row.material,
                    "color_hex": row.color_hex,
                    "grams": row.grams,
                    "module": row.module,
                    "spool_id": row.spool_id,
                    "status": row.status,
                }
            )
        return {"rows": rows, "confirmed": printer_id in b.confirmed}

    @app.post("/api/printers/{printer_id}/job/assignment")
    async def confirm_assignment(printer_id: str, body: dict[str, str]) -> dict[str, Any]:
        """Confirm (and optionally override) the index→module mapping.

        Body: `{index: module_id}` for each filament index. Persists each override into
        brain.assignment so a follow-up GET reflects the chosen module/status. For rows
        that carry a spool_id, also calls set_module on the store (SOFT — store errors are
        logged and skipped so Spoolman down never 500s this endpoint).
        Returns `{ok: true}`.
        """
        b = _brain()
        if printer_id not in b.printers:
            raise HTTPException(status_code=404, detail=f"unknown printer {printer_id!r}")
        proposal = b.assignment.setdefault(printer_id, {})
        for index_str, module_id in body.items():
            try:
                idx = int(index_str)
            except ValueError:
                continue
            row = proposal.get(idx)
            if row is not None:
                # Persist the operator's choice: update the row with the confirmed module.
                proposal[idx] = replace(row, module=module_id, status="loaded")
                # If the row has a spool, tell the store where it lives — SOFT.
                if row.spool_id:
                    try:
                        await b.store.set_module(row.spool_id, module_id)
                    except Exception:
                        log.warning(
                            "set_module failed for spool %s → %s (soft)",
                            row.spool_id,
                            module_id,
                            exc_info=True,
                        )
        b.confirmed.add(printer_id)
        return {"ok": True}

    # ---- simulate-only test hooks --------------------------------------------------------
    # These let a client drive the swap loop without a printer: inject the pause the
    # orchestrator would see over MQTT and trip the printer's filament sensor. They are the
    # missing seam between SimulatedPrinterLink and the HTTP API. Hard-gated on simulate so
    # they can NEVER fire against real hardware.
    def _require_sim(b: Brain) -> None:
        if not b.simulate:
            raise HTTPException(
                status_code=409, detail="sim hooks are only available in simulate mode"
            )

    def _armed_orchestrator(b: Brain, printer_id: str) -> Orchestrator:
        if printer_id not in b.printers:
            raise HTTPException(status_code=404, detail=f"unknown printer {printer_id!r}")
        orch = b.orchestrators.get(printer_id)
        if orch is None:
            raise HTTPException(
                status_code=409,
                detail=f"no job armed for {printer_id!r} — POST a 3MF to /job first",
            )
        return orch

    @app.post("/api/printers/{printer_id}/sim/pause")
    async def sim_pause(
        printer_id: str, tag: str | None = None, line: int | None = None
    ) -> dict[str, Any]:
        """Inject a filament-change pause (simulate mode only).

        Default (no params): an UNTAGGED pause carrying the next expected swap's gcode ``line`` —
        exactly what a real Bambu ``M400 U1`` looks like, so it exercises the #17 ordinal+line
        guard the real loop uses. Pass ``?line=`` to force a different line (e.g. a far value to
        hit the safe-hold path), or ``?tag=`` to inject a tagged pause (and force a tag mismatch).
        Returns immediately; the swap then blocks on the human prompt — poll ``/api/prompts``.
        """
        b = _brain()
        _require_sim(b)
        orch = _armed_orchestrator(b, printer_id)
        if tag is not None:
            event = PauseEvent(printer_id=printer_id, reason=PauseReason.CHANGE, tag=tag)
            injected: dict[str, Any] = {"tag": tag}
        else:
            if line is None:
                if orch.done:
                    raise HTTPException(
                        status_code=409, detail="no remaining planned swap (plan complete)"
                    )
                line = orch.plan.swaps[orch.cursor].line
            # reason=UNKNOWN mirrors the A1 (it doesn't classify the pause); the orchestrator
            # binds it positionally and confirms with the line guard.
            event = PauseEvent(
                printer_id=printer_id, reason=PauseReason.UNKNOWN, tag=None, line=line
            )
            injected = {"line": line}
        # Don't await: on_pause runs the whole swap, which blocks on the human prompt. Fire it
        # onto the loop and return so the client can answer prompts + trip the sensor.
        task = asyncio.create_task(b.events.publish(event))
        _bg_tasks.add(task)
        task.add_done_callback(_bg_tasks.discard)
        return {"injected": "pause", "printer_id": printer_id, **injected}

    @app.post("/api/printers/{printer_id}/sim/sensor")
    async def sim_sensor(printer_id: str, present: bool = True) -> dict[str, Any]:
        """Trip (or clear) the printer's filament-present sensor (simulate mode only).

        Publishes a ``SensorEvent`` — the signal that closes the orchestrator's SENSING loop.
        Call this once the swap has reached SENSING (after answering the feed prompt).
        """
        b = _brain()
        _require_sim(b)
        _armed_orchestrator(b, printer_id)
        await b.events.publish(SensorEvent(printer_id=printer_id, filament_present=present))
        return {"injected": "sensor", "printer_id": printer_id, "filament_present": present}

    return app
