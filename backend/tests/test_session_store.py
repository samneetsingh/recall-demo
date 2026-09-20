"""The tests of the read and write helpers."""

from app.db import session_store

MEETING_URL = "https://meet.google.com/abc-defg-hij"


def test_create_session_has_the_default_values() -> None:
    session = session_store.create_session(MEETING_URL)

    assert session.meeting_url == MEETING_URL
    assert session.mode == "chat"
    assert session.status == "creating_bot"
    assert session.transcript == []
    assert session.summary is None
    assert session.bot_id is None
    assert session.created_at == session.updated_at


def test_create_session_keeps_the_voice_mode() -> None:
    session = session_store.create_session(MEETING_URL, mode="voice")

    assert session.mode == "voice"


def test_get_session_gives_the_same_session() -> None:
    made = session_store.create_session(MEETING_URL)

    read = session_store.get_session(made.id)

    assert read == made


def test_get_session_gives_none_for_an_unknown_id() -> None:
    assert session_store.get_session("no-such-id") is None


def test_set_status_writes_the_status_and_the_reason() -> None:
    session = session_store.create_session(MEETING_URL)

    changed = session_store.set_status(session.id, "error", "the bot cannot join")

    assert changed is not None
    assert changed.status == "error"
    assert changed.error_reason == "the bot cannot join"


def test_set_status_without_a_reason_makes_the_reason_empty() -> None:
    session = session_store.create_session(MEETING_URL)
    session_store.set_status(session.id, "error", "the bot cannot join")

    changed = session_store.set_status(session.id, "in_progress")

    assert changed is not None
    assert changed.status == "in_progress"
    assert changed.error_reason is None


def test_set_summary_writes_the_fields() -> None:
    session = session_store.create_session(MEETING_URL)

    changed = session_store.set_summary(session.id, {"chief_complaint": "headache"})

    assert changed is not None
    assert changed.summary == {"chief_complaint": "headache"}


def test_append_turn_keeps_the_sequence() -> None:
    session = session_store.create_session(MEETING_URL)

    session_store.append_turn(session.id, "bot", "What is the problem?")
    changed = session_store.append_turn(session.id, "patient", "I have a headache.")

    assert changed is not None
    assert changed.transcript == [
        {"role": "bot", "text": "What is the problem?"},
        {"role": "patient", "text": "I have a headache."},
    ]


def test_a_write_to_an_unknown_id_gives_none() -> None:
    assert session_store.set_status("no-such-id", "complete") is None
    assert session_store.set_summary("no-such-id", {}) is None
    assert session_store.append_turn("no-such-id", "bot", "hello") is None
