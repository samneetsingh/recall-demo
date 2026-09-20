"""The tests of chat mode: the parser, the echo filter, the split and the send.

No test here uses the network and no test here uses Recall.
"""

import json
from typing import Any

import httpx
import pytest

from app.config import settings
from app.db import session_store
from app.modes.base import ModeError
from app.modes.chat import CHAT_EVENT, MEET_CHAT_LIMIT, ChatMode, split_message
from app.recall.events import RecallEvent
from tests.conftest import chat_payload, mock_httpx_client

BOT_ID = "bot-abc"
MEETING_URL = "https://meet.google.com/abc-defg-hij"


def _event(
    text: str = "I get bad headaches",
    sender: str | None = "Samneet Singh",
    name: str = CHAT_EVENT,
) -> RecallEvent:
    """Give the verified event that the webhook route gives to the mode."""
    payload = chat_payload(text=text, sender=sender, bot_id=BOT_ID)
    payload["event"] = name
    return RecallEvent(
        name=name,
        bot_id=BOT_ID,
        sub_code=None,
        event_at=None,
        message_id="msg_test_00000001",
        payload=payload,
    )


def _session_with_bot(bot_id: str | None = BOT_ID) -> str:
    session = session_store.create_session(MEETING_URL)
    if bot_id is not None:
        session_store.set_bot_id(session.id, bot_id)
    session_store.set_status(session.id, "in_progress")
    return session.id


# --- handle_incoming_turn -------------------------------------------------


def test_the_true_payload_gives_the_patient_text() -> None:
    assert ChatMode().handle_incoming_turn("s1", _event()) == "I get bad headaches"


def test_the_text_is_stripped() -> None:
    assert ChatMode().handle_incoming_turn("s1", _event("  two weeks  ")) == "two weeks"


def test_a_message_from_the_bot_gives_none() -> None:
    """The bot receives its own messages back. It must not interview itself."""
    event = _event("What brings you in?", sender=settings.RECALL_BOT_NAME)

    assert ChatMode().handle_incoming_turn("s1", event) is None


@pytest.mark.parametrize("sender", ["  headache assistant  ", "HEADACHE ASSISTANT"])
def test_the_bot_name_test_ignores_the_case_and_the_spaces(sender: str) -> None:
    assert ChatMode().handle_incoming_turn("s1", _event(sender=sender)) is None


def test_a_patient_with_another_name_is_a_turn() -> None:
    event = _event("my head hurts", sender="Headache Assistant Patient")

    assert ChatMode().handle_incoming_turn("s1", event) == "my head hurts"


@pytest.mark.parametrize("text", ["", "   ", "\n\t"])
def test_an_empty_text_gives_none(text: str) -> None:
    assert ChatMode().handle_incoming_turn("s1", _event(text)) is None


def test_another_event_name_gives_none() -> None:
    assert ChatMode().handle_incoming_turn("s1", _event(name="transcript.data")) is None


def test_a_participant_with_no_name_is_a_turn() -> None:
    """`name` is `string | null` in the payload. A null name is not the bot."""
    assert ChatMode().handle_incoming_turn("s1", _event(sender=None)) == "I get bad headaches"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"data": None},
        {"data": {"data": {}}},
        {"data": {"data": {"data": {}}}},
        {"data": {"data": {"data": {"text": 42}}}},
        {"data": {"data": "a string where an object must be"}},
    ],
)
def test_a_payload_that_is_not_the_shape_gives_none(payload: dict[str, Any]) -> None:
    """Recall changes a shape without a notice. A webhook handler must not stop."""
    event = RecallEvent(
        name=CHAT_EVENT,
        bot_id=BOT_ID,
        sub_code=None,
        event_at=None,
        message_id="msg_1",
        payload=payload,
    )

    assert ChatMode().handle_incoming_turn("s1", event) is None


def test_a_raw_event_that_is_not_an_event_gives_none() -> None:
    assert ChatMode().handle_incoming_turn("s1", "a string") is None


# --- split_message --------------------------------------------------------


def test_a_short_question_is_one_part() -> None:
    assert split_message("Where is the pain?") == ["Where is the pain?"]


def test_an_empty_text_gives_no_part() -> None:
    assert split_message("   ") == []


def test_a_long_text_is_cut_at_the_end_of_a_sentence() -> None:
    first = "A. " * 100  # 300 characters, the last sentence end is at 300.
    parts = split_message(first + "B" * 400)

    assert len(parts) == 2
    assert parts[0].endswith("A.")
    assert parts[1] == "B" * 400
    assert all(len(part) <= MEET_CHAT_LIMIT for part in parts)


def test_a_long_text_with_no_sentence_end_is_cut_at_a_space() -> None:
    parts = split_message(" ".join(["word"] * 200))

    assert len(parts) == 2
    assert all(len(part) <= MEET_CHAT_LIMIT for part in parts)
    # No word is cut in two.
    assert " ".join(parts).split() == ["word"] * 200


def test_a_long_text_with_no_space_is_cut_at_the_limit() -> None:
    parts = split_message("x" * 1200)

    assert [len(part) for part in parts] == [500, 500, 200]


def test_the_limit_is_a_parameter() -> None:
    assert split_message("one two three", limit=9) == ["one two", "three"]


# --- send_outgoing_turn ---------------------------------------------------


def test_the_message_goes_to_the_send_chat_message_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.read())
        return httpx.Response(200, json={"id": BOT_ID})

    monkeypatch.setattr(httpx, "Client", mock_httpx_client(handler))
    session_id = _session_with_bot()

    ChatMode().send_outgoing_turn(session_id, "Where is the pain?")

    assert seen["url"] == f"https://us-west-2.recall.ai/api/v1/bot/{BOT_ID}/send_chat_message/"
    assert seen["auth"] == "Token test-recall-api-key"
    # Google Meet takes the recipient `everyone` only.
    assert seen["body"] == {"to": "everyone", "message": "Where is the pain?"}


def test_a_long_question_goes_out_in_two_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.read())["message"])
        return httpx.Response(200, json={"id": BOT_ID})

    monkeypatch.setattr(httpx, "Client", mock_httpx_client(handler))
    session_id = _session_with_bot()

    ChatMode().send_outgoing_turn(session_id, "A. " * 100 + "B" * 400)

    assert len(sent) == 2
    assert sent[0].endswith("A.")
    assert sent[1] == "B" * 400


def test_a_session_with_no_bot_id_raises_mode_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("the mode sent a message with no bot id")

    monkeypatch.setattr(httpx, "Client", mock_httpx_client(handler))
    session_id = _session_with_bot(bot_id=None)

    with pytest.raises(ModeError, match="no bot id"):
        ChatMode().send_outgoing_turn(session_id, "Where is the pain?")


def test_an_unknown_session_raises_mode_error() -> None:
    with pytest.raises(ModeError, match="no bot id"):
        ChatMode().send_outgoing_turn("no-such-session", "Where is the pain?")


def test_an_empty_message_raises_mode_error() -> None:
    session_id = _session_with_bot()

    with pytest.raises(ModeError, match="empty"):
        ChatMode().send_outgoing_turn(session_id, "   ")


def test_a_recall_failure_becomes_a_mode_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """`engine/loop.py` catches ModeError. A RecallError would go past it."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="the bot is not in a call")

    monkeypatch.setattr(httpx, "Client", mock_httpx_client(handler))
    session_id = _session_with_bot()

    with pytest.raises(ModeError, match="recall http 400"):
        ChatMode().send_outgoing_turn(session_id, "Where is the pain?")


def test_the_notice_goes_out_pinned(monkeypatch: pytest.MonkeyPatch) -> None:
    """A pinned message stays visible for a participant who joins later."""
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.read())
        return httpx.Response(200, json={"id": BOT_ID})

    monkeypatch.setattr(httpx, "Client", mock_httpx_client(handler))
    session_id = _session_with_bot()

    ChatMode().send_notice(session_id, "Hello. I am an AI intake assistant.")

    assert seen["body"]["pin"] is True
    assert seen["body"]["message"] == "Hello. I am an AI intake assistant."


def test_a_question_is_not_pinned(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.read())
        return httpx.Response(200, json={"id": BOT_ID})

    monkeypatch.setattr(httpx, "Client", mock_httpx_client(handler))
    session_id = _session_with_bot()

    ChatMode().send_outgoing_turn(session_id, "Where is the pain?")

    assert "pin" not in seen["body"]


def test_a_failed_notice_raises_mode_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="continuous chat is on")

    monkeypatch.setattr(httpx, "Client", mock_httpx_client(handler))
    session_id = _session_with_bot()

    with pytest.raises(ModeError, match="recall http 400"):
        ChatMode().send_notice(session_id, "Hello.")
