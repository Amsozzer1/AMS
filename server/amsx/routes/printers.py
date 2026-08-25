"""Printer state: the list, one printer, and the full raw-report detail view."""

from __future__ import annotations

from fastapi import APIRouter

from amsx.apps.printer.view import PrinterDetail, PrinterState
from amsx.errors import NotFoundError
from amsx.system.brain import Brain
from amsx.system.middlewares import BrainDep

router = APIRouter(prefix="/api/printers", tags=["printers"])


def _detail(brain: Brain, printer) -> PrinterDetail:
    """Everything we know about one printer: modeled state + identity + the full raw report.

    Composed here rather than on the model because it draws on two sources (the live Printer
    and the Brain's config). The access code is never included.
    """
    cfg = next((p for p in brain.config.printers if p.id == printer.id), None)
    bus = getattr(printer.link, "bus", None)
    return PrinterDetail(
        **PrinterState.from_printer(printer).model_dump(),
        serial=cfg.serial if cfg else printer.link.serial,
        model=cfg.model if cfg else printer.driver.model,
        ip=cfg.ip if cfg else None,
        simulate=brain.simulate,
        # SimulatedPrinterLink has no bus → always "connected".
        connected=True if bus is None else bool(getattr(bus, "connected", False)),
        seeded=printer._seeded,
        raw=printer.state.raw,
    )


@router.get("")
async def list_printers(brain: BrainDep) -> list[PrinterState]:
    return [PrinterState.from_printer(p) for p in brain.printers.values()]


@router.get("/{printer_id}")
async def get_printer(brain: BrainDep, printer_id: str) -> PrinterState:
    printer = brain.printers.get(printer_id)
    if printer is None:
        raise NotFoundError(f"unknown printer {printer_id!r}")
    return PrinterState.from_printer(printer)


@router.get("/{printer_id}/detail")
async def get_printer_detail(brain: BrainDep, printer_id: str) -> PrinterDetail:
    """Full per-printer view (modeled state + identity + complete raw report)."""
    printer = brain.printers.get(printer_id)
    if printer is None:
        raise NotFoundError(f"unknown printer {printer_id!r}")
    return _detail(brain, printer)
