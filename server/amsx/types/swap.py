"""Motion results and the parsed material-change plan.

`SwapPlan` is produced by the job parser and consumed by the orchestrator — it is the contract
between "what the sliced file says" and "what the state machine does", which is why it lives in
the kernel rather than in either of them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from amsx.types.filament import FilamentColor

__all__ = ["MoveResult", "PlannedSwap", "SwapPlan"]


@dataclass(frozen=True)
class MoveResult:
    """Result of a bounded module move (feed/retract)."""

    ok: bool
    reason: str | None = None
    moved_mm: float | None = None


@dataclass(frozen=True)
class PlannedSwap:
    """One material change parsed from the job. `seq` matches the k-th M400 U1 pause.

    `filament_index` comes from the governing `M1020 S<n>`. `tag` lets the orchestrator
    validate a live pause against the plan (docs/09-filament-change-protocol.md).
    """

    seq: int
    filament_index: int
    tag: str
    layer: int | None = None
    line: int | None = None  # gcode line of this swap's M400 U1 (the #17 ordinal+line guard)
    material: str | None = None
    color_hex: str | None = None


@dataclass(frozen=True)
class SwapPlan:
    """Ordered material-change plan produced by JobParser; consumed by the Orchestrator."""

    swaps: list[PlannedSwap] = field(default_factory=list)
    base: FilamentColor | None = None
    colors: list[FilamentColor] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.swaps)
