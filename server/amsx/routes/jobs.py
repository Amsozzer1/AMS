"""Uploading a sliced 3MF, arming the swap plan, confirming the mapping, and starting."""

from __future__ import annotations

import logging
import tempfile
from dataclasses import replace
from pathlib import Path

from fastapi import APIRouter, UploadFile

from amsx.apps.inventory.view import AssignmentResponse, AssignRow
from amsx.apps.job.view import JobResult, PlannedSwap, StartArmedResult
from amsx.errors import BadRequestError, ConflictError
from amsx.system.infra.http.view import OkResponse
from amsx.system.middlewares import BrainDep, require_printer

log = logging.getLogger("amsx.routes.jobs")

router = APIRouter(prefix="/api/printers", tags=["jobs"])


@router.post("/{printer_id}/job")
async def submit_job(
    brain: BrainDep, printer_id: str, file: UploadFile, start: bool = True
) -> JobResult:
    """Upload a sliced 3MF and arm the swap plan.

    ``start=true`` (default) also pushes (FTPS) + starts the print — the still-unverified
    v0.4 path. ``start=false`` ARMS ONLY: the operator starts the print themselves (Bambu
    Studio / SD) and the Brain owns the swap loop from the pause onward (no FTPS needed).
    """
    require_printer(brain, printer_id)
    log.info("job upload received — printer=%s file=%r start=%s", printer_id, file.filename, start)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".gcode.3mf") as tmp:
        tmp.write(await file.read())
        saved = Path(tmp.name)
    try:
        run = brain.submit_job(printer_id, saved) if start else brain.arm_job(printer_id, saved)
        orch = await run
    except Exception as exc:  # parse/transport errors -> 400 for the UI
        # Log the FULL exception here — otherwise a failed upload/start is invisible on the
        # server (it only became a UI 400), which looked exactly like "it just hangs".
        log.exception("job submit FAILED for %s", printer_id)
        raise BadRequestError(str(exc)) from exc
    log.info("job accepted for %s (started=%s)", printer_id, start)
    return JobResult(
        printer_id=printer_id,
        filename=file.filename,
        started=start,
        planned_swaps=[
            PlannedSwap(seq=sw.seq, filament_index=sw.filament_index, tag=sw.tag)
            for sw in orch.plan.swaps
        ],
    )


@router.post("/{printer_id}/job/start")
async def start_armed_job(brain: BrainDep, printer_id: str) -> StartArmedResult:
    """Push (FTPS) + start the job this printer is ALREADY armed with.

    The two-step flow: upload with ``?start=false`` to arm + propose the mapping, let the
    operator confirm it (POST ``/job/assignment``), then call this to start the held job
    WITHOUT re-arming (which would wipe the confirmed assignment). 409 if nothing is armed.
    """
    require_printer(brain, printer_id)
    try:
        await brain.start_armed(printer_id)
    except KeyError as exc:
        raise ConflictError(str(exc)) from exc
    except Exception as exc:  # FTPS/start transport errors -> 400 for the UI
        log.exception("start_armed FAILED for %s", printer_id)
        raise BadRequestError(str(exc)) from exc
    log.info("armed job started for %s", printer_id)
    return StartArmedResult(printer_id=printer_id, started=True)


@router.get("/{printer_id}/job/assignment")
async def get_assignment(brain: BrainDep, printer_id: str) -> AssignmentResponse:
    """Current spool-assignment proposal for the armed job on this printer.

    Returns rows (one per filament index from the plan), each with the module/spool the
    resolver proposed. `confirmed` is True once the operator has POST-confirmed the mapping.
    Returns empty rows + confirmed=False when no job is armed.
    """
    require_printer(brain, printer_id)
    proposal = brain.assignment.get(printer_id, {})
    rows = [AssignRow.from_proposed(row) for _idx, row in sorted(proposal.items())]
    return AssignmentResponse(rows=rows, confirmed=printer_id in brain.confirmed)


@router.post("/{printer_id}/job/assignment")
async def confirm_assignment(brain: BrainDep, printer_id: str, body: dict[str, str]) -> OkResponse:
    """Confirm (and optionally override) the index→module mapping.

    Body: `{index: module_id}` for each filament index. Persists each override into
    brain.assignment so a follow-up GET reflects the chosen module/status. For rows
    that carry a spool_id, also calls set_module on the store (SOFT — store errors are
    logged and skipped so Spoolman down never 500s this endpoint).
    Returns `{ok: true}`.
    """
    require_printer(brain, printer_id)
    proposal = brain.assignment.setdefault(printer_id, {})
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
                    await brain.store.set_module(row.spool_id, module_id)
                except Exception:
                    log.warning(
                        "set_module failed for spool %s → %s (soft)",
                        row.spool_id,
                        module_id,
                        exc_info=True,
                    )
    brain.confirmed.add(printer_id)
    return OkResponse(ok=True)
