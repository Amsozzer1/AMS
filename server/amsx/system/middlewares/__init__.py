"""middlewares — the per-request dependencies every route can ask for by name.

``context`` supplies the Brain itself; ``guards`` supplies the preconditions (simulate-only,
printer exists, job armed). Both are FastAPI ``Depends`` providers rather than ASGI middleware:
they run per route, compose, and are visible in the handler's signature.
"""

from amsx.system.middlewares.context import BrainDep, get_brain
from amsx.system.middlewares.guards import (
    SimOnlyDep,
    armed_orchestrator,
    require_printer,
    require_sim,
)

__all__ = [
    "BrainDep",
    "SimOnlyDep",
    "armed_orchestrator",
    "get_brain",
    "require_printer",
    "require_sim",
]
