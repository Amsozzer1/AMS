"""Structural contracts (typing.Protocol) for the swappable parts.

The Orchestrator depends ONLY on these — never on a concrete `ManualModule`, `HardwareModule`,
or `X1P1Driver`. That is what makes v0 (human module) → Phase 1 (motor) a drop-in swap, and
lets the printer be a simulator in tests. See docs/06-module-interface.md and
docs/10-domain-model.md. Keep dependency-free.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .types import FilamentRef, ModuleId, ModuleState, MoveResult


@runtime_checkable
class Module(Protocol):
    """One spool's actuator. Non-sentient, stateless; moves filament and reports its LOCAL
    sensor. It does NOT read the printer's sensor and decides nothing (single-brain).
    """

    id: ModuleId
    state: ModuleState

    # bounded motion (no external feedback) — e.g. retract a known distance to clear the hub
    async def feed(self, mm: float, speed: float | None = None) -> MoveResult: ...
    async def retract(self, mm: float, speed: float | None = None) -> MoveResult: ...

    # continuous motion — orchestrator closes the loop against the PRINTER sensor
    async def start_feed(self, speed: float | None = None) -> None: ...
    async def start_retract(self, speed: float | None = None) -> None: ...
    async def stop(self) -> None: ...

    # sensing (LOCAL sensor at the module exit only)
    async def has_filament(self) -> bool: ...

    # lifecycle / safety
    async def abort(self) -> None: ...


@runtime_checkable
class PrinterControl(Protocol):
    """What the Orchestrator needs from a printer, hiding X1/P1 vs A1 and MQTT vs simulator.

    Mirrors the Option-A routine (docs/02 / docs/10): we drive Bambu's OWN change routine, we
    never author hotend gcode. `loaded_filament` is Pi-authoritative.
    """

    @property
    def loaded_filament(self) -> FilamentRef | None: ...

    async def filament_present(self) -> bool: ...

    # drive Bambu's existing change routine over MQTT
    async def routine_unload(self) -> None: ...
    async def routine_extrude(self) -> None: ...
    async def routine_confirm_resume(self) -> None: ...

    # job lifecycle
    async def send_job(self, file: str) -> str: ...
    async def start_print(self, path: str) -> None: ...
