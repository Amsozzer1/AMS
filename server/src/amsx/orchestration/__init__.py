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
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from amsx.events import EventBus, FaultEvent, PauseEvent, SensorEvent
from amsx.inventory import SpoolStore
from amsx.protocols import Module, PrinterControl
from amsx.types import PauseReason, PlannedSwap, SwapPlan, SwapState

log = logging.getLogger("amsx.orchestration")

# Defaults for the v0 swap geometry. The retract distance is "enough to clear the shared hub
# line" (docs/02 — a full retract clears the line before the next feed). Tunable per install.
DEFAULT_RETRACT_MM = 120.0
DEFAULT_SENSE_TIMEOUT_S = 120.0
DEFAULT_SENSE_POLL_S = 0.5

# Guard tolerances for untagged (real Bambu) pauses (open question #17). The cursor is the source
# of truth for *which* swap; the layer/line is only a GUARD that the cursor-th change is genuinely
# happening here and not at a stray/user pause.
#
# LAYER is the primary guard: the A1 reports mc_print_line_number as 0 at the pause (so the gcode
# line can't guard), but layer_num IS reported correctly (confirmed live 2026-06-25: M400 U1 at
# line 133871 = layer 75, printer reported layer 75 at the pause). ±1 absorbs an off-by-one if the
# printer increments its layer counter right at the change boundary; kept tight so it can't bind a
# non-adjacent change. Pauses arriving in order plus the advancing cursor disambiguate multiple
# changes on the same layer.
DEFAULT_LAYER_TOLERANCE = 1

# LINE is the fallback guard for printers that report a usable mc_print_line_number (e.g. X1/P1).
# The printer can report the line slightly before/after the exact M400 U1 line, so we accept a
# small window rather than an exact match; bounded by the previous/next swap lines so it can't
# swallow a neighbouring change.
DEFAULT_LINE_TOLERANCE = 50

# Alert sink: how the single brain raises a human-visible alert on any exception. Injectable.
Alerter = Callable[[str], Awaitable[None]]


async def _noop_alert(message: str) -> None:  # pragma: no cover - default sink
    return None


async def consume_plan(
    store: SpoolStore,
    plan: SwapPlan,
    *,
    assignment: dict[int, str],
    loaded: dict[str, str],
) -> None:
    """Aggregate the plan's per-index grams by spool and decrement each (best-effort, SOFT).

    `assignment` maps filament_index → module_id (from the confirmed assignment).
    `loaded` maps module_id → spool_id (from the live inventory).
    Both should be pre-built by the caller from Brain.assignment and store.list_spools().
    """
    grams_by_spool: dict[str, float] = {}
    for fc in plan.colors:
        module = assignment.get(fc.index)
        spool_id = loaded.get(module) if module else None
        if spool_id and fc.grams:
            grams_by_spool[spool_id] = grams_by_spool.get(spool_id, 0.0) + fc.grams
    for spool_id, grams in grams_by_spool.items():
        try:
            await store.consume(spool_id, grams)
        except Exception:  # SOFT — consume errors must never break the swap path
            pass


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
        log.info(
            "swap #%d [%s]: UNLOADING — unload_filament%s",
            ctx.planned_swap.seq,
            ctx.planned_swap.tag,
            f" + retract old module {ctx.old_module.id}" if ctx.old_module else "",
        )
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
        log.info(
            "swap #%d [%s]: FEEDING — module %s (filament_index=%s)",
            ctx.planned_swap.seq,
            ctx.planned_swap.tag,
            ctx.next_module.id,
            ctx.planned_swap.filament_index,
        )
        await ctx.next_module.start_feed()

    async def _sensing(self, ctx: SwapContext) -> None:
        """SENSE (the closed loop): poll the PRINTER's sensor; stop() the module on trip.

        The module never reads the printer sensor — both signals live here in the brain. We
        race a poll loop against any pushed SensorEvent, and bound the whole thing by a
        timeout → FAULT (docs/02 step 6). On trip we stop the module's continuous feed.
        """
        self.state = SwapState.SENSING
        log.info(
            "swap #%d [%s]: SENSING — waiting for the printer filament sensor (timeout %.0fs)",
            ctx.planned_swap.seq,
            ctx.planned_swap.tag,
            ctx.sense_timeout_s,
        )
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
        """RESUME: hand back to Bambu's routine to load-to-nozzle, purge, and resume the print.

        If the swap carries colour/material metadata, also tell the printer what it now holds via
        `set_external_filament`. This is guarded — `PrinterControl` doesn't declare the method, so
        we use `getattr` to stay compatible with simulators/fakes that don't implement it.
        """
        self.state = SwapState.RESUMING
        log.info(
            "swap #%d [%s]: RESUMING — sensor tripped, resuming the print",
            ctx.planned_swap.seq,
            ctx.planned_swap.tag,
        )
        await ctx.printer.routine_confirm_resume()
        # set_external_filament fires AFTER routine_confirm_resume intentionally: the routine
        # completes the load-to-nozzle + purge sequence, so by the time we tag the filament the
        # printer actually holds what we're declaring (tells it what it now holds post-resume).
        # Tell the printer what filament it now holds (best-effort: simulators/fakes may not have
        # set_external_filament, so guard with getattr and swallow errors softly).
        _set_ext = getattr(ctx.printer, "set_external_filament", None)
        if _set_ext is not None and (
            ctx.planned_swap.material is not None or ctx.planned_swap.color_hex is not None
        ):
            try:
                await _set_ext(ctx.planned_swap.material, ctx.planned_swap.color_hex)
                log.info(
                    "swap #%d [%s]: set_external_filament → material=%s color=%s",
                    ctx.planned_swap.seq,
                    ctx.planned_swap.tag,
                    ctx.planned_swap.material,
                    ctx.planned_swap.color_hex,
                )
            except Exception:  # SOFT — don't break the swap if this fails
                log.warning(
                    "swap #%d: set_external_filament failed (soft)",
                    ctx.planned_swap.seq,
                    exc_info=True,
                )

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
        layer_tolerance: int = DEFAULT_LAYER_TOLERANCE,
        line_tolerance: int = DEFAULT_LINE_TOLERANCE,
        module_resolver: Callable[[int], Module] | None = None,
    ) -> None:
        self.printer = printer
        self.plan = plan
        self.registry = registry
        # filament_index -> Module. Defaults to the static config map; the Brain passes a resolver
        # that prefers the operator's confirmed colour→module assignment, falling back to config.
        self._module_for_index: Callable[[int], Module] = (
            module_resolver or registry.for_filament_index
        )
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
        self._layer_tolerance = layer_tolerance
        self._line_tolerance = line_tolerance
        # The gcode line of the last pause we ACCEPTED. Lower bound for the next pause's line
        # guard: a genuine cursor-th change is at/after the previous accepted change's line.
        self._last_accepted_line: int | None = None
        # Serialize swap execution so two pauses can never run concurrently for one printer.
        self._swap_lock = asyncio.Lock()

    # The event types this orchestrator listens on (kept so subscribe/unsubscribe stay symmetric).
    _EVENT_TYPES = (PauseEvent, SensorEvent, FaultEvent)

    def subscribe(self) -> None:
        """Wire this orchestrator onto the bus. Call once before the print starts."""
        for event_type in self._EVENT_TYPES:
            self.bus.subscribe(event_type, self._on_event)

    def unsubscribe(self) -> None:
        """Detach from the bus. Called when this printer is re-armed so a stale orchestrator
        can't also hear the next pause and run the swap a second time (the duplicate-prompt bug).
        """
        for event_type in self._EVENT_TYPES:
            self.bus.unsubscribe(event_type, self._on_event)

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
        log.info(
            "orchestrator [%s]: pause received (tag=%s reason=%s line=%s) — cursor %d/%d",
            self.printer_id,
            event.tag,
            event.reason,
            event.line,
            self.cursor,
            len(self.plan),
        )
        # Already mid-swap or already held: a stray pause must not double-trigger.
        if self.sm.busy:
            await self._safe_hold(
                f"pause arrived while mid-swap (state={self.sm.state}); ignoring as stray"
            )
            return
        try:
            swap, unguarded = self._validate(event)
        except PauseValidationError as exc:
            await self._safe_hold(str(exc))
            return

        if unguarded is not None:
            # We accepted the swap ordinally (cursor is the source of truth) but could not apply
            # the line guard — alert so a human knows the loop ran UNGUARDED, but don't hold.
            self.alerts.append(unguarded)
            await self._alert(unguarded)

        async with self._swap_lock:
            # SELECTING: resolve the module via the injected resolver (operator's confirmed
            # colour→module assignment, falling back to the static config map).
            next_module = self._module_for_index(swap.filament_index)
            old_module = self._current_old_module()
            log.info(
                "orchestrator [%s]: pause ACCEPTED as swap #%d → running swap (module %s)",
                self.printer_id,
                swap.seq,
                next_module.id,
            )
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
            # Remember where this accepted change happened so the NEXT untagged pause's line
            # guard has a lower bound (a later change is at/after this one's line).
            if event.line is not None:
                self._last_accepted_line = event.line
            self.cursor += 1
            log.info(
                "orchestrator [%s]: ✓ swap #%d COMPLETE — cursor %d/%d%s",
                self.printer_id,
                swap.seq,
                self.cursor,
                len(self.plan),
                " (print plan done)" if self.done else "",
            )

    # ---- pause validation ----------------------------------------------------------------
    def _validate(self, event: PauseEvent) -> tuple[PlannedSwap, str | None]:
        """Bind a live pause to `plan.swaps[cursor]` (open question #17).

        The CURSOR is the source of truth for sequencing: the k-th `M400 U1` pause is swap
        cursor k-1. Returns `(swap, unguarded_alert)`; `unguarded_alert` is non-None when the
        swap was accepted ordinally but the line guard could not be applied (caller alerts but
        does not hold). Anything we cannot safely bind raises PauseValidationError → safe-hold.

        Two binding paths:
        * Tagged pause (sim hooks + authored pauses): exact tag match against the expected
          swap — equal accepts, otherwise mismatch → exception. (Preserves all existing tests.)
        * Untagged pause (the real Bambu `M400 U1`, which carries no tag): an explicit USER
          pause is never ours; a CHANGE/UNKNOWN pause is bound by the LINE guard (or, if line
          info is missing, degraded to pure ordinal with an "unguarded" alert).
        """
        if self.cursor >= len(self.plan):
            raise PauseValidationError(
                f"pause with no remaining planned swap (cursor={self.cursor}, "
                f"swaps={len(self.plan)})",
                event,
            )
        expected = self.plan.swaps[self.cursor]

        # --- tagged path: exact match exactly as before (sim/pause hook, authored pauses) ----
        if event.tag is not None:
            if event.tag != expected.tag:
                raise PauseValidationError(
                    f"pause tag {event.tag!r} does not match expected {expected.tag!r} "
                    f"for swap #{expected.seq}",
                    event,
                )
            return expected, None

        # --- untagged path: the real Bambu pause (open question #17) -------------------------
        if event.reason is PauseReason.USER:
            # An explicit user pause is never our planned swap.
            raise PauseValidationError(
                f"untagged user pause (reason={event.reason}) — not a planned swap; "
                f"expected swap #{expected.seq}",
                event,
            )

        # CHANGE / UNKNOWN (the A1 reports UNKNOWN). Bind by LAYER first — it's the only reliable
        # position on the A1 (mc_print_line_number is 0 at the pause, layer_num is correct). Fall
        # back to the LINE guard for printers that report a usable line, then to pure ordinal.
        if event.layer is not None and expected.layer is not None:
            if abs(event.layer - expected.layer) > self._layer_tolerance:
                raise PauseValidationError(
                    f"untagged pause at layer {event.layer} is out of range for swap "
                    f"#{expected.seq} (expected.layer={expected.layer}, "
                    f"tol=±{self._layer_tolerance}) — not the cursor-th planned change",
                    event,
                )
            return expected, None

        # No layer to bind on → the LINE guard (X1/P1 may report a usable line; a falsy line — the
        # A1's 0 or a missing value — is treated as "no usable line").
        if event.line and expected.line is not None:
            # Lower bound: at/after the previous accepted swap's line (a later change can't be
            # earlier in the file). Upper bound: before the NEXT planned swap's line, so a stray
            # pause that belongs to a later change can't be eaten here.
            next_line = self._next_swap_line()
            low = expected.line - self._line_tolerance
            if self._last_accepted_line is not None:
                low = max(low, self._last_accepted_line)
            high = min(expected.line + self._line_tolerance, next_line)
            if not (low <= event.line < high):
                raise PauseValidationError(
                    f"untagged pause line {event.line} is out of range for swap #{expected.seq} "
                    f"(expected.line={expected.line}, tol=±{self._line_tolerance}, "
                    f"accepted window [{low}, {high})) — not the cursor-th planned change",
                    event,
                )
            return expected, None

        # Neither layer nor line to guard against → pure ordinal, flagged UNGUARDED (the cursor is
        # still correct; a human is told the loop ran without a position guard).
        return expected, (
            f"untagged pause accepted UNGUARDED (ordinal-only) for swap #{expected.seq}: "
            f"no layer/line to guard against (event.layer={event.layer}, "
            f"event.line={event.line}, expected.layer={expected.layer}, "
            f"expected.line={expected.line})"
        )

    def _next_swap_line(self) -> float:
        """The gcode line of the swap AFTER the cursor (upper bound), or +inf if none/unknown."""
        nxt = self.cursor + 1
        if nxt < len(self.plan):
            line = self.plan.swaps[nxt].line
            if line is not None:
                return float(line)
        return float("inf")

    # ---- helpers -------------------------------------------------------------------------
    _loaded_index: int | None = None

    def _current_old_module(self) -> Module | None:
        """The module believed loaded right now, if we can resolve it. None on the first swap."""
        if self._loaded_index is None:
            return None
        try:
            return self._module_for_index(self._loaded_index)
        except KeyError:
            return None

    async def _safe_hold(self, reason: str) -> None:
        self.held = True
        self.alerts.append(reason)
        log.warning("orchestrator [%s]: ⚠ SAFE-HOLD — %s", self.printer_id, reason)
        await self._alert(reason)
