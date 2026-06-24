"""orchestration — the only sentient part of the system.

Design source: docs/02-architecture.md (8-step swap sequence, hybrid trigger, pause
validation, single-brain) and docs/10-domain-model.md (`Orchestrator`, `SwapStateMachine`,
`SwapContext`).

Three pieces:

* `SwapContext`  — per-swap working state (printer, old/next module, planned swap, retries).
* `SwapStateMachine` — drives WATCHING → UNLOADING → SELECTING → FEEDING → SENSING →
  RESUMING → WATCHING, with FAULT reachable from any step. It rides Bambu's OWN change
  routine via the `PrinterControl` protocol (Option A) and closes the sensing loop against
  the PRINTER's sensor — the module never reads it.
* `Orchestrator` — subscribes to PauseEvent / SensorEvent / FaultEvent on the EventBus,
  VALIDATES every pause against `plan.swaps[cursor]` (tag match), runs the swap, advances the
  cursor. An untagged / mismatched pause, a fault, or a disconnect is a safe-hold + alert —
  never a swap, never a guess.

Hard rule honored here: we depend ONLY on the `amsx.protocols.Module` / `PrinterControl`
Protocols — never a concrete printer/driver/HardwareModule. Async throughout; nothing blocks
the event loop.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from amsx.events import EventBus, FaultEvent, PauseEvent, SensorEvent
from amsx.protocols import Module, PrinterControl
from amsx.types import PlannedSwap, SwapPlan, SwapState

# Defaults for the v0 swap geometry. The retract distance is "enough to clear the shared hub
# line" (docs/02 — a full retract clears the line before the next feed). Tunable per install.
DEFAULT_RETRACT_MM = 120.0
DEFAULT_SENSE_TIMEOUT_S = 120.0
DEFAULT_SENSE_POLL_S = 0.5

# Alert sink: how the single brain raises a human-visible alert on any exception. Injectable.
Alerter = Callable[[str], Awaitable[None]]


async def _noop_alert(message: str) -> None:  # pragma: no cover - default sink
    return None


class PauseValidationError(Exception):
    """A pause we cannot match to our own plan (untagged / mismatched / out of swaps).

    Per docs/02 + docs/09 this is an EXCEPTION, never a swap: the orchestrator safe-holds and
    alerts. Carrying the offending event keeps the alert specific.
    """

    def __init__(self, message: str, event: PauseEvent) -> None:
        super().__init__(message)
        self.event = event


class SwapFault(Exception):
    """A swap step failed (sensor never tripped, a move faulted). The machine lands in FAULT."""


@dataclass
class SwapContext:
    """Per-swap working state (docs/10-domain-model.md). One instance per pause we act on."""

    printer: PrinterControl
    old_module: Module | None
    next_module: Module
    planned_swap: PlannedSwap
    retract_mm: float = DEFAULT_RETRACT_MM
    sense_timeout_s: float = DEFAULT_SENSE_TIMEOUT_S
    sense_poll_s: float = DEFAULT_SENSE_POLL_S
    retries: int = 0


class SwapStateMachine:
    """The heart: runs one swap through the documented sequence (docs/02 / docs/10).

    `state` is observable so the Orchestrator owns "am I mid-swap" and stray events can't
    double-trigger. `execute(ctx)` runs the full sequence and returns the terminal state
    (WATCHING on success, FAULT on failure). FAULT is reachable from any step.
    """

    def __init__(self) -> None:
        self.state: SwapState = SwapState.WATCHING
        # Set when a SensorEvent reports the printer's filament-present sensor tripping during
        # SENSING. Lets the closed loop react to a pushed event as well as polling.
        self._sensor_tripped = asyncio.Event()

    @property
    def busy(self) -> bool:
        return self.state not in (SwapState.WATCHING, SwapState.FAULT)

    def note_sensor(self, present: bool) -> None:
        """Feed a pushed SensorEvent into the sensing loop (orchestrator forwards these)."""
        if present:
            self._sensor_tripped.set()

    async def execute(self, ctx: SwapContext) -> SwapState:
        """Run the swap. Returns WATCHING on success; raises SwapFault (after landing in
        FAULT) on any failure, so the Orchestrator gets the specific reason to alert on.
        """
        try:
            await self._unloading(ctx)
            await self._selecting(ctx)
            await self._feeding(ctx)
            await self._sensing(ctx)
            await self._resuming(ctx)
            self.state = SwapState.WATCHING
            return self.state
        except SwapFault:
            await self._to_fault(ctx)
            raise
        except Exception as exc:  # any failure is the brain's to handle → FAULT, never a guess
            await self._to_fault(ctx)
            raise SwapFault(str(exc)) from exc

    # ---- steps ---------------------------------------------------------------------------
    async def _unloading(self, ctx: SwapContext) -> None:
        """UNLOAD: ride Bambu's unload routine, then retract the old module until the hub clears."""
        self.state = SwapState.UNLOADING
        await ctx.printer.routine_unload()
        if ctx.old_module is not None:
            # Bounded retract to clear the shared line; then confirm the module's LOCAL sensor
            # shows the filament has pulled clear of the module exit.
            result = await ctx.old_module.retract(ctx.retract_mm)
            if not result.ok:
                raise SwapFault(f"old module {ctx.old_module.id} retract failed: {result.reason}")

    async def _selecting(self, ctx: SwapContext) -> None:
        """SELECT: next_module was resolved from the plan's filament_index by the registry."""
        self.state = SwapState.SELECTING
        # Nothing to drive here in v0 — the Orchestrator resolved next_module before execute().
        # Kept as an explicit step so the sequence matches docs/02 and future inventory logic.

    async def _feeding(self, ctx: SwapContext) -> None:
        """FEED: start the next module feeding continuously toward the printer inlet."""
        self.state = SwapState.FEEDING
        await ctx.next_module.start_feed()

    async def _sensing(self, ctx: SwapContext) -> None:
        """SENSE (the closed loop): poll the PRINTER's sensor; stop() the module on trip.

        The module never reads the printer sensor — both signals live here in the brain. We
        race a poll loop against any pushed SensorEvent, and bound the whole thing by a
        timeout → FAULT (docs/02 step 6). On trip we stop the module's continuous feed.
        """
        self.state = SwapState.SENSING
        self._sensor_tripped.clear()
        try:
            tripped = await asyncio.wait_for(self._await_sensor(ctx), timeout=ctx.sense_timeout_s)
        except TimeoutError as exc:
            # Stop the module before faulting so it isn't left feeding into a jam.
            await ctx.next_module.stop()
            raise SwapFault(
                f"printer sensor never tripped within {ctx.sense_timeout_s}s — possible hub jam"
            ) from exc
        if not tripped:  # pragma: no cover - _await_sensor only returns True or times out
            await ctx.next_module.stop()
            raise SwapFault("sensing ended without a filament-present trip")
        await ctx.next_module.stop()

    async def _await_sensor(self, ctx: SwapContext) -> bool:
        """Return True once the printer reports filament present (poll OR pushed event)."""
        while True:
            if self._sensor_tripped.is_set():
                return True
            if await ctx.printer.filament_present():
                return True
            await asyncio.sleep(ctx.sense_poll_s)

    async def _resuming(self, ctx: SwapContext) -> None:
        """RESUME: hand back to Bambu's routine to load-to-nozzle, purge, and resume the print."""
        self.state = SwapState.RESUMING
        await ctx.printer.routine_confirm_resume()

    async def _to_fault(self, ctx: SwapContext) -> None:
        self.state = SwapState.FAULT
        # Best-effort: make sure the next module is not left feeding once we've faulted.
        try:
            await ctx.next_module.stop()
        except Exception:  # pragma: no cover - stop() failing during fault is non-fatal
            pass


class Orchestrator:
    """Ties the parsed plan + live events + module actions into one closed swap loop, for one
    print. The ONLY decision-maker (single-brain).

    Subscribes to PauseEvent / SensorEvent / FaultEvent. On a pause it validates against the
    plan, runs the swap via `SwapStateMachine`, and advances the cursor. Any exception
    (untagged pause, mismatched tag, sensor timeout, fault, disconnect) → safe-hold + alert.
    """

    def __init__(
        self,
        printer: PrinterControl,
        plan: SwapPlan,
        registry,  # ModuleRegistry; typed loosely to avoid a module<-orchestration import cycle
        bus: EventBus,
        *,
        printer_id: str,
        sm: SwapStateMachine | None = None,
        alerter: Alerter | None = None,
        retract_mm: float = DEFAULT_RETRACT_MM,
        sense_timeout_s: float = DEFAULT_SENSE_TIMEOUT_S,
        sense_poll_s: float = DEFAULT_SENSE_POLL_S,
    ) -> None:
        self.printer = printer
        self.plan = plan
        self.registry = registry
        self.bus = bus
        self.printer_id = printer_id
        self.sm = sm or SwapStateMachine()
        self._alert = alerter or _noop_alert
        self.cursor = 0
        self.held = False
        self.alerts: list[str] = []
        self._retract_mm = retract_mm
        self._sense_timeout_s = sense_timeout_s
        self._sense_poll_s = sense_poll_s
        # Serialize swap execution so two pauses can never run concurrently for one printer.
        self._swap_lock = asyncio.Lock()

    def subscribe(self) -> None:
        """Wire this orchestrator onto the bus. Call once before the print starts."""
        self.bus.subscribe(PauseEvent, self._on_event)
        self.bus.subscribe(SensorEvent, self._on_event)
        self.bus.subscribe(FaultEvent, self._on_event)

    @property
    def done(self) -> bool:
        return self.cursor >= len(self.plan)

    # ---- event dispatch ------------------------------------------------------------------
    async def _on_event(self, event) -> None:
        if isinstance(event, PauseEvent):
            await self.on_pause(event)
        elif isinstance(event, SensorEvent):
            self.on_sensor(event)
        elif isinstance(event, FaultEvent):
            await self.on_fault(event)

    def on_sensor(self, event: SensorEvent) -> None:
        """Forward the printer's sensor state into the sensing loop (closes the loop)."""
        if event.printer_id != self.printer_id:
            return
        self.sm.note_sensor(event.filament_present)

    async def on_fault(self, event: FaultEvent) -> None:
        """A printer/module/transport fault or disconnect → safe-hold + alert, never a swap."""
        await self._safe_hold(f"fault from {event.source}: {event.detail}")

    async def on_pause(self, event: PauseEvent) -> None:
        """The hybrid trigger. Validate against the plan, then run the swap. Exceptions hold."""
        if event.printer_id != self.printer_id:
            return
        # Already mid-swap or already held: a stray pause must not double-trigger.
        if self.sm.busy:
            await self._safe_hold(
                f"pause arrived while mid-swap (state={self.sm.state}); ignoring as stray"
            )
            return
        try:
            swap = self._validate(event)
        except PauseValidationError as exc:
            await self._safe_hold(str(exc))
            return

        async with self._swap_lock:
            next_module = self.registry.for_filament_index(swap.filament_index)
            old_module = self._current_old_module()
            ctx = SwapContext(
                printer=self.printer,
                old_module=old_module,
                next_module=next_module,
                planned_swap=swap,
                retract_mm=self._retract_mm,
                sense_timeout_s=self._sense_timeout_s,
                sense_poll_s=self._sense_poll_s,
            )
            try:
                await self.sm.execute(ctx)
            except SwapFault as exc:
                await self._safe_hold(f"swap #{swap.seq} faulted: {exc}")
                return
            # Success: this filament is now the loaded one; advance the cursor.
            self._loaded_index = swap.filament_index
            self.cursor += 1

    # ---- pause validation ----------------------------------------------------------------
    def _validate(self, event: PauseEvent) -> PlannedSwap:
        """Match a live pause to `plan.swaps[cursor]` by tag. Anything else is an exception.

        Rules (docs/02 / docs/09):
        * no swaps left at the cursor → stray pause, exception.
        * the pause carries no tag → a user/stray pause, never ours → exception.
        * the tag doesn't equal the expected swap's tag → mismatch → exception.
        Only a tag-exact match returns the planned swap to act on.
        """
        if self.cursor >= len(self.plan):
            raise PauseValidationError(
                f"pause with no remaining planned swap (cursor={self.cursor}, "
                f"swaps={len(self.plan)})",
                event,
            )
        expected = self.plan.swaps[self.cursor]
        if event.tag is None:
            raise PauseValidationError(
                f"untagged pause (reason={event.reason}) — not ours; expected tag "
                f"{expected.tag!r} for swap #{expected.seq}",
                event,
            )
        if event.tag != expected.tag:
            raise PauseValidationError(
                f"pause tag {event.tag!r} does not match expected {expected.tag!r} "
                f"for swap #{expected.seq}",
                event,
            )
        return expected

    # ---- helpers -------------------------------------------------------------------------
    _loaded_index: int | None = None

    def _current_old_module(self) -> Module | None:
        """The module believed loaded right now, if we can resolve it. None on the first swap."""
        if self._loaded_index is None:
            return None
        try:
            return self.registry.for_filament_index(self._loaded_index)
        except KeyError:
            return None

    async def _safe_hold(self, reason: str) -> None:
        self.held = True
        self.alerts.append(reason)
        await self._alert(reason)
