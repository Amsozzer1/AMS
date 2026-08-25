"""Simulate-only hooks: drive the whole swap loop with no printer on the LAN.

These inject the two signals the orchestrator would otherwise get over MQTT — the
filament-change pause and the printer's filament-present sensor — so a client can walk the v0
money shot end to end. They are the missing seam between SimulatedPrinterLink and the API.

This router is mounted ONLY when the Brain is in simulate mode (see infra/http), so a real
deployment does not expose them at all. `SimOnlyDep` is the second lock on the same door.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter

from amsx.apps.printer.view import SimPauseResult, SimSensorResult
from amsx.enums import PauseReason
from amsx.errors import ConflictError
from amsx.events import PauseEvent, SensorEvent
from amsx.system.middlewares import SimOnlyDep, armed_orchestrator

router = APIRouter(prefix="/api/printers", tags=["sim"])

# Strong refs to fire-and-forget swap tasks so the loop can't GC them mid-swap.
_bg_tasks: set[asyncio.Task] = set()


# `response_model_exclude_unset` keeps the historical sparse shape: a tagged pause
# returns `tag` and no `line` key at all, and vice versa. Clients that test for key
# PRESENCE (rather than value) would otherwise see both keys, one of them null.
@router.post("/{printer_id}/sim/pause", response_model_exclude_unset=True)
async def sim_pause(
    brain: SimOnlyDep, printer_id: str, tag: str | None = None, line: int | None = None
) -> SimPauseResult:
    """Inject a filament-change pause (simulate mode only).

    Default (no params): an UNTAGGED pause carrying the next expected swap's gcode ``line`` —
    exactly what a real Bambu ``M400 U1`` looks like, so it exercises the #17 ordinal+line
    guard the real loop uses. Pass ``?line=`` to force a different line (e.g. a far value to
    hit the safe-hold path), or ``?tag=`` to inject a tagged pause (and force a tag mismatch).
    Returns immediately; the swap then blocks on the human prompt — poll ``/api/prompts``.
    """
    orch = armed_orchestrator(brain, printer_id)
    if tag is not None:
        event = PauseEvent(printer_id=printer_id, reason=PauseReason.CHANGE, tag=tag)
        injected = SimPauseResult(injected="pause", printer_id=printer_id, tag=tag)
    else:
        if line is None:
            if orch.done:
                raise ConflictError("no remaining planned swap (plan complete)")
            line = orch.plan.swaps[orch.cursor].line
        # reason=UNKNOWN mirrors the A1 (it doesn't classify the pause); the orchestrator
        # binds it positionally and confirms with the line guard.
        event = PauseEvent(printer_id=printer_id, reason=PauseReason.UNKNOWN, tag=None, line=line)
        injected = SimPauseResult(injected="pause", printer_id=printer_id, line=line)
    # Don't await: on_pause runs the whole swap, which blocks on the human prompt. Fire it
    # onto the loop and return so the client can answer prompts + trip the sensor.
    task = asyncio.create_task(brain.events.publish(event))
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)
    return injected


@router.post("/{printer_id}/sim/sensor")
async def sim_sensor(brain: SimOnlyDep, printer_id: str, present: bool = True) -> SimSensorResult:
    """Trip (or clear) the printer's filament-present sensor (simulate mode only).

    Publishes a ``SensorEvent`` — the signal that closes the orchestrator's SENSING loop.
    Call this once the swap has reached SENSING (after answering the feed prompt).
    """
    armed_orchestrator(brain, printer_id)
    await brain.events.publish(SensorEvent(printer_id=printer_id, filament_present=present))
    return SimSensorResult(printer_id=printer_id, filament_present=present)
