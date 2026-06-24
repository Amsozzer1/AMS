"""module — the `Module` contract's v0 human-backed implementation, plus the registry and
cluster that resolve and serialize module motion.

Design source: docs/06-module-interface.md (the `Module` contract + `ManualModule`) and
docs/10-domain-model.md (`ModuleRegistry`, `Cluster`). We depend on the SHARED `Module`
Protocol in `amsx.protocols` and never redefine it: `ManualModule` (and a future
`HardwareModule`) are structurally interchangeable so the orchestrator never changes.

`ManualModule` makes each motion call a PROMPT to a human. The prompt mechanism is injectable
(an async callable) so tests can auto-answer without real stdin. The module is non-sentient and
stateless: it moves filament and reports its LOCAL sensor; it never reads the printer's sensor
and decides nothing (single-brain principle).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from amsx.protocols import Module
from amsx.types import ModuleId, ModuleState, MoveResult

T = TypeVar("T")

# An async prompt: given a message, return the human's answer (already stripped/lowercased by
# the default). Injectable so tests can auto-answer. Default talks to stdin/stdout off-thread.
Prompter = Callable[[str], Awaitable[str]]


async def _stdin_prompter(message: str) -> str:
    """Default prompt: print the message and read one line from stdin without blocking the loop."""

    def _ask() -> str:
        return input(f"{message} ").strip()

    return await asyncio.to_thread(_ask)


class ManualModule:
    """v0 module: a human performs every motion. Implements `amsx.protocols.Module`.

    Each call turns into a prompt and waits for the human (or the injected auto-answerer). The
    module tracks only its `id` and `state` per the docs/06 state machine — nothing else.
    """

    def __init__(
        self,
        module_id: ModuleId,
        *,
        prompter: Prompter | None = None,
        has_filament_default: bool = True,
    ) -> None:
        self.id: ModuleId = module_id
        self.state: ModuleState = ModuleState.IDLE
        self._prompter: Prompter = prompter or _stdin_prompter
        # LOCAL presence sensor stand-in for v0 (a real cheap sensor later). Starts loaded.
        self._has_filament = has_filament_default

    # ---- bounded motion (no external feedback) -------------------------------------------
    async def feed(self, mm: float, speed: float | None = None) -> MoveResult:
        self.state = ModuleState.FEEDING
        await self._prompter(
            f"[module {self.id}] FEED filament ~{mm:.0f}mm toward the hub, then confirm."
        )
        self.state = ModuleState.IDLE
        return MoveResult(ok=True, moved_mm=mm)

    async def retract(self, mm: float, speed: float | None = None) -> MoveResult:
        self.state = ModuleState.RETRACTING
        await self._prompter(
            f"[module {self.id}] RETRACT filament ~{mm:.0f}mm back onto the spool, then confirm."
        )
        self.state = ModuleState.IDLE
        return MoveResult(ok=True, moved_mm=mm)

    # ---- continuous motion (orchestrator closes the loop against the PRINTER sensor) ------
    async def start_feed(self, speed: float | None = None) -> None:
        self.state = ModuleState.FEEDING
        await self._prompter(
            f"[module {self.id}] START FEEDING continuously, confirm you have begun."
        )

    async def start_retract(self, speed: float | None = None) -> None:
        self.state = ModuleState.RETRACTING
        await self._prompter(
            f"[module {self.id}] START RETRACTING continuously, confirm you have begun."
        )

    async def stop(self) -> None:
        await self._prompter(f"[module {self.id}] STOP — confirm you have stopped moving filament.")
        self.state = ModuleState.IDLE

    # ---- sensing (LOCAL sensor at the module exit only) ----------------------------------
    async def has_filament(self) -> bool:
        return self._has_filament

    def set_has_filament(self, present: bool) -> None:
        """Test/UI hook to flip the local presence sensor (a human or real sensor in v0)."""
        self._has_filament = present
        if not present:
            self.state = ModuleState.EMPTY

    # ---- lifecycle / safety --------------------------------------------------------------
    async def abort(self) -> None:
        await self._prompter(
            f"[module {self.id}] ABORT — hard stop. Confirm filament is held safe."
        )
        self.state = ModuleState.FAULT


class ModuleRegistry:
    """Resolves "which module" for a swap. Config map now; Spoolman material match later.

    Holds `Module` protocol objects (any implementation) and a `filament_index -> module_id`
    map so the orchestrator can pick the next module from the parsed plan's `filament_index`.
    """

    def __init__(self, modules: list[Module], filament_index_map: dict[int, ModuleId]) -> None:
        self._by_id: dict[ModuleId, Module] = {m.id: m for m in modules}
        self._by_index = dict(filament_index_map)

    def by_id(self, module_id: ModuleId) -> Module:
        try:
            return self._by_id[module_id]
        except KeyError as exc:
            raise KeyError(f"no module with id {module_id!r}") from exc

    def for_filament_index(self, index: int) -> Module:
        try:
            module_id = self._by_index[index]
        except KeyError as exc:
            raise KeyError(f"no module mapped to filament_index {index}") from exc
        return self.by_id(module_id)


class Cluster:
    """One ESP32's worth of modules, enforcing the shared-line rule: ONE module moves at a time.

    The hub merges N PTFE leads into one line, so two modules feeding at once would collide.
    `Cluster` is the interlock: `move(module, motion)` acquires the cluster's single active
    slot, runs the motion, and releases it. `motion` is a zero-arg factory that produces the
    awaitable so we only ever start it once the slot is held (no dangling coroutine on reject).
    A second module trying to move while one is active raises `ClusterBusyError` (the
    orchestrator decides what to do — it never silently overlaps moves).
    """

    def __init__(self, cluster_id: str, modules: list[Module]) -> None:
        self.id = cluster_id
        self._modules: dict[ModuleId, Module] = {m.id: m for m in modules}
        self.active: ModuleId | None = None
        self._lock = asyncio.Lock()

    @property
    def modules(self) -> list[Module]:
        return list(self._modules.values())

    async def move(self, module: Module, motion: Callable[[], Awaitable[T]]) -> T:
        """Run `motion()` for `module` under the one-at-a-time interlock.

        `motion` is a zero-arg factory; it is only invoked once the slot is held, so a rejected
        move never leaves an un-awaited coroutine. Raises ClusterBusyError if another module
        already holds the active slot — a stray concurrent move can never collide on the line.
        """
        if module.id not in self._modules:
            raise KeyError(f"module {module.id!r} not in cluster {self.id!r}")
        if self.active is not None and self.active != module.id:
            raise ClusterBusyError(
                f"cluster {self.id!r} busy: module {self.active!r} is moving, "
                f"cannot move {module.id!r}"
            )
        async with self._lock:
            self.active = module.id
            try:
                return await motion()
            finally:
                self.active = None


class ClusterBusyError(RuntimeError):
    """Raised when a second module tries to move while the cluster's active slot is held."""
