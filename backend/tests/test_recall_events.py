"""Tests of the signature check and the event parser."""

import json

import pytest

from app.config import settings
from app.recall import events as recall_events
from app.recall.events import PayloadError, SignatureError
from tests.conftest import signed_headers

FATAL_PAYLOAD = {
    "event": "bot.fatal",
    "data": {
        "data": {
            "code": "fatal",
            "sub_code": "meeting_link_invalid",
            "updated_at": "2026-09-19T10:00:00Z",
        },
        "bot": {"id": "bot-1", "metadata": {"session_id": "s1"}},
    },
}


def _body(payload: dict) -> bytes:
    return json.dumps(payload).encode()


def test_a_good_signature_gives_the_event() -> None:
    body = _body(FATAL_PAYLOAD)

    event = recall_events.verify_and_parse(body, signed_headers(body))

    assert event.name == "bot.fatal"
    assert event.bot_id == "bot-1"
    assert event.sub_code == "meeting_link_invalid"
    assert event.payload == FATAL_PAYLOAD


def test_a_bad_signature_raises() -> None:
    body = _body(FATAL_PAYLOAD)
    headers = signed_headers(body)
    headers["webhook-signature"] = "v1,AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

    with pytest.raises(SignatureError):
        recall_events.verify_and_parse(body, headers)


def test_a_changed_body_raises() -> None:
    body = _body(FATAL_PAYLOAD)
    headers = signed_headers(body)

    with pytest.raises(SignatureError):
        recall_events.verify_and_parse(b'{"event": "bot.done"}', headers)


def test_a_wrong_secret_raises() -> None:
    body = _body(FATAL_PAYLOAD)
    other = signed_headers(body, secret="whsec_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")

    with pytest.raises(SignatureError):
        recall_events.verify_and_parse(body, other)


def test_missing_headers_raise() -> None:
    body = _body(FATAL_PAYLOAD)

    with pytest.raises(SignatureError):
        recall_events.verify_and_parse(body, {"content-type": "application/json"})


def test_an_empty_secret_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    body = _body(FATAL_PAYLOAD)
    headers = signed_headers(body)
    monkeypatch.setattr(settings, "RECALL_WEBHOOK_SECRET", "")

    with pytest.raises(SignatureError, match="no webhook verification secret"):
        recall_events.verify_and_parse(body, headers)


def test_a_bad_signature_does_not_read_the_body(monkeypatch: pytest.MonkeyPatch) -> None:
    """The check comes first. A refused body never reaches `json.loads`."""

    def fail(*args: object, **kwargs: object) -> object:
        raise AssertionError("the module read the payload before the check")

    monkeypatch.setattr(recall_events.json, "loads", fail)
    body = _body(FATAL_PAYLOAD)
    headers = signed_headers(body)
    headers["webhook-signature"] = "v1,AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

    with pytest.raises(SignatureError):
        recall_events.verify_and_parse(body, headers)


def test_a_body_with_no_event_name_raises() -> None:
    body = _body({"data": {"bot": {"id": "bot-1"}}})

    with pytest.raises(PayloadError, match="no event name"):
        recall_events.verify_and_parse(body, signed_headers(body))


def test_a_body_that_is_not_json_raises() -> None:
    body = b"not json at all"

    with pytest.raises(PayloadError, match="not JSON"):
        recall_events.verify_and_parse(body, signed_headers(body))


def test_an_unknown_sub_code_stays_a_string() -> None:
    payload = {
        "event": "bot.fatal",
        "data": {
            "data": {"sub_code": "a_sub_code_from_next_year"},
            "bot": {"id": "bot-9"},
        },
    }
    body = _body(payload)

    event = recall_events.verify_and_parse(body, signed_headers(body))

    assert event.sub_code == "a_sub_code_from_next_year"


def test_an_event_with_no_sub_code_gives_none() -> None:
    payload = {"event": "bot.in_call_recording", "data": {"bot": {"id": "bot-2"}}}
    body = _body(payload)

    event = recall_events.verify_and_parse(body, signed_headers(body))

    assert event.sub_code is None
    assert event.bot_id == "bot-2"


def test_a_realtime_event_gives_the_full_payload() -> None:
    payload = {
        "event": "participant_events.chat_message",
        "data": {
            "data": {"text": "hello", "participant": {"name": "Sam"}},
            "bot": {"id": "bot-3"},
        },
    }
    body = _body(payload)

    event = recall_events.verify_and_parse(body, signed_headers(body))

    assert event.name == "participant_events.chat_message"
    assert event.payload["data"]["data"]["text"] == "hello"
