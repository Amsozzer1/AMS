"""Wire shapes that belong to no single app: liveness and the generic acks."""

from __future__ import annotations

from pydantic import BaseModel

__all__ = ["DeleteResult", "Health", "OkResponse"]


class Health(BaseModel):
    """GET /health."""

    ok: bool
    simulate: bool
    printers: list[str]
    modules: int


class OkResponse(BaseModel):
    """Bare success ack (PUT /loadout, POST /job/assignment)."""

    ok: bool = True


class DeleteResult(BaseModel):
    """DELETE /api/spools/{spool_id}."""

    ok: bool = True
    id: str
