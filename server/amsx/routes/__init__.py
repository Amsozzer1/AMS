"""routes — one module per resource, each exposing an APIRouter.

Mounted by ``amsx.system.infra.http``. `sim` is deliberately NOT in ``ALL`` — it is mounted
only in simulate mode, so a real deployment never exposes the pause/sensor injectors.
"""

from amsx.routes import health, jobs, loadout, modules, orchestrator, printers, prompts, spools

#: Routers mounted in every mode, in the order they appear in /docs.
ALL = [
    health.router,
    printers.router,
    jobs.router,
    prompts.router,
    orchestrator.router,
    modules.router,
    spools.router,
    loadout.router,
]

__all__ = ["ALL"]
