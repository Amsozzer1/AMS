"""`amsx` entrypoint — start the Brain behind the FastAPI app.

    uv run amsx                 # simulate mode (no printer needed) on 127.0.0.1:8000
    AMSX_SIMULATE=0 uv run amsx # real transport (needs a printer + the v0.2 spike confirmed)

Env: AMSX_HOST, AMSX_PORT, AMSX_CONFIG, AMSX_SIMULATE, AMSX_LOG_LEVEL.
"""

from __future__ import annotations

import logging
import os

from .api import create_app


def main() -> None:
    import uvicorn

    logging.basicConfig(
        level=os.getenv("AMSX_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    simulate = os.getenv("AMSX_SIMULATE", "1") not in ("0", "false", "False")
    host = os.getenv("AMSX_HOST", "127.0.0.1")
    port = int(os.getenv("AMSX_PORT", "8000"))

    app = create_app(simulate=simulate)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
