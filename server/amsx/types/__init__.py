"""types — the kernel every layer depends on: value objects, ids, wire shapes, and seams.

Split out of the old single ``types.py``; the enums that lived alongside these now live in
``amsx.enums``. Everything is re-exported here, so ``from amsx.types import Spool`` keeps
working and callers never need to know which submodule a name lives in.

Keep this package dependency-free apart from ``amsx.enums`` (stdlib otherwise).

Design source: docs/10-domain-model.md and docs/06-module-interface.md.
"""

from __future__ import annotations

from amsx.types.filament import FilamentColor, FilamentRef
from amsx.types.ids import ClusterId, ModuleId, PrinterId
from amsx.types.protocols import (
    FtpClient,
    Module,
    PrinterControl,
    PrinterDriver,
    PrinterLink,
    SpoolStore,
)
from amsx.types.spool import Spool, SpoolSpec
from amsx.types.swap import MoveResult, PlannedSwap, SwapPlan
from amsx.types.wire import Report, ReportHandler

__all__ = [
    "ClusterId",
    "FilamentColor",
    "FilamentRef",
    "FtpClient",
    "Module",
    "ModuleId",
    "MoveResult",
    "PlannedSwap",
    "PrinterControl",
    "PrinterDriver",
    "PrinterId",
    "PrinterLink",
    "Report",
    "ReportHandler",
    "Spool",
    "SpoolSpec",
    "SpoolStore",
    "SwapPlan",
]
