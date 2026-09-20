"""The tests of POST /webhooks/recall: the status map, and the chat wire."""

import itertools
import json
import time

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import session_store
from app.engine import intake, prompts, summary as summary_engine
from app.modes.base import CLOSING_MESSAGE, CONSENT_NOTICE, CONSENT_NOTICE_VOICE
from app.recall import client as recall_client
from app.recall.client import RecallError
from app.routes import webhooks
from app.tts import openai_tts
from tests.conftest import chat_payload, signed_headers, transcript_payload

BOT_ID = "bot-abc"
MEETING_URL = "https://meet.google.com/abc-defg-hij"

SUMMARY_ANSWER = {field: f"the {field}" for field in prompts.SUMMARY_FIELDS}

# The real wake-up, bound at import, before the `offline` fixture replaces it.
REAL_ARM = webhooks._arm_voice_flush


@pytest.fixture
def session_id() -> str:
    """Make a session with a bot id, the state after `POST /sessions`."""
    session = session_store.create_session(MEETING_URL)
    session_store.set_bot_id(session.id, BOT_ID)
    session_store.set_status(session.id, "waiting_for_bot")
    return session.id


@pytest.fixture
def sent() -> list[str]:
    """The messages that went to the meeting chat, in order."""
    return []


@pytest.fixture
def pinned() -> list[str]:
    """The messages that went out with a pin."""
    return []


@pytest.fixture
def left() -> list[str]:
    """The bot ids that were taken out of a call."""
    return []


@pytest.fixture
def spoken() -> list[str]:
    """The texts that went to TTS, in order. Voice mode says these."""
    return []


@pytest.fixture
def played() -> list[bytes]:
    """The audio that went to the output audio endpoint of a bot."""
    return []


@pytest.fixture
def armed() -> list[str]:
    """The sessions that got a silence wake-up."""
    return []


@pytest.fixture(autouse=True)
def offline(
    monkeypatch: pytest.MonkeyPatch,
    sent: list[str],
    pinned: list[str],
    left: list[str],
    spoken: list[str],
    played: list[bytes],
    armed: list[str],
) -> None:
    """No test in this file calls OpenAI or Recall.

    The route starts the intake now, so a test that makes a session
    `in_progress` reaches the model and the chat send. Both are fakes here.
    Section 5a added a third caller, `leave_call`, which is a fake for the same
    reason: a route that gains a caller takes a test file back on to the
    network.

    Section 6 adds two more callers, `openai_tts.speak` and
    `send_output_audio`. **They are fakes here before the route calls them.**
    This is lesson 3 of ../../tasks/lessons.md.
    """
    asked = {"count": 0}

    def fake_intake(system, messages, schema, schema_name):
        asked["count"] += 1
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
    def fake_send(bot_id: str, text: str, pin: bool = False) -> None:
        sent.append(text)
        if pin:
            pinned.append(text)

    monkeypatch.setattr(recall_client, "send_chat_message", fake_send)

    def fake_leave(bot_id: str) -> None:
        left.append(bot_id)

    monkeypatch.setattr(recall_client, "leave_call", fake_leave)

    def fake_speak(text: str) -> bytes:
        spoken.append(text)
        return b"fake-mp3-bytes"

    monkeypatch.setattr(openai_tts, "speak", fake_speak)

    def fake_output_audio(bot_id: str, audio: bytes) -> None:
        played.append(audio)

    monkeypatch.setattr(recall_client, "send_output_audio", fake_output_audio)

    def fake_arm(session_id: str) -> None:
        armed.append(session_id)

    # The real wake-up is a thread that fires 2.5 seconds later, which is after
    # the test deleted its database file. The tests call `flush_voice_turn`
    # themselves, and one test puts the real wake-up back.
    monkeypatch.setattr(webhooks, "_arm_voice_flush", fake_arm)
    # A gap of 0 makes each part old enough at once.
    monkeypatch.setattr(settings, "VOICE_TURN_GAP_SECONDS", 0.0)
    # The real delay is 3 seconds, which each test in this file would wait.
    monkeypatch.setattr(settings, "BOT_LEAVE_DELAY_SECONDS", 0.0)


def _post(client: TestClient, payload: dict, message_id: str = "msg_test_00000001"):
    body = json.dumps(payload).encode()
    return client.post(
        "/webhooks/recall",
        content=body,
        headers=signed_headers(body, message_id=message_id),
    )


def _chat(
    client: TestClient,
    text: str = "I get bad headaches",
    sender: str = "Samneet Singh",
    bot_id: str = BOT_ID,
    message_id: str = "msg_test_00000001",
):
    """Send one signed chat message, in the true shape of the Recall event."""
    return _post(client, chat_payload(text, sender, bot_id), message_id=message_id)


def _bot_event(name: str, sub_code: str | None = None, bot_id: str = BOT_ID) -> dict:
    data: dict = {"bot": {"id": bot_id, "metadata": {}}}
    if sub_code is not None:
        data["data"] = {"code": name.split(".")[-1], "sub_code": sub_code}
    return {"event": name, "data": data}


def test_a_bad_signature_gives_401(client: TestClient) -> None:
    body = json.dumps(_bot_event("bot.fatal", "meeting_link_invalid")).encode()
    headers = signed_headers(body)
    headers["webhook-signature"] = "v1,AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

    result = client.post("/webhooks/recall", content=body, headers=headers)

    assert result.status_code == 401


def test_no_signature_headers_give_401(client: TestClient) -> None:
    result = client.post("/webhooks/recall", json=_bot_event("bot.fatal"))

    assert result.status_code == 401


def test_a_bad_signature_does_not_change_the_session(
    client: TestClient, session_id: str
) -> None:
    body = json.dumps(_bot_event("bot.fatal", "meeting_link_invalid")).encode()
    headers = signed_headers(body)
    headers["webhook-signature"] = "v1,AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

    client.post("/webhooks/recall", content=body, headers=headers)

    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "waiting_for_bot"


def test_a_signed_body_that_is_not_an_event_gives_400(client: TestClient) -> None:
    body = json.dumps({"data": {}}).encode()

    result = client.post("/webhooks/recall", content=body, headers=signed_headers(body))

    assert result.status_code == 400


def test_bot_fatal_gives_the_status_error_and_the_sub_code(
    client: TestClient, session_id: str
) -> None:
    result = _post(client, _bot_event("bot.fatal", "meeting_link_invalid"))

    assert result.status_code == 200
    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "error"
    assert session.error_reason == "meeting_link_invalid"


def test_bot_in_call_recording_gives_in_progress(
    client: TestClient, session_id: str
) -> None:
    result = _post(client, _bot_event("bot.in_call_recording"))

    assert result.status_code == 200
    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "in_progress"
    assert session.error_reason is None


@pytest.mark.parametrize(
    "name",
    [
        "bot.joining_call",
        "bot.in_waiting_room",
        "bot.in_call_not_recording",
        "bot.recording_permission_allowed",
    ],
)
def test_the_join_events_give_waiting_for_bot(
    client: TestClient, session_id: str, name: str
) -> None:
    session_store.set_status(session_id, "creating_bot")

    _post(client, _bot_event(name))

    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "waiting_for_bot"


def test_recording_permission_denied_gives_error(
    client: TestClient, session_id: str
) -> None:
    _post(client, _bot_event("bot.recording_permission_denied", "permission_denied"))

    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "error"
    assert session.error_reason == "permission_denied"


def test_an_unknown_sub_code_goes_in_the_column(
    client: TestClient, session_id: str
) -> None:
    """Recall adds sub-codes. A new value must not stop the application."""
    _post(client, _bot_event("bot.fatal", "a_sub_code_from_next_year"))

    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "error"
    assert session.error_reason == "a_sub_code_from_next_year"


def test_call_ended_before_the_intake_gives_error_with_a_prefix(
    client: TestClient, session_id: str
) -> None:
    session_store.set_status(session_id, "in_progress")

    _post(client, _bot_event("bot.call_ended", "call_ended_by_host"))

    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "error"
    assert session.error_reason == "call_ended:call_ended_by_host"


def test_call_ended_after_complete_makes_no_change(
    client: TestClient, session_id: str
) -> None:
    session_store.set_status(session_id, "complete")

    result = _post(client, _bot_event("bot.call_ended", "call_ended_by_host"))

    assert result.status_code == 200
    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "complete"
    assert session.error_reason is None


def test_bot_fatal_after_complete_makes_no_change(
    client: TestClient, session_id: str
) -> None:
    session_store.set_status(session_id, "complete")

    _post(client, _bot_event("bot.fatal", "bot_errored"))

    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "complete"


def test_bot_done_makes_no_change(client: TestClient, session_id: str) -> None:
    session_store.set_status(session_id, "error", "meeting_link_invalid")

    result = _post(client, _bot_event("bot.done"))

    assert result.status_code == 200
    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "error"
    assert session.error_reason == "meeting_link_invalid"


def test_an_unknown_event_name_gives_200_and_no_change(
    client: TestClient, session_id: str
) -> None:
    result = _post(client, _bot_event("bot.an_event_from_next_year"))

    assert result.status_code == 200
    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "waiting_for_bot"


def test_an_unknown_bot_id_gives_200(client: TestClient, session_id: str) -> None:
    result = _post(client, _bot_event("bot.fatal", "bot_errored", bot_id="bot-other"))

    assert result.status_code == 200
    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "waiting_for_bot"


@pytest.mark.parametrize(
    "name", ["participant_events.chat_message", "transcript.data"]
)
def test_a_realtime_event_gives_200_and_no_status_change(
    client: TestClient, session_id: str, name: str
) -> None:
    """A payload with no text and no words makes no turn in either mode."""
    result = _post(client, {"event": name, "data": {"bot": {"id": BOT_ID}}})

    assert result.status_code == 200
    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "waiting_for_bot"


# The four events of the live test of session 05, with the times that Recall
# gave them. Recall sent them out of order: `bot.in_waiting_room` went out
# before `bot.joining_call`. See ../../docs/task-02-event-ordering/todo.md.
LIVE_EVENTS = [
    ("bot.joining_call", "2026-09-20T05:47:04.508000Z"),
    ("bot.in_waiting_room", "2026-09-20T05:47:04.524000Z"),
    ("bot.in_call_not_recording", "2026-09-20T05:47:04.532000Z"),
    ("bot.in_call_recording", "2026-09-20T05:47:04.556000Z"),
]


def _timed_event(name: str, updated_at: str | None, bot_id: str) -> dict:
    data: dict = {"bot": {"id": bot_id, "metadata": {}}}
    if updated_at is not None:
        data["data"] = {"code": name.split(".")[-1], "updated_at": updated_at}
    return {"event": name, "data": data}


def _session_with_bot(bot_id: str) -> str:
    session = session_store.create_session(MEETING_URL)
    session_store.set_bot_id(session.id, bot_id)
    session_store.set_status(session.id, "waiting_for_bot")
    return session.id


@pytest.mark.parametrize("order", list(itertools.permutations(LIVE_EVENTS)))
def test_every_order_of_the_live_events_ends_in_progress(
    client: TestClient, order: tuple
) -> None:
    """Recall has no delivery order. Each of the 24 orders must give the same end."""
    bot_id = f"bot-order-{abs(hash(order))}"
    session_id = _session_with_bot(bot_id)

    for name, updated_at in order:
        result = _post(client, _timed_event(name, updated_at, bot_id))
        assert result.status_code == 200

    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "in_progress", f"order {[n for n, _ in order]}"


def test_a_late_event_does_not_put_back_an_old_status(
    client: TestClient, session_id: str
) -> None:
    """The failure this task prevents: the bot is recording, the session is not."""
    _post(client, _timed_event("bot.in_call_recording", LIVE_EVENTS[3][1], BOT_ID))
    _post(client, _timed_event("bot.in_call_not_recording", LIVE_EVENTS[2][1], BOT_ID))

    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "in_progress"


def test_the_same_event_two_times_changes_the_session_one_time(
    client: TestClient, session_id: str
) -> None:
    """Svix delivers at least one time, so a duplicate is normal."""
    payload = _timed_event("bot.in_call_recording", LIVE_EVENTS[3][1], BOT_ID)

    assert _post(client, payload).status_code == 200
    first = session_store.get_session(session_id)
    assert _post(client, payload).status_code == 200
    second = session_store.get_session(session_id)

    assert first is not None and second is not None
    assert first.status == second.status == "in_progress"
    assert first.updated_at == second.updated_at


def test_an_event_with_no_time_is_applied(client: TestClient, session_id: str) -> None:
    """The test webhook of the dashboard has no `data.data`. Do not lose a true event."""
    result = _post(client, _timed_event("bot.in_call_recording", None, BOT_ID))

    assert result.status_code == 200
    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "in_progress"
    assert session.last_event_at is None


def test_an_event_with_no_time_keeps_the_last_time(
    client: TestClient, session_id: str
) -> None:
    _post(client, _timed_event("bot.in_call_recording", LIVE_EVENTS[3][1], BOT_ID))
    before = session_store.get_session(session_id)

    _post(client, _timed_event("bot.in_call_not_recording", None, BOT_ID))
    after = session_store.get_session(session_id)

    assert before is not None and after is not None
    assert after.last_event_at == before.last_event_at


def test_an_old_event_does_not_change_a_complete_session(
    client: TestClient, session_id: str
) -> None:
    session_store.set_status(session_id, "complete")

    _post(client, _timed_event("bot.in_call_recording", LIVE_EVENTS[3][1], BOT_ID))

    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "complete"


def test_the_event_time_is_stored_in_one_format(
    client: TestClient, session_id: str
) -> None:
    _post(client, _timed_event("bot.in_call_recording", LIVE_EVENTS[3][1], BOT_ID))

    session = session_store.get_session(session_id)
    assert session is not None
    assert session.last_event_at == "2026-09-20T05:47:04.556000+00:00"


# --- The chat wire: section 5 -------------------------------------------


def test_the_bot_in_the_call_sends_the_notice_and_then_the_first_question(
    client: TestClient, session_id: str, sent: list[str], pinned: list[str]
) -> None:
    """The order is the whole reason the notice left the create-bot body."""
    _post(client, _bot_event("bot.in_call_recording"))

    assert sent == [CONSENT_NOTICE, "question 1"]
    assert pinned == [CONSENT_NOTICE]
    log = session_store.get_turns(session_id)
    assert log == [{"role": "bot", "text": "question 1"}]


def test_a_chat_message_gives_one_turn_and_one_question(
    client: TestClient, session_id: str, sent: list[str]
) -> None:
    _post(client, _bot_event("bot.in_call_recording"))

    result = _chat(client, "I get bad headaches", message_id="msg_02")

    assert result.status_code == 200
    log = session_store.get_turns(session_id)
    assert log == [
        {"role": "bot", "text": "question 1"},
        {"role": "patient", "text": "I get bad headaches"},
        {"role": "bot", "text": "question 2"},
    ]
    assert sent == [CONSENT_NOTICE, "question 1", "question 2"]


def test_the_same_chat_message_two_times_gives_one_turn(
    client: TestClient, session_id: str, sent: list[str]
) -> None:
    """Recall delivers at least one time. The `webhook-id` is the `event_id`."""
    _post(client, _bot_event("bot.in_call_recording"))

    _chat(client, "I get bad headaches", message_id="msg_02")
    _chat(client, "I get bad headaches", message_id="msg_02")

    assert len(session_store.get_turns(session_id)) == 3
    assert sent == [CONSENT_NOTICE, "question 1", "question 2"]


def test_the_bot_does_not_answer_itself(
    client: TestClient, session_id: str, sent: list[str]
) -> None:
    """The bot receives its own messages back. It must not interview itself."""
    _post(client, _bot_event("bot.in_call_recording"))

    _chat(client, "question 1", sender=settings.RECALL_BOT_NAME, message_id="msg_02")

    assert session_store.get_turns(session_id) == [
        {"role": "bot", "text": "question 1"}
    ]
    assert sent == [CONSENT_NOTICE, "question 1"]


def test_a_chat_message_for_an_unknown_bot_gives_200(
    client: TestClient, session_id: str, sent: list[str]
) -> None:
    result = _chat(client, bot_id="bot-other", message_id="msg_02")

    assert result.status_code == 200
    assert session_store.get_turns(session_id) == []
    assert sent == []


def test_a_chat_message_before_the_bot_is_in_the_call_changes_nothing(
    client: TestClient, session_id: str, sent: list[str]
) -> None:
    result = _chat(client, "hello?", message_id="msg_02")

    assert result.status_code == 200
    assert session_store.get_turns(session_id) == []
    assert sent == []


def test_an_empty_chat_message_changes_nothing(
    client: TestClient, session_id: str, sent: list[str]
) -> None:
    _post(client, _bot_event("bot.in_call_recording"))

    _chat(client, "   ", message_id="msg_02")

    assert len(session_store.get_turns(session_id)) == 1


def test_the_last_answer_gives_the_summary_and_the_closing_line(
    client: TestClient, session_id: str, sent: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _post(client, _bot_event("bot.in_call_recording"))
    # The model ends the intake on the next call.
    monkeypatch.setattr(
        intake,
        "ask_model",
        lambda system, messages, schema, name: {
            "action": "complete",
            "turn": 2,
            "question": "",
            "notes": "",
        },
    )

    _chat(client, "two weeks", message_id="msg_02")

    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "complete"
    assert session.summary == SUMMARY_ANSWER
    assert sent == [CONSENT_NOTICE, "question 1", CLOSING_MESSAGE]


def test_a_failed_send_puts_the_session_in_error(
    client: TestClient, session_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A send that failed must not be silent: the frontend reads the reason."""

    def refuse(bot_id: str, text: str, pin: bool = False) -> None:
        raise RecallError("recall http 400: the bot is not in a call")

    monkeypatch.setattr(recall_client, "send_chat_message", refuse)

    _post(client, _bot_event("bot.in_call_recording"))

    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "error"
    assert "recall http 400" in (session.error_reason or "")
    # A question that the patient never got is not in the log.
    assert session_store.get_turns(session_id) == []


def test_a_failed_closing_line_keeps_the_session_complete(
    client: TestClient, session_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The summary is written. A closing line that failed must not take it away."""
    _post(client, _bot_event("bot.in_call_recording"))
    monkeypatch.setattr(
        intake,
        "ask_model",
        lambda system, messages, schema, name: {
            "action": "complete",
            "turn": 2,
            "question": "",
            "notes": "",
        },
    )

    def refuse(bot_id: str, text: str, pin: bool = False) -> None:
        raise RecallError("recall http 400: the call ended")

    monkeypatch.setattr(recall_client, "send_chat_message", refuse)

    _chat(client, "two weeks", message_id="msg_02")

    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "complete"
    assert session.summary == SUMMARY_ANSWER


def test_a_chat_message_in_a_voice_session_makes_no_turn(
    client: TestClient, sent: list[str], spoken: list[str]
) -> None:
    """One session has one mode. Sam selected this.

    A patient who types in a voice call gets no answer, and the container log
    is the one place that says so.
    """
    session = session_store.create_session(MEETING_URL, "voice")
    session_store.set_bot_id(session.id, "bot-voice")
    session_store.set_status(session.id, "in_progress")

    result = _chat(client, "I get bad headaches", bot_id="bot-voice", message_id="msg_02")

    assert result.status_code == 200
    after = session_store.get_session(session.id)
    assert after is not None
    assert after.status == "in_progress"
    assert session_store.get_turns(session.id) == []
    assert sent == []
    assert spoken == []


def test_a_message_after_the_intake_sends_no_second_closing_line(
    client: TestClient, session_id: str, sent: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _post(client, _bot_event("bot.in_call_recording"))
    monkeypatch.setattr(
        intake,
        "ask_model",
        lambda system, messages, schema, name: {
            "action": "complete",
            "turn": 2,
            "question": "",
            "notes": "",
        },
    )
    _chat(client, "two weeks", message_id="msg_02")
    assert sent == [CONSENT_NOTICE, "question 1", CLOSING_MESSAGE]

    _chat(client, "thank you", message_id="msg_03")

    assert sent == [CONSENT_NOTICE, "question 1", CLOSING_MESSAGE]
    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "complete"


def test_a_notice_that_fails_does_not_stop_the_first_question(
    client: TestClient, session_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refused pin must not cost the intake. Only the notice is lost."""
    asked: list[str] = []

    def send(bot_id: str, text: str, pin: bool = False) -> None:
        if pin:
            raise RecallError("recall http 400: continuous chat is on")
        asked.append(text)

    monkeypatch.setattr(recall_client, "send_chat_message", send)

    _post(client, _bot_event("bot.in_call_recording"))

    assert asked == ["question 1"]
    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "in_progress"
    assert session_store.get_turns(session_id) == [
        {"role": "bot", "text": "question 1"}
    ]


def _complete_on_the_next_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the model end the intake on its next answer."""
    monkeypatch.setattr(
        intake,
        "ask_model",
        lambda system, messages, schema, name: {
            "action": "complete",
            "turn": 2,
            "question": "",
            "notes": "",
        },
    )


def test_a_complete_intake_takes_the_bot_out_of_the_call(
    client: TestClient,
    session_id: str,
    sent: list[str],
    left: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The patient must not have to remove the bot."""
    _post(client, _bot_event("bot.in_call_recording"))
    _complete_on_the_next_call(monkeypatch)

    _chat(client, "two weeks", message_id="msg_02")

    assert sent == [CONSENT_NOTICE, "question 1", CLOSING_MESSAGE]
    assert left == [BOT_ID]


def test_the_closing_line_goes_out_before_the_leave(
    client: TestClient, session_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A leave before the line cuts the line. The order is the whole point."""
    order: list[str] = []

    def send(bot_id: str, text: str, pin: bool = False) -> None:
        order.append(f"message:{text}")

    def leave(bot_id: str) -> None:
        order.append("leave")

    monkeypatch.setattr(recall_client, "send_chat_message", send)
    monkeypatch.setattr(recall_client, "leave_call", leave)

    _post(client, _bot_event("bot.in_call_recording"))
    _complete_on_the_next_call(monkeypatch)
    _chat(client, "two weeks", message_id="msg_02")

    assert order[-2:] == [f"message:{CLOSING_MESSAGE}", "leave"]


def test_an_intake_that_continues_does_not_leave_the_call(
    client: TestClient, session_id: str, left: list[str]
) -> None:
    _post(client, _bot_event("bot.in_call_recording"))

    _chat(client, "two weeks", message_id="msg_02")

    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "in_progress"
    assert left == []


def test_a_message_after_the_intake_does_not_leave_a_second_time(
    client: TestClient,
    session_id: str,
    left: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The leave is irreversible. A second call is an error against Recall."""
    _post(client, _bot_event("bot.in_call_recording"))
    _complete_on_the_next_call(monkeypatch)
    _chat(client, "two weeks", message_id="msg_02")
    assert left == [BOT_ID]

    _chat(client, "thank you", message_id="msg_03")

    assert left == [BOT_ID]


def test_a_failed_leave_keeps_the_session_complete(
    client: TestClient, session_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The summary is written. A bot that stays in the call costs no data."""
    _post(client, _bot_event("bot.in_call_recording"))
    _complete_on_the_next_call(monkeypatch)

    def refuse(bot_id: str) -> None:
        raise RecallError("recall http 400: the bot is not in a call")

    monkeypatch.setattr(recall_client, "leave_call", refuse)

    _chat(client, "two weeks", message_id="msg_02")

    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "complete"
    assert session.summary == SUMMARY_ANSWER


def test_a_session_that_goes_to_error_keeps_its_bot(
    client: TestClient, session_id: str, left: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sam selected this: an error usually means that the bot takes no command."""

    def refuse(bot_id: str, text: str, pin: bool = False) -> None:
        raise RecallError("recall http 400: the bot is not in a call")

    monkeypatch.setattr(recall_client, "send_chat_message", refuse)

    _post(client, _bot_event("bot.in_call_recording"))

    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "error"
    assert left == []


def test_a_session_with_no_bot_id_does_not_raise_on_the_leave(
    client: TestClient, left: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A session that got no bot has nothing to take out of a call."""
    from app.routes import webhooks

    session = session_store.create_session(MEETING_URL)
    session_store.set_status(session.id, "complete")

    webhooks._leave_call(session_store.get_session(session.id))

    assert left == []


def test_the_leave_waits_before_it_calls_recall(
    client: TestClient, session_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The wait is what keeps the closing line. A delay of 0 makes no call."""
    from app.routes import webhooks

    waited: list[float] = []
    monkeypatch.setattr(webhooks.time, "sleep", lambda seconds: waited.append(seconds))

    session = session_store.get_session(session_id)
    assert session is not None

    monkeypatch.setattr(settings, "BOT_LEAVE_DELAY_SECONDS", 0.0)
    webhooks._leave_call(session)
    assert waited == []

    monkeypatch.setattr(settings, "BOT_LEAVE_DELAY_SECONDS", 3.0)
    webhooks._leave_call(session)
    assert waited == [3.0]


# Voice mode. Section 6 of ../../docs/TASKS.md.
#
# `transcript.data` is a finalized utterance and it is not a turn: a patient
# answers in parts. The parts wait in the `voice_buffers` table, and a silence
# of VOICE_TURN_GAP_SECONDS ends the turn. The tests call `flush_voice_turn`
# in place of the wake-up thread, and one test puts the real wake-up back.

VOICE_BOT_ID = "bot-voice"


@pytest.fixture
def voice_session_id() -> str:
    """A voice session with a bot id, the state after `POST /sessions`."""
    session = session_store.create_session(MEETING_URL, "voice")
    session_store.set_bot_id(session.id, VOICE_BOT_ID)
    session_store.set_status(session.id, "waiting_for_bot")
    return session.id


def _utterance(
    client: TestClient,
    text: str = "I get bad headaches",
    speaker: str = "Samneet Singh",
    bot_id: str = VOICE_BOT_ID,
    message_id: str = "msg_test_00000001",
):
    """Send one signed transcript utterance, in the true shape of the event."""
    return _post(
        client, transcript_payload(text, speaker, bot_id), message_id=message_id
    )


def test_the_voice_notice_is_spoken_and_not_pinned(
    client: TestClient, voice_session_id: str, spoken: list[str], pinned: list[str]
) -> None:
    _post(client, _bot_event("bot.in_call_recording", bot_id=VOICE_BOT_ID))

    assert spoken == [CONSENT_NOTICE_VOICE, "question 1"]
    assert pinned == []


def test_the_voice_notice_does_not_say_the_chat(
    client: TestClient, voice_session_id: str, spoken: list[str]
) -> None:
    """The last sentence of the notice says where to answer."""
    _post(client, _bot_event("bot.in_call_recording", bot_id=VOICE_BOT_ID))

    assert spoken[0].endswith("Please answer out loud.")


def test_the_chat_notice_did_not_change(
    client: TestClient, session_id: str, sent: list[str], pinned: list[str]
) -> None:
    """Voice mode is an addition. Chat mode must give the same result."""
    _post(client, _bot_event("bot.in_call_recording"))

    assert sent == [CONSENT_NOTICE, "question 1"]
    assert pinned == [CONSENT_NOTICE]


def test_the_first_question_is_played_as_audio(
    client: TestClient, voice_session_id: str, played: list[bytes]
) -> None:
    _post(client, _bot_event("bot.in_call_recording", bot_id=VOICE_BOT_ID))

    assert played == [b"fake-mp3-bytes", b"fake-mp3-bytes"]


def test_one_utterance_makes_no_turn(
    client: TestClient, voice_session_id: str, armed: list[str], spoken: list[str]
) -> None:
    """An utterance is not a turn. It goes in the buffer and arms the silence."""
    _post(client, _bot_event("bot.in_call_recording", bot_id=VOICE_BOT_ID))
    spoken.clear()

    result = _utterance(client, "I get")

    assert result.status_code == 200
    assert session_store.get_turns(voice_session_id) == [
        {"role": "bot", "text": "question 1"}
    ]
    assert armed == [voice_session_id]
    assert spoken == []


def test_three_utterances_and_a_silence_make_one_turn(
    client: TestClient, voice_session_id: str, spoken: list[str]
) -> None:
    """The patient answers in three parts. The engine gets one answer."""
    _post(client, _bot_event("bot.in_call_recording", bot_id=VOICE_BOT_ID))
    spoken.clear()

    _utterance(client, "I get", message_id="msg_02")
    _utterance(client, "bad headaches", message_id="msg_03")
    _utterance(client, "most mornings", message_id="msg_04")
    webhooks.flush_voice_turn(voice_session_id)

    assert session_store.get_turns(voice_session_id) == [
        {"role": "bot", "text": "question 1"},
        {"role": "patient", "text": "I get bad headaches most mornings"},
        {"role": "bot", "text": "question 2"},
    ]
    assert spoken == ["question 2"]


def test_the_event_id_of_a_voice_turn_is_the_buffer_id(
    client: TestClient, voice_session_id: str
) -> None:
    """A turn is made of many events, so no Svix id names it. The row does."""
    _post(client, _bot_event("bot.in_call_recording", bot_id=VOICE_BOT_ID))
    _utterance(client, "I get bad headaches", message_id="msg_02")

    webhooks.flush_voice_turn(voice_session_id)

    with session_store.connect() as connection:
        rows = connection.execute(
            "SELECT role, event_id FROM turns WHERE session_id = ? ORDER BY id",
            (voice_session_id,),
        ).fetchall()
    assert [(row["role"], row["event_id"]) for row in rows] == [
        ("bot", None),
        ("patient", "voice-1"),
        ("bot", None),
    ]


def test_a_second_silence_makes_no_second_turn(
    client: TestClient, voice_session_id: str
) -> None:
    """A wake-up is not cancelled, so two can fire for one buffer."""
    _post(client, _bot_event("bot.in_call_recording", bot_id=VOICE_BOT_ID))
    _utterance(client, "I get bad headaches", message_id="msg_02")
    webhooks.flush_voice_turn(voice_session_id)

    webhooks.flush_voice_turn(voice_session_id)

    assert session_store.get_turns(voice_session_id) == [
        {"role": "bot", "text": "question 1"},
        {"role": "patient", "text": "I get bad headaches"},
        {"role": "bot", "text": "question 2"},
    ]


def test_a_wake_up_that_is_too_early_makes_no_turn(
    client: TestClient, voice_session_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A part arrived after the wake-up started. The patient still speaks."""
    _post(client, _bot_event("bot.in_call_recording", bot_id=VOICE_BOT_ID))
    _utterance(client, "I get", message_id="msg_02")
    monkeypatch.setattr(settings, "VOICE_TURN_GAP_SECONDS", 30.0)

    webhooks.flush_voice_turn(voice_session_id)

    assert session_store.get_turns(voice_session_id) == [
        {"role": "bot", "text": "question 1"}
    ]
    assert session_store.open_voice_buffer(voice_session_id) is not None


def test_the_bot_does_not_answer_itself(
    client: TestClient, voice_session_id: str, armed: list[str]
) -> None:
    """The bot plays its audio into the meeting, so Recall transcribes it."""
    _post(client, _bot_event("bot.in_call_recording", bot_id=VOICE_BOT_ID))

    _utterance(client, "question 1", speaker=settings.RECALL_BOT_NAME, message_id="msg_02")

    assert armed == []
    assert session_store.open_voice_buffer(voice_session_id) is None


def test_a_transcript_in_a_chat_session_arms_nothing(
    client: TestClient, session_id: str, armed: list[str]
) -> None:
    """One `realtime_endpoints` list carries both events, so a chat bot gets these."""
    _post(client, _bot_event("bot.in_call_recording"))

    _utterance(client, "I get bad headaches", bot_id=BOT_ID, message_id="msg_02")

    assert armed == []
    assert session_store.open_voice_buffer(session_id) is None


def test_a_transcript_for_a_bot_that_no_session_holds_gives_200(
    client: TestClient, voice_session_id: str, armed: list[str]
) -> None:
    result = _utterance(client, "I get", bot_id="bot-other")

    assert result.status_code == 200
    assert armed == []


def test_a_whole_voice_intake_says_the_closing_line_and_leaves(
    client: TestClient,
    voice_session_id: str,
    spoken: list[str],
    left: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _post(client, _bot_event("bot.in_call_recording", bot_id=VOICE_BOT_ID))
    _utterance(client, "I get bad headaches", message_id="msg_02")
    _complete_on_the_next_call(monkeypatch)

    webhooks.flush_voice_turn(voice_session_id)

    session = session_store.get_session(voice_session_id)
    assert session is not None
    assert session.status == "complete"
    assert session.summary == SUMMARY_ANSWER
    assert spoken == [CONSENT_NOTICE_VOICE, "question 1", CLOSING_MESSAGE]
    assert left == [VOICE_BOT_ID]


def test_a_voice_turn_after_the_intake_makes_no_second_closing_line(
    client: TestClient,
    voice_session_id: str,
    spoken: list[str],
    left: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _post(client, _bot_event("bot.in_call_recording", bot_id=VOICE_BOT_ID))
    _utterance(client, "I get bad headaches", message_id="msg_02")
    _complete_on_the_next_call(monkeypatch)
    webhooks.flush_voice_turn(voice_session_id)

    _utterance(client, "one more thing", message_id="msg_03")
    webhooks.flush_voice_turn(voice_session_id)

    assert spoken.count(CLOSING_MESSAGE) == 1
    assert left == [VOICE_BOT_ID]


def test_a_flush_for_a_session_that_is_gone_does_nothing(
    client: TestClient, spoken: list[str]
) -> None:
    webhooks.flush_voice_turn("no-such-session")

    assert spoken == []


def test_a_failed_tts_puts_the_session_in_error(
    client: TestClient, voice_session_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A question that nothing said must not leave the session `in_progress`."""

    def fail(text: str) -> bytes:
        raise openai_tts.TTSError("openai tts failed: no key")

    _post(client, _bot_event("bot.in_call_recording", bot_id=VOICE_BOT_ID))
    monkeypatch.setattr(openai_tts, "speak", fail)
    _utterance(client, "I get bad headaches", message_id="msg_02")

    webhooks.flush_voice_turn(voice_session_id)

    session = session_store.get_session(voice_session_id)
    assert session is not None
    assert session.status == "error"
    assert "openai tts failed" in (session.error_reason or "")


def test_the_wake_up_ends_the_turn_by_itself(
    client: TestClient, voice_session_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real thread, with a gap of 0. Each other test calls the flush."""
    monkeypatch.setattr(webhooks, "_arm_voice_flush", REAL_ARM)
    _post(client, _bot_event("bot.in_call_recording", bot_id=VOICE_BOT_ID))

    _utterance(client, "I get bad headaches", message_id="msg_02")

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if len(session_store.get_turns(voice_session_id)) >= 3:
            break
        time.sleep(0.02)

    assert session_store.get_turns(voice_session_id) == [
        {"role": "bot", "text": "question 1"},
        {"role": "patient", "text": "I get bad headaches"},
        {"role": "bot", "text": "question 2"},
    ]
