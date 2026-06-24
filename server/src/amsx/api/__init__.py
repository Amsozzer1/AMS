"""api — FastAPI app: dashboard data, 3MF upload, live printer state, human-swap prompts.

The SPA front end consumes these endpoints (see the `frontend` agent). v0 runs in simulate
mode by default — no printer required — so `uv run amsx` starts and serves immediately.
"""

from __future__ import annotations

import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from ..brain import Brain, build_brain
from ..printer import Printer

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
    async def submit_job(printer_id: str, file: UploadFile) -> dict[str, Any]:
        b = _brain()
        if printer_id not in b.printers:
            raise HTTPException(status_code=404, detail=f"unknown printer {printer_id!r}")
        with tempfile.NamedTemporaryFile(delete=False, suffix=".gcode.3mf") as tmp:
            tmp.write(await file.read())
            saved = Path(tmp.name)
        try:
            orch = await b.submit_job(printer_id, saved)
        except Exception as exc:  # parse/transport errors -> 400 for the UI
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "printer_id": printer_id,
            "filename": file.filename,
            "planned_swaps": [
                {"seq": sw.seq, "filament_index": sw.filament_index, "tag": sw.tag}
                for sw in orch.plan.swaps
            ],
        }

    @app.get("/api/prompts")
    async def list_prompts() -> list[dict[str, Any]]:
        """Pending human-swap actions the orchestrator is waiting on."""
        return _brain().prompts.pending()

    @app.post("/api/prompts/{prompt_id}/answer")
    async def answer_prompt(prompt_id: str, response: str = "done") -> dict[str, Any]:
        if not _brain().prompts.answer(prompt_id, response):
            raise HTTPException(status_code=404, detail=f"unknown prompt {prompt_id!r}")
        return {"ok": True, "prompt_id": prompt_id}

    return app
