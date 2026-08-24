#!/usr/bin/env python3
"""Dump the Brain's OpenAPI schema to a file — the source for the frontend's TS types.

Imports the app directly instead of hitting a running server, so codegen is deterministic
and works in CI with no ports and no live process. Never starts the Brain (the lifespan
never runs); it only reads the route signatures.

    uv run python scripts/dump_openapi.py                 # -> server/openapi.json
    uv run python scripts/dump_openapi.py path/to/out.json

Consumed by `npm run gen:api` in frontend/. See CLAUDE.md RULE 1: api/models.py owns the
wire contract, and this is how that contract reaches TypeScript without being retyped.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Importable whether run via `uv run` (installed) or straight from a checkout.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from amsx.api import create_app

DEFAULT_OUT = Path(__file__).resolve().parents[1] / "openapi.json"


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    spec = create_app(simulate=True).openapi()
    out.write_text(json.dumps(spec, indent=2) + "\n")
    schemas = len(spec.get("components", {}).get("schemas", {}))
    routes = sum(len(ops) for ops in spec.get("paths", {}).values())
    print(f"wrote {out} — {routes} operations, {schemas} schemas")


if __name__ == "__main__":
    main()
