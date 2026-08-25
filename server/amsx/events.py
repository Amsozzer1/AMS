"""Typed events + a tiny async pub/sub bus.

The transport/printer layers turn raw MQTT reports into these typed events; the Orchestrator
subscribes. This is the `EventBus` of docs/10-domain-model.md ("reports become typed events").
Keep it dependency-free (stdlib only) so every layer can import it.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from .types import ModuleId, ModuleState, PauseReason, PrinterId


# ---- event payloads ----
@dataclass(frozen=True)
class PauseEvent:
    """Printer reported a pause. `reason`/`tag`/`line` feed the orchestrator's plan validation.

    `line` is the printer's reported gcode line (`mc_print_line_number`) at the pause — the
    unique, monotonic position that lets the orchestrator confirm an untagged Bambu `M400 U1`
    pause is genuinely the cursor-th planned change (open question #17). `layer` is the coarser
    fallback (breaks when a layer has multiple changes).
    """

    printer_id: PrinterId
    reason: PauseReason = PauseReason.UNKNOWN
    tag: str | None = None
    layer: int | None = None
    line: int | None = None


@dataclass(frozen=True)
class SensorEvent:
    """The printer's own filament-present sensor changed state (read over MQTT)."""

    printer_id: PrinterId
    filament_present: bool


@dataclass(frozen=True)
class ModuleEvent:
    """A module emitted one of MOVE_COMPLETE / FILAMENT_PRESENT / FILAMENT_ABSENT / FAULT."""

    module_id: ModuleId
    kind: str
    state: ModuleState | None = None


@dataclass(frozen=True)
class FaultEvent:
    """Something faulted (printer, module, or transport). Orchestrator → safe-hold + alert."""

    source: str
    detail: str


@dataclass(frozen=True)
class FinishedEvent:
    """Printer reported gcode_state→FINISH. Brain uses this to consume spool grams (SOFT)."""

    printer_id: PrinterId


Event = PauseEvent | SensorEvent | ModuleEvent | FaultEvent | FinishedEvent
Handler = Callable[[Event], Awaitable[None]]


class EventBus:
    """Minimal async pub/sub keyed by event type. Handlers are coroutines.

    Intentionally tiny — may later wrap MqttBus directly. Publishing awaits all matching
    handlers; a handler raising is surfaced (the single brain must see its own failures).
    """

    def __init__(self) -> None:
        self._handlers: dict[type, list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: type, handler: Handler) -> None:
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: type, handler: Handler) -> None:
        """Remove a previously-subscribed handler (idempotent — a no-op if not present).

        Needed so re-arming a printer can tear down its old Orchestrator's subscription; otherwise
        a stale orchestrator keeps hearing pauses and the swap runs twice.
        """
        handlers = self._handlers.get(event_type)
        if handlers and handler in handlers:
            handlers.remove(handler)

    async def publish(self, event: Event) -> None:
        # Snapshot so a handler that (un)subscribes mid-dispatch can't mutate what we're iterating.
        handlers = list(self._handlers.get(type(event), []))
        if handlers:
            await asyncio.gather(*(h(event) for h in handlers))
