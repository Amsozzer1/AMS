"""errors — every exception the system raises on purpose, in one place.

Two families:

* **Domain errors** — raised by the swap path and the parsers. These were previously defined
  in whichever module happened to raise them (`orchestration`, `job`, `module`), which made
  "what can go wrong here?" impossible to answer without reading all three.
* **HTTP errors** — carry a status code and are converted to a response at the edge. Routes
  raise these instead of constructing a bare ``fastapi.HTTPException``, so a handler reads as
  ``raise NotFoundError(f"unknown printer {pid!r}")`` and the status code lives with the error
  type rather than being retyped at 22 call sites.

Keep dependency-free (stdlib only) — this sits in the kernel and everything may import it.
"""

from __future__ import annotations

__all__ = [
    "AmsxError",
    "BadRequestError",
    "ClusterBusyError",
    "ConflictError",
    "HTTPError",
    "JobParseError",
    "NotFoundError",
    "PauseValidationError",
    "SwapFault",
    "UnprocessableError",
]


class AmsxError(Exception):
    """Root of every error we raise deliberately. Lets a caller catch ours and nothing else."""


# ---- domain -----------------------------------------------------------------------------


class PauseValidationError(AmsxError):
    """A live pause did not match the plan — never a swap, never a guess (docs/02).

    Carries the offending event so the caller can log/alert with the full context rather than
    just a message.
    """

    def __init__(self, message: str, event: object) -> None:
        super().__init__(message)
        self.event = event


class SwapFault(AmsxError):
    """A swap could not complete. Drives the state machine into FAULT + safe-hold."""


class JobParseError(AmsxError):
    """The sliced 3MF could not be parsed into a SwapPlan."""


class ClusterBusyError(AmsxError, RuntimeError):
    """Another module in this cluster is already moving (one motor at a time, docs/08).

    Also a ``RuntimeError`` so existing ``except RuntimeError`` callers keep working.
    """


# ---- http -------------------------------------------------------------------------------


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
