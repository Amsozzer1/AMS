"""protocols — every swappable seam in the system, in one file.

RULE 1 says each layer depends on the one below through a *named seam*. These are those seams,
collected here so "what can I swap out, and what would I have to implement?" is one file rather
than a hunt across six modules.

Each Protocol is **structural**: an implementation satisfies it by having the right methods, not
by inheriting from it. `ManualModule` names no base class at all and still satisfies `Module`.
That is what lets v0 (a human) become Phase 1 (a motor) as a drop-in swap, and what lets every
test run against a simulator with no printer, no broker, and no network.

Depends only on the rest of `types` and on `enums` — never on an implementation.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..enums import ModuleState, PauseReason
from .filament import FilamentRef
from .ids import ModuleId, PrinterId
from .spool import Spool, SpoolSpec
from .swap import MoveResult
from .wire import Report, ReportHandler

__all__ = [
    "FtpClient",
    "Module",
    "PrinterControl",
    "PrinterDriver",
    "PrinterLink",
    "SpoolStore",
]


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


@runtime_checkable
class PrinterLink(Protocol):
    """One per printer. Out on ``device/{serial}/request``; in on ``device/{serial}/report``.

    Both the real (MQTT) and simulated implementations satisfy this Protocol so ``Printer`` is
    transport-agnostic. ``request`` sends a command payload; ``on_report`` registers the
    handler that receives full + delta reports.
    """

    printer_id: PrinterId
    serial: str

    async def request(self, payload: Report) -> None: ...

    def on_report(self, handler: ReportHandler) -> None: ...


@runtime_checkable
class FtpClient(Protocol):
    """Uploads the sliced ``.gcode.3mf`` to the printer over FTPS and returns its remote path."""

    async def upload(self, printer: PrinterId, file: str) -> str: ...


@runtime_checkable
class PrinterDriver(Protocol):
    """Model-specific command builder. Option A: ride Bambu's existing change routine.

    Methods return the request payload (a dict) to be sent over the ``PrinterLink`` — keeping
    the driver pure/testable and the link responsible for the wire. The Printer owns sequencing
    and state; the driver only knows "what does an unload look like on *this* model".
    """

    model: str

    def request_unload(self) -> Report: ...
    def request_extrude(self) -> Report: ...
    def request_confirm_resume(self) -> Report: ...
    def request_start_print(self, remote_path: str) -> Report: ...

    def parse_pause_reason(self, report: Report) -> PauseReason: ...
    def parse_filament_present(self, report: Report) -> bool | None: ...

    def parse_external_filament(self, report: Report) -> tuple[str | None, str | None]: ...
    def request_set_external_filament(
        self,
        material: str | None,
        color_hex: str | None,
        *,
        tray_info_idx: str = "GFL04",
        tmin: int = 190,
        tmax: int = 240,
    ) -> Report: ...


@runtime_checkable
class SpoolStore(Protocol):
    """The spool catalog. Spoolman is a SOFT dependency: a real store that can't reach Spoolman
    returns empty/None and logs, never raising into the swap path.
    """

    async def list_spools(self, *, include_archived: bool = False) -> list[Spool]: ...
    async def get_spool(self, spool_id: str) -> Spool | None: ...
    async def loaded_in(self, module_id: ModuleId) -> Spool | None: ...
    async def set_module(self, spool_id: str, module_id: ModuleId | None) -> None: ...
    async def match(self, material: str | None, color_hex: str | None) -> list[Spool]: ...
    async def consume(self, spool_id: str, grams: float) -> None: ...
    async def ensure_module_field(self) -> None: ...
    async def create_spool(self, spec: SpoolSpec) -> Spool: ...
    async def update_spool(
        self,
        spool_id: str,
        *,
        remaining_g: float | None = None,
        location: str | None = None,
        archived: bool | None = None,
    ) -> Spool: ...
    async def delete_spool(self, spool_id: str) -> None: ...
