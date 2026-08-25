"""infra.http — the FastAPI app: middleware, lifespan, error handling, router mounting.

This is the composition of the HTTP surface and nothing else. The handlers live in
``amsx.routes``, the shapes they return live in each app's ``view.py``, and the dependencies
they ask for live in ``amsx.system.middlewares``. Nothing is defined here that a route needs.

Sits at the *top* of the layer stack even though its siblings (``infra.mqtt``, ``infra.ftps``)
sit near the bottom: adapters are grouped by protocol, not by altitude.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from amsx.errors import HTTPError
from amsx.routes import ALL
from amsx.routes import sim as sim_routes
from amsx.system.brain import Brain, build_brain

log = logging.getLogger("amsx.system.infra.http")

__all__ = ["create_app"]

# Local-first dev: the SPA is served from a different port, so allow the dev origins.
# Override with AMSX_CORS_ORIGINS (comma-separated) when serving from elsewhere.
_DEFAULT_CORS = "http://localhost:3000,http://127.0.0.1:3000"


def create_app(brain: Brain | None = None, *, simulate: bool = True) -> FastAPI:
    """Build the app. Pass a pre-built `brain` (e.g. in tests); otherwise one is constructed
    from the resolved config on startup.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        b = brain or build_brain(simulate=simulate)
        await b.start()
        app.state.brain = b
        try:
            yield
        finally:
            await b.stop()

    app = FastAPI(title="AMS-X Brain", version="0.0.0", lifespan=lifespan)

    raw_origins = os.getenv("AMSX_CORS_ORIGINS", _DEFAULT_CORS)
    origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(HTTPError)
    async def _http_error(_request: Request, exc: HTTPError) -> JSONResponse:
        """Render our own errors in FastAPI's shape, so clients see no difference.

        Routes raise ``NotFoundError(...)`` instead of ``HTTPException(status_code=404, ...)``:
        the status code travels with the error type rather than being retyped at every call
        site, and the domain stays free of FastAPI imports.
        """
        body: dict[str, object] = {"detail": exc.detail}
        if exc.expose:
            body |= exc.expose
        return JSONResponse(status_code=exc.status_code, content=body)

    for router in ALL:
        app.include_router(router)

    # Simulate-only injectors are not merely guarded, they are not mounted at all when a real
    # printer is in play — a real deployment has no route that can fake a pause.
    is_sim = brain.simulate if brain is not None else simulate
    if is_sim:
        app.include_router(sim_routes.router)

    return app
