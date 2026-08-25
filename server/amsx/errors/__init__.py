"""errors — every exception the system raises on purpose, in one place.

Two families: **domain** errors from the swap path and parsers, and **HTTP** errors that carry
their own status code. Both descend from ``AmsxError``.

Keep dependency-free (stdlib only) — this sits in the kernel and everything may import it.
"""

from amsx.errors.base import AmsxError
from amsx.errors.domain import (
    ClusterBusyError,
    JobParseError,
    PauseValidationError,
    SwapFault,
)
from amsx.errors.http import (
    BadRequestError,
    ConflictError,
    HTTPError,
    NotFoundError,
    UnprocessableError,
)

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
