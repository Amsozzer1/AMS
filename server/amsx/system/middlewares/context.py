"""The running Brain, as a dependency any route can ask for by name.

FastAPI's ``Depends`` is the equivalent of an Express middleware that hangs a service off
``req``, with two differences: it is declared in the handler's signature rather than in the
route chain, and it is typed, so the handler says exactly what it needs::

    async def health(brain: BrainDep) -> Health: ...

Before this existed, every route was a closure over a ``_brain()`` local inside ``create_app``,
which is what physically kept all 20 handlers in one 445-line file — a closure cannot be moved
to another module. ``BrainDep`` is what let them split.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from amsx.system.brain import Brain

__all__ = ["BrainDep", "get_brain"]


def get_brain(request: Request) -> Brain:
    """The running Brain, stashed on app.state by the lifespan."""
    return request.app.state.brain


BrainDep = Annotated[Brain, Depends(get_brain)]
