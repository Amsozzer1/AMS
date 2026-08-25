"""HTTP errors — carry a status code and are turned into a response at the edge.

Routes raise these instead of constructing a bare ``fastapi.HTTPException``, so a handler reads
as ``raise NotFoundError(f"unknown printer {pid!r}")``: the status code lives with the error
type rather than being retyped at every call site, and the domain stays free of FastAPI imports.
``amsx.system.infra.http.app`` registers the handler that renders them.
"""

from __future__ import annotations

from amsx.errors.base import AmsxError

__all__ = [
    "BadRequestError",
    "ConflictError",
    "HTTPError",
    "NotFoundError",
    "UnprocessableError",
]


class HTTPError(AmsxError):
    """An error that already knows its HTTP status code.

    ``detail`` is what reaches the client; ``expose`` is optional structured context (field
    issues, ids) attached to the response body when present.
    """

    status_code: int = 500

    def __init__(self, detail: str, *, expose: dict | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.expose = expose


class BadRequestError(HTTPError):
    status_code = 400


class NotFoundError(HTTPError):
    status_code = 404


class ConflictError(HTTPError):
    status_code = 409


class UnprocessableError(HTTPError):
    status_code = 422
