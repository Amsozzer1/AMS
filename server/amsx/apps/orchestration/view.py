"""orchestration — the wire shapes for the armed swap loop's status."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from amsx.apps.orchestration.service import Orchestrator

__all__ = ["OrchestratorArmed", "OrchestratorIdle", "OrchestratorStatus", "OrchestratorSwap"]


class OrchestratorSwap(BaseModel):
    """One swap in the armed plan, flagged when it is the cursor's current target."""

    seq: int
    filament_index: int
    tag: str
    current: bool


class OrchestratorArmed(BaseModel):
    """The live swap loop for a printer with a job armed."""

    armed: Literal[True] = True
    printer_id: str
    cursor: int
    total: int
    done: bool
    held: bool
    swap_state: str
    alerts: list[str]
    swaps: list[OrchestratorSwap]

    @classmethod
    def from_orchestrator(cls, orch: Orchestrator) -> OrchestratorArmed:
        return cls(
            printer_id=orch.printer_id,
            cursor=orch.cursor,
            total=len(orch.plan),
            done=orch.done,
            held=orch.held,
            swap_state=str(orch.sm.state),
            alerts=list(orch.alerts),
            swaps=[
                OrchestratorSwap(
                    seq=sw.seq,
                    filament_index=sw.filament_index,
                    tag=sw.tag,
                    current=i == orch.cursor,
                )
                for i, sw in enumerate(orch.plan.swaps)
            ],
        )


class OrchestratorIdle(BaseModel):
    """No job armed for this printer yet."""

    armed: Literal[False] = False
    printer_id: str


# A plain union, NOT Field(discriminator="armed"). Pydantic renders a discriminator mapping
# with Python's "True"/"False" string keys, which makes openapi-typescript type the tag as the
# *string* "True" instead of the boolean the server actually sends. Left as a bare union, each
# member's `armed: Literal[...]` becomes a JSON-schema const and TypeScript narrows on it
# correctly. Pydantic's smart-union matching picks the right member on its own.
OrchestratorStatus = OrchestratorArmed | OrchestratorIdle
