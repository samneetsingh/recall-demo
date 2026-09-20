"""The intake engine.

It takes the conversation log and gives the next question, or a signal that the
intake is complete. It takes plain text in and gives plain text out.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import settings
from app.engine import prompts
from app.engine.llm import LLMError, ask_model, to_messages


@dataclass(frozen=True)
class NextTurn:
    """The result of one call to the engine.

    One field holds the state, so a question and a complete signal cannot
    disagree.
    """

    question: str | None

    @property
    def complete(self) -> bool:
        """True when the intake has no more questions."""
        return self.question is None


COMPLETE = NextTurn(question=None)


def turn_count(log: list[dict[str, str]]) -> int:
    """Count the complete turns.

    A turn is one message from each party: a question and its answer. A
    question that has no answer yet is not a turn.
    """
    return len(log) // 2


def next_turn(log: list[dict[str, str]]) -> NextTurn:
    """Give the next question of this conversation, or the complete signal."""
    if turn_count(log) >= settings.INTAKE_MAX_TURNS:
        return COMPLETE

    system = prompts.intake_system(settings.INTAKE_MAX_TURNS)
    answer = ask_model(system, to_messages(log), prompts.INTAKE_SCHEMA, "intake_turn")

    if answer.get("action") == "complete":
        return COMPLETE

    question = str(answer.get("question") or "").strip()
    if not question:
        # An empty question sends nothing to the meeting, which looks like a
        # hang to the patient.
        raise LLMError("the model asked a question that is empty")
    return NextTurn(question=question)
