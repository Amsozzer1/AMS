"""`amsx` entrypoint — start the Brain behind the FastAPI app.

    uv run amsx                 # simulate mode (no printer needed) on 127.0.0.1:9001
    AMSX_SIMULATE=0 uv run amsx # real transport (needs a printer + the v0.2 spike confirmed)
    AMSX_RELOAD=1 uv run amsx   # watch amsx/ and hot-reload on every change (dev)

Env: AMSX_HOST, AMSX_PORT, AMSX_CONFIG, AMSX_SIMULATE, AMSX_RELOAD, AMSX_LOG_LEVEL.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from amsx.system.infra.http.app import create_app


def _truthy(name: str, default: str = "0") -> bool:
    return os.getenv(name, default) not in ("0", "false", "False", "")


def setup_logging() -> None:
    """Attach a dedicated handler to the ``amsx`` logger so the whole pipeline is visible.

    Done on the ``amsx`` logger (not root) on purpose: under ``--reload`` the app runs in a
    uvicorn worker subprocess whose root logger only surfaces WARNING+, which would swallow our
    INFO pipeline logs. A dedicated handler with ``propagate=False`` shows them at the chosen
    level in BOTH the plain and reload paths, without double-printing. We also quiet uvicorn's
    per-request access log (the dashboard polls ~1/s) so the pipeline story stays readable —
    set AMSX_LOG_LEVEL=DEBUG for the raw report stream, or AMSX_ACCESS_LOG=1 to see requests.
    """
    level = os.getenv("AMSX_LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s — %(message)s"))
    amsx = logging.getLogger("amsx")
    amsx.handlers.clear()
    amsx.addHandler(handler)
    amsx.setLevel(level)
    amsx.propagate = False
    if not _truthy("AMSX_ACCESS_LOG"):
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def reload_app():
    """Factory uvicorn imports (by string) in reload mode, so the app is rebuilt per reload.

    Reads AMSX_SIMULATE itself because the reloader re-imports this module in a fresh process
    and never sees the kwargs ``main`` would pass. Re-runs logging setup so the worker
    subprocess shows the ``amsx`` pipeline logs.
    """
    setup_logging()
    return create_app(simulate=_truthy("AMSX_SIMULATE", "1"))


def main() -> None:
    import uvicorn

    setup_logging()
    host = os.getenv("AMSX_HOST", "127.0.0.1")
    # 9001, not 8000: 8000 is a heavily contested port (a stray file server, a stray
    # dev server) and every task/script here already standardises on 9001.
    port = int(os.getenv("AMSX_PORT", "9001"))

    if _truthy("AMSX_RELOAD"):
        # Watch the package source and restart on any .py change (dev — keeps the running
        # server in sync with edits). uvicorn needs an import string + factory to own reloads.
        src_dir = str(Path(__file__).resolve().parent)  # .../src/amsx
        uvicorn.run(
            "amsx.system.__main__:reload_app",
            factory=True,
            host=host,
            port=port,
            reload=True,
            reload_dirs=[src_dir],
        )
        return

    app = create_app(simulate=_truthy("AMSX_SIMULATE", "1"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
