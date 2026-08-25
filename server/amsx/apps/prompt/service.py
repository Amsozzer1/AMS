"""prompt — the human-in-the-loop actuator bridge.

`ManualModule` is the v0 stand-in for module hardware: every motion is a message to a person.
That message has to reach an operator and their answer has to come back, but the module itself
only knows how to `await prompter(message)`.

`PromptBroker` is that bridge. `ask` parks the swap on a future and hands the question to
whoever is listening (the HTTP API); `answer` resolves the future and the swap resumes. This
is the v0 money shot: the server prompts the human, the human swaps the spool, the server
resumes the print.

Lifted out of `brain.py` so the Brain is purely a composition root, and so the prompts routes
have an app to belong to like every other resource.
"""

from __future__ import annotations

import asyncio
import logging

from amsx.types import ModuleId

log = logging.getLogger("amsx.apps.prompt")

__all__ = ["PendingPrompt", "PromptBroker"]


class PendingPrompt:
    """A human action the orchestrator is waiting on (surfaced over HTTP)."""

    def __init__(self, prompt_id: str, module_id: ModuleId, message: str) -> None:
        self.id = prompt_id
        self.module_id = module_id
        self.message = message
        self.future: asyncio.Future[str] = asyncio.get_event_loop().create_future()


class PromptBroker:
    """Bridges `ManualModule`'s async prompter to the API. `ask` blocks the swap until the
    human answers via `answer`. This is the v0 stand-in for module hardware.
    """

    def __init__(self) -> None:
        self._pending: dict[str, PendingPrompt] = {}
        self._counter = 0

    def prompter_for(self, module_id: ModuleId):
        async def _prompter(message: str) -> str:
            return await self.ask(module_id, message)

        return _prompter

    async def ask(self, module_id: ModuleId, message: str) -> str:
        self._counter += 1
        prompt_id = f"p{self._counter}"
        pending = PendingPrompt(prompt_id, module_id, message)
        self._pending[prompt_id] = pending
        log.info("PROMPT %s [module %s]: %s", prompt_id, module_id, message)
        try:
            return await pending.future
        finally:
            self._pending.pop(prompt_id, None)

    def answer(self, prompt_id: str, response: str = "done") -> bool:
        pending = self._pending.get(prompt_id)
        if pending is None:
            return False
        log.info("PROMPT %s answered (module %s): %s", prompt_id, pending.module_id, response)
        if not pending.future.done():
            pending.future.set_result(response)
        return True

    def pending(self) -> list[dict]:
        return [
            {"id": p.id, "module_id": p.module_id, "message": p.message}
            for p in self._pending.values()
        ]
