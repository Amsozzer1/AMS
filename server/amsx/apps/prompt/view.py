"""prompt — the wire shapes for the human-swap prompt loop."""

from __future__ import annotations

from pydantic import BaseModel

__all__ = ["AnswerResult", "Prompt"]


class Prompt(BaseModel):
    """One pending human-swap action the orchestrator is blocked on."""

    id: str
    module_id: str
    message: str


class AnswerResult(BaseModel):
    """POST /api/prompts/{prompt_id}/answer."""

    ok: bool = True
    prompt_id: str
