"""The human-swap prompt loop: what the orchestrator is waiting on, and answering it."""

from __future__ import annotations

from fastapi import APIRouter

from amsx.apps.prompt.view import AnswerResult, Prompt
from amsx.errors import NotFoundError
from amsx.system.middlewares import BrainDep

router = APIRouter(prefix="/api/prompts", tags=["prompts"])


@router.get("")
async def list_prompts(brain: BrainDep) -> list[Prompt]:
    """Pending human-swap actions the orchestrator is waiting on."""
    return [Prompt(**p) for p in brain.prompts.pending()]


@router.post("/{prompt_id}/answer")
async def answer_prompt(brain: BrainDep, prompt_id: str, response: str = "done") -> AnswerResult:
    if not brain.prompts.answer(prompt_id, response):
        raise NotFoundError(f"unknown prompt {prompt_id!r}")
    return AnswerResult(ok=True, prompt_id=prompt_id)
