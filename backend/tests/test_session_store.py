"""The tests of the read and write helpers."""

import threading

from app.db import session_store

MEETING_URL = "https://meet.google.com/abc-defg-hij"


def test_create_session_has_the_default_values() -> None:
    session = session_store.create_session(MEETING_URL)

    assert session.meeting_url == MEETING_URL
    assert session.mode == "chat"
    assert session.status == "creating_bot"
    assert session_store.get_turns(session.id) == []
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

    first = session_store.append_turn(session.id, "bot", "What is the problem?")
    second = session_store.append_turn(session.id, "patient", "I have a headache.")

    assert first is not None and second is not None
    assert second > first
    assert session_store.get_turns(session.id) == [
        {"role": "bot", "text": "What is the problem?"},
        {"role": "patient", "text": "I have a headache."},
    ]


def test_a_write_to_an_unknown_id_gives_none() -> None:
    assert session_store.set_status("no-such-id", "complete") is None
    assert session_store.set_summary("no-such-id", {}) is None
    assert session_store.append_turn("no-such-id", "bot", "hello") is None


def test_set_bot_id_writes_the_column() -> None:
    session = session_store.create_session(MEETING_URL)

    updated = session_store.set_bot_id(session.id, "bot-77")

    assert updated is not None
    assert updated.bot_id == "bot-77"


def test_get_session_by_bot_id_finds_the_row() -> None:
    session = session_store.create_session(MEETING_URL)
    session_store.set_bot_id(session.id, "bot-88")

    found = session_store.get_session_by_bot_id("bot-88")

    assert found is not None
    assert found.id == session.id


def test_get_session_by_bot_id_gives_none_for_an_unknown_bot() -> None:
    assert session_store.get_session_by_bot_id("bot-not-here") is None


def test_a_new_session_has_no_bot_id() -> None:
    session = session_store.create_session(MEETING_URL)

    assert session.bot_id is None


def test_a_repeated_event_makes_one_turn() -> None:
    """Svix delivers at least one time, so a repeat is normal."""
    session = session_store.create_session(MEETING_URL)

    first = session_store.append_turn(session.id, "patient", "hello", "msg_1")
    again = session_store.append_turn(session.id, "patient", "hello", "msg_1")

    assert first is not None
    assert again is None
    assert session_store.get_turns(session.id) == [{"role": "patient", "text": "hello"}]


def test_two_events_make_two_turns() -> None:
    session = session_store.create_session(MEETING_URL)

    session_store.append_turn(session.id, "patient", "one", "msg_1")
    session_store.append_turn(session.id, "bot", "a question")
    session_store.append_turn(session.id, "patient", "two", "msg_2")

    assert len(session_store.get_turns(session.id)) == 3


def test_the_same_event_id_in_another_session_is_not_a_repeat() -> None:
    one = session_store.create_session(MEETING_URL)
    two = session_store.create_session(MEETING_URL)

    assert session_store.append_turn(one.id, "patient", "hello", "msg_1") is not None
    assert session_store.append_turn(two.id, "patient", "hello", "msg_1") is not None


def test_many_bot_turns_have_no_event_id() -> None:
    """SQLite makes each NULL different, so the unique index permits them."""
    session = session_store.create_session(MEETING_URL)

    session_store.append_turn(session.id, "bot", "one")
    session_store.append_turn(session.id, "patient", "a", "msg_a")
    session_store.append_turn(session.id, "bot", "two")
    session_store.append_turn(session.id, "patient", "b", "msg_b")
    session_store.append_turn(session.id, "bot", "three")

    assert len(session_store.get_turns(session.id)) == 5


def test_the_log_always_alternates() -> None:
    """Half-duplex. The assistant answers before it takes the next message."""
    session = session_store.create_session(MEETING_URL)

    assert session_store.append_turn(session.id, "bot", "what brings you in?")
    assert session_store.append_turn(session.id, "patient", "headaches", "msg_1")
    # The patient sends a second message before the assistant answered.
    assert session_store.append_turn(session.id, "patient", "for weeks", "msg_2") is None
    assert session_store.append_turn(session.id, "bot", "how long?")
    assert session_store.append_turn(session.id, "patient", "three weeks", "msg_3")

    assert session_store.get_turns(session.id) == [
        {"role": "bot", "text": "what brings you in?"},
        {"role": "patient", "text": "headaches"},
        {"role": "bot", "text": "how long?"},
        {"role": "patient", "text": "three weeks"},
    ]


def test_two_assistant_turns_in_a_row_are_refused() -> None:
    session = session_store.create_session(MEETING_URL)

    assert session_store.append_turn(session.id, "bot", "one question")
    assert session_store.append_turn(session.id, "bot", "another question") is None


def test_a_turn_of_another_session_is_not_in_the_log() -> None:
    one = session_store.create_session(MEETING_URL)
    two = session_store.create_session(MEETING_URL)
    session_store.append_turn(two.id, "bot", "not mine")

    assert session_store.get_turns(one.id) == []


def test_two_appends_at_the_same_time_give_one_turn_and_no_loss() -> None:
    """The fault of task 3 was that a read and then a write lost a turn.

    With the alternation rule, two patient messages at the same time give one
    turn and one refusal. Neither is decided by which thread was faster to
    read, which is what the fault was.
    """
    session = session_store.create_session(MEETING_URL)
    start = threading.Barrier(2)
    ids: list[int | None] = []
    lock = threading.Lock()

    def append(text: str) -> None:
        start.wait(timeout=5)
        turn_id = session_store.append_turn(session.id, "patient", text)
        with lock:
            ids.append(turn_id)

    threads = [
        threading.Thread(target=append, args=("one",)),
        threading.Thread(target=append, args=("two",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    # Exactly one goes in. The other is the second patient message of a
    # half-duplex conversation, and the store refuses it.
    assert sorted(ids, key=lambda value: value is None) [0] is not None
    assert ids.count(None) == 1
    log = session_store.get_turns(session.id)
    assert len(log) == 1
    assert log[0]["text"] in {"one", "two"}


# The voice buffer. One `transcript.data` utterance is one part, and a silence
# ends the turn. See ../app/modes/voice.py.

FAR_FUTURE = "2099-01-01T00:00:00.000000+00:00"
LONG_PAST = "2000-01-01T00:00:00.000000+00:00"


def test_the_first_part_opens_a_buffer() -> None:
    session = session_store.create_session(MEETING_URL, mode="voice")

    buffer_id = session_store.add_voice_part(session.id, "I get")

    assert buffer_id is not None
    assert session_store.open_voice_buffer(session.id) == (buffer_id, "I get")


def test_a_second_part_joins_the_open_buffer() -> None:
    session = session_store.create_session(MEETING_URL, mode="voice")

    first = session_store.add_voice_part(session.id, "I get")
    second = session_store.add_voice_part(session.id, "bad headaches")

    assert first == second
    assert session_store.open_voice_buffer(session.id) == (first, "I get bad headaches")


def test_the_claim_gives_the_words_and_closes_the_buffer() -> None:
    session = session_store.create_session(MEETING_URL, mode="voice")
    buffer_id = session_store.add_voice_part(session.id, "I get bad headaches")

    assert session_store.claim_voice_buffer(session.id, FAR_FUTURE) == (
        buffer_id,
        "I get bad headaches",
    )
    assert session_store.open_voice_buffer(session.id) is None


def test_a_second_claim_gives_nothing() -> None:
    """A wake-up is not cancelled, so two can fire for one buffer."""
    session = session_store.create_session(MEETING_URL, mode="voice")
    session_store.add_voice_part(session.id, "I get bad headaches")
    session_store.claim_voice_buffer(session.id, FAR_FUTURE)

    assert session_store.claim_voice_buffer(session.id, FAR_FUTURE) is None


def test_a_claim_that_is_too_early_keeps_the_buffer() -> None:
    """A part arrived after the wake-up started. The patient still speaks."""
    session = session_store.create_session(MEETING_URL, mode="voice")
    session_store.add_voice_part(session.id, "I get")

    assert session_store.claim_voice_buffer(session.id, LONG_PAST) is None
    assert session_store.open_voice_buffer(session.id) is not None


def test_a_claim_with_no_buffer_gives_nothing() -> None:
    session = session_store.create_session(MEETING_URL, mode="voice")

    assert session_store.claim_voice_buffer(session.id, FAR_FUTURE) is None


def test_a_part_after_a_claim_opens_a_new_buffer() -> None:
    session = session_store.create_session(MEETING_URL, mode="voice")
    first = session_store.add_voice_part(session.id, "I get")
    session_store.claim_voice_buffer(session.id, FAR_FUTURE)

    second = session_store.add_voice_part(session.id, "two weeks")

    assert second != first
    assert session_store.open_voice_buffer(session.id) == (second, "two weeks")


def test_two_sessions_keep_their_own_buffers() -> None:
    one = session_store.create_session(MEETING_URL, mode="voice")
    two = session_store.create_session(MEETING_URL, mode="voice")

    session_store.add_voice_part(one.id, "I get")
    session_store.add_voice_part(two.id, "two weeks")

    assert session_store.open_voice_buffer(one.id) is not None
    assert session_store.open_voice_buffer(one.id)[1] == "I get"
    assert session_store.open_voice_buffer(two.id)[1] == "two weeks"


def test_two_claims_at_the_same_time_give_one_turn() -> None:
    """Two wake-ups must not make two turns of one answer.

    The claim is one UPDATE with its condition in the same statement, which is
    the rule that `apply_bot_event` uses. This test is the reason it is not a
    read and then a write.
    """
    session = session_store.create_session(MEETING_URL, mode="voice")
    session_store.add_voice_part(session.id, "I get bad headaches")
    start = threading.Barrier(2)
    claimed: list[tuple[int, str] | None] = []
    lock = threading.Lock()

    def claim() -> None:
        start.wait(timeout=5)
        result = session_store.claim_voice_buffer(session.id, FAR_FUTURE)
        with lock:
            claimed.append(result)

    threads = [threading.Thread(target=claim) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert len([one for one in claimed if one is not None]) == 1
    assert claimed.count(None) == 1
