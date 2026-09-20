"""The standalone proof of the engine.

A scripted patient answers a scripted model through a fake mode. No Recall, no
webhook and no network. This is the test that section 3 of docs/TASKS.md asks
for.
"""

import pytest

from app.config import settings
from app.db import session_store
from app.engine import intake, loop, prompts, summary as summary_engine
from app.engine.llm import LLMError
from app.modes.base import MODES, ModeError

MEETING_URL = "https://meet.google.com/abc-defg-hij"

SUMMARY_ANSWER = {field: f"the {field}" for field in prompts.SUMMARY_FIELDS}


class FakeMode:
    """A mode that keeps the outgoing text instead of a meeting."""

    def __init__(self, fail: bool = False) -> None:
        self.sent: list[str] = []
        self.fail = fail

    def handle_incoming_turn(self, session_id: str, raw_event: object) -> str | None:
        return str(raw_event) or None

    def send_outgoing_turn(self, session_id: str, text: str) -> None:
        if self.fail:
            raise ModeError("the meeting refused the message")
        self.sent.append(text)


@pytest.fixture
def mode(monkeypatch: pytest.MonkeyPatch) -> FakeMode:
    """Put a fake mode in the registry, which is empty until section 5."""
    fake = FakeMode()
    monkeypatch.setitem(MODES, "chat", fake)
    return fake


def _script(monkeypatch: pytest.MonkeyPatch, *, stop_after: int | None = None) -> None:
    """Make the model ask a question each turn, and give a summary at the end."""
    asked = {"count": 0}

    def fake_intake(system, messages, schema, schema_name):
        asked["count"] += 1
        if stop_after is not None and asked["count"] > stop_after:
            return {"action": "complete", "turn": asked["count"], "question": "", "notes": ""}
        return {
            "action": "ask",
            "turn": asked["count"],
            "question": f"question {asked['count']}",
            "notes": "",
        }

    def fake_summary(system, messages, schema, schema_name):
        return SUMMARY_ANSWER

    monkeypatch.setattr(intake, "ask_model", fake_intake)
    monkeypatch.setattr(summary_engine, "ask_model", fake_summary)


def _new_session() -> str:
    session = session_store.create_session(MEETING_URL)
    session_store.set_status(session.id, "in_progress")
    return session.id


def test_a_full_intake_runs_from_the_first_question_to_the_summary(
    monkeypatch: pytest.MonkeyPatch, mode: FakeMode
) -> None:
    _script(monkeypatch)
    session_id = _new_session()

    loop.start_intake(session_id)
    for turn in range(settings.INTAKE_MAX_TURNS):
        loop.run_turn(session_id, f"answer {turn}")

    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "complete"
    assert session.summary == SUMMARY_ANSWER
    assert len(mode.sent) == settings.INTAKE_MAX_TURNS
    assert mode.sent[0] == "question 1"

    # The log holds one question and one answer for each turn, in order.
    log = session_store.get_turns(session_id)
    assert len(log) == settings.INTAKE_MAX_TURNS * 2
    assert [turn["role"] for turn in log[:4]] == ["bot", "patient", "bot", "patient"]
    assert intake.turn_count(log) == settings.INTAKE_MAX_TURNS


def test_the_model_can_end_the_intake_early(
    monkeypatch: pytest.MonkeyPatch, mode: FakeMode
) -> None:
    _script(monkeypatch, stop_after=2)
    session_id = _new_session()

    loop.start_intake(session_id)
    loop.run_turn(session_id, "a headache")
    loop.run_turn(session_id, "two weeks")

    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "complete"
    assert len(mode.sent) == 2


def test_the_summary_is_written_before_the_status(
    monkeypatch: pytest.MonkeyPatch, mode: FakeMode
) -> None:
    # The frontend reads the status and then asks for the summary, so a
    # complete session must never be without one.
    _script(monkeypatch, stop_after=1)
    session_id = _new_session()
    seen: dict[str, object] = {}
    real_set_status = session_store.set_status

    def watch(session_id_arg, status, error_reason=None):
        if status == "complete":
            current = session_store.get_session(session_id_arg)
            seen["summary_first"] = current is not None and current.summary is not None
        return real_set_status(session_id_arg, status, error_reason)

    monkeypatch.setattr(session_store, "set_status", watch)

    loop.start_intake(session_id)
    loop.run_turn(session_id, "a headache")

    assert seen["summary_first"] is True


def test_a_model_failure_puts_the_session_in_error(
    monkeypatch: pytest.MonkeyPatch, mode: FakeMode
) -> None:
    def fail(*args, **kwargs):
        raise LLMError("openai request failed: timeout")

    monkeypatch.setattr(intake, "ask_model", fail)
    session_id = _new_session()

    loop.start_intake(session_id)

    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "error"
    assert session.error_reason == "openai request failed: timeout"
    assert mode.sent == []


def test_a_mode_with_no_implementation_puts_the_session_in_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Section 5 put chat in the registry and section 6 put voice in it. The
    # entry goes out here, because the rule is about a mode that is absent.
    _script(monkeypatch)
    monkeypatch.delitem(MODES, "voice")
    session = session_store.create_session(MEETING_URL, "voice")
    session_store.set_status(session.id, "in_progress")

    loop.start_intake(session.id)

    after = session_store.get_session(session.id)
    assert after is not None
    assert after.status == "error"
    assert "no implementation" in (after.error_reason or "")


def test_a_question_that_was_not_sent_is_not_in_the_log(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    _script(monkeypatch)
    monkeypatch.setitem(MODES, "chat", FakeMode(fail=True))
    session_id = _new_session()

    loop.start_intake(session_id)

    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "error"
    assert session_store.get_turns(session_id) == []


def test_a_turn_after_the_intake_is_complete_changes_nothing(
    monkeypatch: pytest.MonkeyPatch, mode: FakeMode
) -> None:
    _script(monkeypatch, stop_after=1)
    session_id = _new_session()
    loop.start_intake(session_id)
    loop.run_turn(session_id, "a headache")
    before = session_store.get_turns(session_id)

    loop.run_turn(session_id, "one more message")

    after = session_store.get_session(session_id)
    assert after is not None
    assert session_store.get_turns(session_id) == before
    assert after.status == "complete"


def test_the_intake_starts_one_time(
    monkeypatch: pytest.MonkeyPatch, mode: FakeMode
) -> None:
    # Recall delivers an event more than one time.
    _script(monkeypatch)
    session_id = _new_session()

    loop.start_intake(session_id)
    loop.start_intake(session_id)

    assert len(mode.sent) == 1


def test_a_session_that_is_not_in_progress_asks_nothing(
    monkeypatch: pytest.MonkeyPatch, mode: FakeMode
) -> None:
    _script(monkeypatch)
    session = session_store.create_session(MEETING_URL)

    loop.start_intake(session.id)
    loop.run_turn(session.id, "hello")

    assert mode.sent == []
    assert (session_store.get_session(session.id) or session).status == "creating_bot"


def test_an_empty_patient_turn_changes_nothing(
    monkeypatch: pytest.MonkeyPatch, mode: FakeMode
) -> None:
    _script(monkeypatch)
    session_id = _new_session()
    loop.start_intake(session_id)

    loop.run_turn(session_id, "   ")

    assert len(session_store.get_turns(session_id)) == 1
    assert len(mode.sent) == 1


def test_an_unknown_session_is_not_a_failure(
    monkeypatch: pytest.MonkeyPatch, mode: FakeMode
) -> None:
    _script(monkeypatch)

    loop.start_intake("no-such-session")
    loop.run_turn("no-such-session", "hello")

    assert mode.sent == []


def test_a_repeated_event_asks_no_second_question(
    monkeypatch: pytest.MonkeyPatch, mode: FakeMode
) -> None:
    """Svix delivers at least one time. The second delivery must change nothing."""
    _script(monkeypatch)
    session_id = _new_session()
    loop.start_intake(session_id)

    loop.run_turn(session_id, "a headache", event_id="msg_1")
    loop.run_turn(session_id, "a headache", event_id="msg_1")

    # One greeting, one patient turn, one question. Not two.
    assert len(session_store.get_turns(session_id)) == 3
    assert len(mode.sent) == 2


def test_a_second_message_before_the_answer_is_refused(
    monkeypatch: pytest.MonkeyPatch, mode: FakeMode
) -> None:
    """Half-duplex. One full message in, one question out, then the next.

    The store refuses the second message, so the log always alternates and
    `turn_count` is exact.
    """
    _script(monkeypatch)
    session_id = _new_session()
    loop.start_intake(session_id)

    # Both arrive before the assistant has answered the first.
    real_append = session_store.append_turn

    def append_then_another(session_id_arg, role, text, event_id=None):
        turn_id = real_append(session_id_arg, role, text, event_id)
        if role == "patient":
            assert real_append(session_id_arg, "patient", "the second message") is None
        return turn_id

    monkeypatch.setattr(session_store, "append_turn", append_then_another)
    loop.run_turn(session_id, "the first message", event_id="msg_1")

    log = session_store.get_turns(session_id)
    assert [turn["text"] for turn in log] == [
        "question 1",
        "the first message",
        "question 2",
    ]
    assert [turn["role"] for turn in log] == ["bot", "patient", "bot"]
    assert intake.turn_count(log) == 1


def test_the_log_alternates_for_a_full_intake(
    monkeypatch: pytest.MonkeyPatch, mode: FakeMode
) -> None:
    """`turn_count` is len // 2, so the log must never have two in a row."""
    _script(monkeypatch)
    session_id = _new_session()

    loop.start_intake(session_id)
    for turn in range(settings.INTAKE_MAX_TURNS):
        loop.run_turn(session_id, f"answer {turn}", event_id=f"msg_{turn}")

    roles = [turn["role"] for turn in session_store.get_turns(session_id)]
    assert roles == ["bot", "patient"] * settings.INTAKE_MAX_TURNS
