"""Test doubles for the orchestrator suite — a scriptable printer simulator and helpers.

These live entirely in the test tree (the orchestrator must be provable with NO real hardware
and NO real printer package). `FakePrinter` implements the `amsx.protocols.PrinterControl`
Protocol structurally and records the Option-A routine calls so tests can assert the swap
sequence. `auto_answer` builds a `Prompter` that auto-confirms `ManualModule` prompts so tests
never touch stdin.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from amsx.types import FilamentRef


class FakePrinter:
    """A scriptable `PrinterControl`. `filament_present()` returns False until the test trips
    it (directly, or after N polls), so we can drive the closed sensing loop deterministically.
    Records every routine_* call in `calls` for sequence assertions.
    """

    def __init__(
        self,
        *,
        trip_after_polls: int | None = None,
        loaded_filament: FilamentRef | None = None,
    ) -> None:
        self.calls: list[str] = []
        self._present = False
        self._polls = 0
        # If set, filament_present() flips to True on the Nth poll (simulates feed reaching
        # the sensor). If None, the sensor stays down until trip() is called (or never → timeout).
        self._trip_after_polls = trip_after_polls
        self._loaded_filament = loaded_filament

    # ---- PrinterControl ------------------------------------------------------------------
    @property
    def loaded_filament(self) -> FilamentRef | None:
        return self._loaded_filament

    async def filament_present(self) -> bool:
        self._polls += 1
        if self._trip_after_polls is not None and self._polls >= self._trip_after_polls:
            self._present = True
        return self._present

    async def routine_unload(self) -> None:
        self.calls.append("routine_unload")

    async def routine_extrude(self) -> None:
        self.calls.append("routine_extrude")

    async def routine_confirm_resume(self) -> None:
        self.calls.append("routine_confirm_resume")

    async def send_job(self, file: str) -> str:
        self.calls.append(f"send_job:{file}")
        return f"/cache/{file}"

    async def start_print(self, path: str) -> None:
        self.calls.append(f"start_print:{path}")

    # ---- test controls -------------------------------------------------------------------
    def trip(self) -> None:
        """Force the printer's filament-present sensor to read True from now on."""
        self._present = True

    def reset_sensor(self) -> None:
        self._present = False
        self._polls = 0


def auto_answer(
    answer: str = "ok", *, record: list[str] | None = None
) -> Callable[[str], Awaitable[str]]:
    """Build an async `Prompter` that records prompts and returns a canned answer (no stdin)."""

    async def _prompter(message: str) -> str:
        if record is not None:
            record.append(message)
        return answer

    return _prompter
