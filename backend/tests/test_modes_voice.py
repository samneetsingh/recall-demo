"""Tests of voice mode: the parse, the buffer, the gap and the two sends."""

import pytest

from app.config import settings
from app.db import session_store
from app.modes.base import ModeError
from app.modes.voice import VoiceMode, VoiceTurnGap, utterance_text
from app.recall import client as recall_client
from app.recall.client import RecallError
from app.recall.events import RecallEvent
from app.tts import openai_tts
from app.tts.openai_tts import TTSError
from tests.conftest import chat_payload, transcript_payload

MEETING_URL = "https://meet.google.com/abc-defg-hij"
BOT_ID = "bot-abc"
MP3 = b"fake-mp3-bytes"


@pytest.fixture(autouse=True)
def no_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    """The wake-up fires after the gap. A test must not wait 2.5 seconds.

    A gap of 0 makes each part old enough at once. The test that proves the
    gap itself sets a large value and expects no turn.
    """
    monkeypatch.setattr(settings, "VOICE_TURN_GAP_SECONDS", 0.0)


@pytest.fixture
def mode() -> VoiceMode:
    return VoiceMode()


@pytest.fixture
def session_id() -> str:
    """A voice session that is in the call."""
    session = session_store.create_session(MEETING_URL, "voice")
    session_store.set_bot_id(session.id, BOT_ID)
    session_store.set_status(session.id, "in_progress")
    return session.id


@pytest.fixture
def audio(monkeypatch: pytest.MonkeyPatch) -> dict[str, list]:
    """Fake the TTS call and the Recall send. No test here uses the network."""
    calls: dict[str, list] = {"spoken": [], "played": []}

    def fake_speak(text: str) -> bytes:
        calls["spoken"].append(text)
        return MP3

    def fake_output_audio(bot_id: str, data: bytes) -> None:
        calls["played"].append((bot_id, data))

    monkeypatch.setattr(openai_tts, "speak", fake_speak)
    monkeypatch.setattr(recall_client, "send_output_audio", fake_output_audio)
    return calls


def _event(payload: dict, name: str = "transcript.data") -> RecallEvent:
    return RecallEvent(
        name=name,
        bot_id=BOT_ID,
        sub_code=None,
        event_at=None,
        message_id="msg_test_00000001",
        payload=payload,
    )


def _gap(session_id: str) -> VoiceTurnGap:
    return VoiceTurnGap(session_id=session_id)


# The parse


def test_the_words_join_into_one_line() -> None:
    """The payload has no sentence field. `data.data.words` is a list."""
    payload = transcript_payload("I get bad headaches")

    assert utterance_text(payload) == "I get bad headaches"


def test_a_payload_with_no_words_gives_an_empty_text() -> None:
    assert utterance_text({"event": "transcript.data", "data": {}}) == ""


def test_a_word_that_is_not_an_object_is_skipped() -> None:
    payload = transcript_payload("one two")
    payload["data"]["data"]["words"].append("three")
    payload["data"]["data"]["words"].append({"start_timestamp": {"relative": 1.0}})

    assert utterance_text(payload) == "one two"


# What the mode does with an event


def test_one_utterance_is_not_a_turn(mode: VoiceMode, session_id: str) -> None:
    """A patient answers in parts. One `transcript.data` is one part."""
    result = mode.handle_incoming_turn(session_id, _event(transcript_payload("I get")))

    assert result is None
    assert session_store.open_voice_buffer(session_id) == (1, "I get")


def test_the_parts_of_one_answer_join(mode: VoiceMode, session_id: str) -> None:
    for part in ("I get", "bad headaches", "most mornings"):
        mode.handle_incoming_turn(session_id, _event(transcript_payload(part)))

    open_buffer = session_store.open_voice_buffer(session_id)
    assert open_buffer is not None
    assert open_buffer[1] == "I get bad headaches most mornings"


def test_the_bot_does_not_hear_itself(mode: VoiceMode, session_id: str) -> None:
    """The bot plays its own audio into the meeting, so Recall transcribes it."""
    payload = transcript_payload("Where is the pain?", speaker=settings.RECALL_BOT_NAME)

    assert mode.handle_incoming_turn(session_id, _event(payload)) is None
    assert session_store.open_voice_buffer(session_id) is None


def test_a_chat_message_makes_no_part(mode: VoiceMode, session_id: str) -> None:
    """One session has one mode. Sam selected this."""
    event = _event(chat_payload("I get bad headaches"), "participant_events.chat_message")

    assert mode.handle_incoming_turn(session_id, event) is None
    assert session_store.open_voice_buffer(session_id) is None


def test_an_empty_utterance_makes_no_part(mode: VoiceMode, session_id: str) -> None:
    assert mode.handle_incoming_turn(session_id, _event(transcript_payload(""))) is None
    assert session_store.open_voice_buffer(session_id) is None


@pytest.mark.parametrize("payload", [None, "a string", 7, []])
def test_a_shape_that_is_not_known_gives_none(
    mode: VoiceMode, session_id: str, payload: object
) -> None:
    """Recall adds fields. A handler must not stop on a payload that changed."""
    event = RecallEvent(
        name="transcript.data",
        bot_id=BOT_ID,
        sub_code=None,
        event_at=None,
        message_id="m1",
        payload=payload,  # type: ignore[arg-type]
    )

    assert mode.handle_incoming_turn(session_id, event) is None


# The gap


def test_the_gap_gives_the_whole_answer(mode: VoiceMode, session_id: str) -> None:
    for part in ("I get", "bad headaches", "most mornings"):
        mode.handle_incoming_turn(session_id, _event(transcript_payload(part)))

    gap = _gap(session_id)

    assert mode.handle_incoming_turn(session_id, gap) == "I get bad headaches most mornings"


def test_the_gap_gives_the_buffer_id_as_the_event_id(
    mode: VoiceMode, session_id: str
) -> None:
    """One buffer row is one turn, so the row id is the `event_id`."""
    mode.handle_incoming_turn(session_id, _event(transcript_payload("I get")))
    gap = _gap(session_id)

    mode.handle_incoming_turn(session_id, gap)

    assert gap.event_id == "voice-1"


def test_a_second_gap_gives_nothing(mode: VoiceMode, session_id: str) -> None:
    """A wake-up is not cancelled, so two can fire for one buffer."""
    mode.handle_incoming_turn(session_id, _event(transcript_payload("I get")))
    mode.handle_incoming_turn(session_id, _gap(session_id))

    assert mode.handle_incoming_turn(session_id, _gap(session_id)) is None


def test_a_gap_with_no_buffer_gives_nothing(mode: VoiceMode, session_id: str) -> None:
    assert mode.handle_incoming_turn(session_id, _gap(session_id)) is None


def test_a_gap_that_is_too_early_gives_nothing(
    mode: VoiceMode, session_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The patient is still speaking. The part that arrived armed its own wake-up."""
    monkeypatch.setattr(settings, "VOICE_TURN_GAP_SECONDS", 30.0)
    mode.handle_incoming_turn(session_id, _event(transcript_payload("I get")))

    assert mode.handle_incoming_turn(session_id, _gap(session_id)) is None
    assert session_store.open_voice_buffer(session_id) is not None


def test_the_next_answer_gets_a_new_buffer(mode: VoiceMode, session_id: str) -> None:
    mode.handle_incoming_turn(session_id, _event(transcript_payload("I get")))
    mode.handle_incoming_turn(session_id, _gap(session_id))

    mode.handle_incoming_turn(session_id, _event(transcript_payload("two weeks")))
    second = _gap(session_id)

    assert mode.handle_incoming_turn(session_id, second) == "two weeks"
    assert second.event_id == "voice-2"


# The send


def test_send_outgoing_turn_speaks_and_plays(
    mode: VoiceMode, session_id: str, audio: dict[str, list]
) -> None:
    mode.send_outgoing_turn(session_id, "Where is the pain?")

    assert audio["spoken"] == ["Where is the pain?"]
    assert audio["played"] == [(BOT_ID, MP3)]


def test_send_notice_uses_the_same_path(
    mode: VoiceMode, session_id: str, audio: dict[str, list]
) -> None:
    """The notice is spoken, not pinned. A pin is a chat word."""
    mode.send_notice(session_id, "Hello. I am an AI intake assistant.")

    assert audio["spoken"] == ["Hello. I am an AI intake assistant."]
    assert audio["played"] == [(BOT_ID, MP3)]


def test_a_long_question_goes_out_in_one_clip(
    mode: VoiceMode, session_id: str, audio: dict[str, list]
) -> None:
    """The 500 character limit is a Google Meet chat rule, not an audio rule."""
    question = "Where is the pain? " * 60

    mode.send_outgoing_turn(session_id, question)

    assert len(audio["spoken"]) == 1


def test_a_session_with_no_bot_id_raises_a_mode_error(
    mode: VoiceMode, audio: dict[str, list]
) -> None:
    session = session_store.create_session(MEETING_URL, "voice")

    with pytest.raises(ModeError, match="has no bot id"):
        mode.send_outgoing_turn(session.id, "Where is the pain?")

    assert audio["spoken"] == []


def test_a_session_that_is_gone_raises_a_mode_error(
    mode: VoiceMode, audio: dict[str, list]
) -> None:
    with pytest.raises(ModeError, match="has no bot id"):
        mode.send_outgoing_turn("no-such-session", "Where is the pain?")


@pytest.mark.parametrize("text", ["", "   "])
def test_an_empty_message_raises_a_mode_error(
    mode: VoiceMode, session_id: str, audio: dict[str, list], text: str
) -> None:
    with pytest.raises(ModeError, match="the message is empty"):
        mode.send_outgoing_turn(session_id, text)

    assert audio["spoken"] == []


def test_a_tts_failure_becomes_a_mode_error(
    mode: VoiceMode, session_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`engine/loop.py` catches ModeError. A TTSError would go past it."""

    def fail(text: str) -> bytes:
        raise TTSError("openai tts failed: no key")

    monkeypatch.setattr(openai_tts, "speak", fail)

    with pytest.raises(ModeError, match="openai tts failed"):
        mode.send_outgoing_turn(session_id, "Where is the pain?")


def test_a_recall_failure_becomes_a_mode_error(
    mode: VoiceMode, session_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(openai_tts, "speak", lambda text: MP3)

    def fail(bot_id: str, data: bytes) -> None:
        raise RecallError("recall http 400: cannot_command_unstarted_bot")

    monkeypatch.setattr(recall_client, "send_output_audio", fail)

    with pytest.raises(ModeError, match="recall http 400"):
        mode.send_outgoing_turn(session_id, "Where is the pain?")


def test_the_audio_is_not_made_for_a_session_with_no_bot(
    mode: VoiceMode, audio: dict[str, list]
) -> None:
    """The bot id is read first. A TTS call that nothing can play is waste."""
    session = session_store.create_session(MEETING_URL, "voice")

    with pytest.raises(ModeError):
        mode.send_notice(session.id, "Hello.")

    assert audio["spoken"] == []
