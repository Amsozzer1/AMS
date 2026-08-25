"""enums — every closed set of states in the system, and nothing else.

All of these are ``StrEnum``: they compare equal to their own string value, which keeps them
JSON-serialisable and readable in logs without a ``.value`` at every use site.

Design source: docs/10-domain-model.md and docs/06-module-interface.md. Keep dependency-free.
"""

from amsx.enums.module import ModuleState
from amsx.enums.printer import PauseReason, PrinterStage
from amsx.enums.swap import SwapState

__all__ = ["ModuleState", "PauseReason", "PrinterStage", "SwapState"]
