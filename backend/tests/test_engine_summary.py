"""Tests of the summary engine, with the LLM replaced."""

import pytest

from app.engine import prompts, summary as summary_engine
from app.engine.llm import LLMError
from app.engine.summary import make_summary

FULL_ANSWER = {
    "chief_complaint": "Headaches for two weeks.",
    "onset_duration": "They started two weeks ago and last four hours.",
    "location_character": "Right side, throbbing.",
    "severity": "7 of 10.",
    "triggers": "Bright light and a late night.",
    "associated_symptoms": "Nausea. No red flag was reported.",
    "prior_treatments": "Ibuprofen, with a small effect.",
    "notes": "The patient missed two days of work.",
}

LOG = [
    {"role": "bot", "text": "What brings you in today?"},
    {"role": "patient", "text": "I get headaches."},
]


def _fake_model(answer: dict, seen: list | None = None):
    def fake(system, messages, schema, schema_name):
        if seen is not None:
            seen.append({"system": system, "schema": schema, "name": schema_name})
        return answer

    return fake


def test_the_summary_has_the_eight_fields_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(summary_engine, "ask_model", _fake_model(FULL_ANSWER))

    result = make_summary(LOG)

    assert tuple(result) == prompts.SUMMARY_FIELDS
    assert result == FULL_ANSWER


def test_the_summary_uses_its_own_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list = []
    monkeypatch.setattr(summary_engine, "ask_model", _fake_model(FULL_ANSWER, seen))

    make_summary(LOG)

    assert seen[0]["system"] == prompts.SUMMARY_SYSTEM
    assert seen[0]["schema"] == prompts.SUMMARY_SCHEMA
    assert seen[0]["name"] == "intake_summary"


@pytest.mark.parametrize("value", [None, "", "   "])
def test_a_field_with_no_answer_says_not_discussed(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    answer = {**FULL_ANSWER, "triggers": value}
    monkeypatch.setattr(summary_engine, "ask_model", _fake_model(answer))

    assert make_summary(LOG)["triggers"] == prompts.NOT_DISCUSSED


def test_a_field_that_is_absent_says_not_discussed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answer = {k: v for k, v in FULL_ANSWER.items() if k != "prior_treatments"}
    monkeypatch.setattr(summary_engine, "ask_model", _fake_model(answer))

    result = make_summary(LOG)

    assert result["prior_treatments"] == prompts.NOT_DISCUSSED
    assert len(result) == 8


def test_a_key_that_is_not_a_field_is_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    # The frontend shows the eight fields. A diagnosis is out of scope.
    answer = {**FULL_ANSWER, "diagnosis": "migraine"}
    monkeypatch.setattr(summary_engine, "ask_model", _fake_model(answer))

    assert "diagnosis" not in make_summary(LOG)


def test_an_empty_log_still_gives_the_eight_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(summary_engine, "ask_model", _fake_model({}))

    result = make_summary([])

    assert tuple(result) == prompts.SUMMARY_FIELDS
    assert set(result.values()) == {prompts.NOT_DISCUSSED}


def test_a_model_failure_goes_up(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args, **kwargs):
        raise LLMError("openai request failed")

    monkeypatch.setattr(summary_engine, "ask_model", fail)

    with pytest.raises(LLMError):
        make_summary(LOG)
