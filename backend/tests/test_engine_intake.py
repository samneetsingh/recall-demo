"""Tests of the intake engine, with the LLM replaced.

No test here makes a network call. Each test gives the answers of the model from
a script.
"""

import pytest

from app.config import settings
from app.engine import intake
from app.engine.intake import next_turn
from app.engine.llm import LLMError


def _ask(question: str, turn: int = 1) -> dict:
    return {"action": "ask", "turn": turn, "question": question, "notes": ""}


COMPLETE_ANSWER = {"action": "complete", "turn": 1, "question": "", "notes": "enough"}


def _fake_model(*answers: dict, seen: list | None = None):
    """Give a fake `ask_model` that answers from the script, in order."""
    script = list(answers)

    def fake(system, messages, schema, schema_name):
        if seen is not None:
            seen.append({"system": system, "messages": messages, "name": schema_name})
        return script.pop(0) if script else COMPLETE_ANSWER

    return fake


def _refuse_call(*args, **kwargs):
    raise AssertionError("the engine must not call the model here")


def _log(exchanges: int) -> list[dict[str, str]]:
    """Give a log of complete turns. One turn is a question and its answer."""
    log: list[dict[str, str]] = []
    for index in range(exchanges):
        log.append({"role": "bot", "text": f"question {index}"})
        log.append({"role": "patient", "text": f"answer {index}"})
    return log


def test_an_empty_log_gives_the_first_question(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list = []
    monkeypatch.setattr(
        intake, "ask_model", _fake_model(_ask("What brings you in today?"), seen=seen)
    )

    result = next_turn([])

    assert result.question == "What brings you in today?"
    assert result.complete is False
    assert seen[0]["messages"] == []
    assert seen[0]["name"] == "intake_turn"
    assert f"{settings.INTAKE_MAX_TURNS} questions" in seen[0]["system"]


def test_the_log_goes_to_the_model_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list = []
    monkeypatch.setattr(intake, "ask_model", _fake_model(_ask("Where is it?"), seen=seen))

    next_turn(
        [
            {"role": "bot", "text": "What brings you in?"},
            {"role": "patient", "text": "A headache for two weeks."},
        ]
    )

    assert seen[0]["messages"] == [
        {"role": "assistant", "content": "What brings you in?"},
        {"role": "user", "content": "A headache for two weeks."},
    ]


def test_the_model_can_end_the_intake(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(intake, "ask_model", _fake_model(COMPLETE_ANSWER))

    result = next_turn(_log(2))

    assert result.complete is True
    assert result.question is None


def test_the_engine_ends_the_intake_at_the_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The model is not asked. The engine applies the limit, not the prompt.
    monkeypatch.setattr(intake, "ask_model", _refuse_call)

    result = next_turn(_log(settings.INTAKE_MAX_TURNS))

    assert result.complete is True


def test_one_question_less_than_the_limit_still_asks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(intake, "ask_model", _fake_model(_ask("Last one?")))

    result = next_turn(_log(settings.INTAKE_MAX_TURNS - 1))

    assert result.question == "Last one?"


def test_a_model_that_never_stops_is_stopped_by_the_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The scripted model always asks. A full conversation must still end.
    log: list[dict[str, str]] = []
    questions = 0
    for turn in range(settings.INTAKE_MAX_TURNS + 3):
        monkeypatch.setattr(
            intake, "ask_model", _fake_model(_ask(f"question {turn}", turn + 1))
        )
        result = next_turn(log)
        if result.complete:
            break
        questions += 1
        log.append({"role": "bot", "text": result.question or ""})
        log.append({"role": "patient", "text": f"answer {turn}"})

    assert questions == settings.INTAKE_MAX_TURNS


def test_an_empty_question_is_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(intake, "ask_model", _fake_model(_ask("   ")))

    with pytest.raises(LLMError, match="question that is empty"):
        next_turn([])


def test_an_answer_with_no_action_is_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(intake, "ask_model", _fake_model({"turn": 1}))

    with pytest.raises(LLMError):
        next_turn([])


def test_the_turn_field_of_the_model_is_not_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The model says turn 99. The engine counts the log, so the intake goes on.
    monkeypatch.setattr(intake, "ask_model", _fake_model(_ask("Next?", turn=99)))

    assert next_turn(_log(1)).question == "Next?"


def test_turn_count_counts_a_complete_exchange() -> None:
    """A turn is one message from each party, not one message."""
    assert intake.turn_count([]) == 0
    assert intake.turn_count(_log(3)) == 3
    assert intake.turn_count(_log(3)) * 2 == len(_log(3))

    # A question with no answer yet is not a turn.
    assert intake.turn_count([{"role": "bot", "text": "What brings you in?"}]) == 0
    assert intake.turn_count([*_log(2), {"role": "bot", "text": "one more?"}]) == 2


def test_a_question_keeps_no_extra_space(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(intake, "ask_model", _fake_model(_ask("  Where is it?  ")))

    assert next_turn([]).question == "Where is it?"
