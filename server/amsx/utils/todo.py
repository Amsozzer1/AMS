"""The ``@todo`` decorator — RULE 2's marker for a not-yet-implemented callable."""

from __future__ import annotations

import functools
import inspect
import logging
from collections.abc import Callable
from typing import TypeVar

log = logging.getLogger("amsx.utils")

F = TypeVar("F", bound=Callable[..., object])


def todo(arg: F | str | None = None) -> F | Callable[[F], F]:
    """Mark a callable as not-yet-implemented.

    Project rule: every unfinished stub is decorated with ``@todo`` (optionally ``@todo("why")``)
    instead of a hand-written ``raise NotImplementedError``. Calling a ``@todo`` callable logs a
    warning and raises ``NotImplementedError`` naming it, so unfinished work fails *loudly* and is
    greppable in one place. The wrapper sets ``__todo__ = True`` for introspection/tests. Works on
    both sync and async callables.

    Usage::

        @todo
        def request_unload(self) -> Report: ...

        @todo("A1 feed path differs; build after X1/P1 is proven (docs/10 #10/#11)")
        def request_extrude(self) -> Report: ...
    """

    def decorate(func: F, note: str) -> F:
        msg = f"{func.__qualname__} is not implemented yet (@todo)"
        if note:
            msg = f"{msg}: {note}"

        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def awrapper(*args: object, **kwargs: object) -> object:
                log.warning(msg)
                raise NotImplementedError(msg)

            wrapper: Callable[..., object] = awrapper
        else:

            @functools.wraps(func)
            def swrapper(*args: object, **kwargs: object) -> object:
                log.warning(msg)
                raise NotImplementedError(msg)

            wrapper = swrapper

        wrapper.__todo__ = True  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    # Bare ``@todo`` -> arg is the decorated function. ``@todo("note")`` -> arg is the note.
    if callable(arg):
        return decorate(arg, "")
    return lambda func: decorate(func, arg or "")
