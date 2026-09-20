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


def test_the_event_time_comes_from_the_payload() -> None:
    body = _body(FATAL_PAYLOAD)

    event = recall_events.verify_and_parse(body, signed_headers(body))

    assert event.event_at == "2026-09-19T10:00:00.000000+00:00"


@pytest.mark.parametrize(
    "written",
    [
        "2026-09-20T05:47:04.556000Z",
        "2026-09-20T05:47:04.556000+00:00",
        "2026-09-20T06:47:04.556000+01:00",
    ],
)
def test_the_same_moment_gives_the_same_text(written: str) -> None:
    """A text comparison is correct only if each value has one shape."""
    payload = {
        "event": "bot.in_call_recording",
        "data": {"data": {"updated_at": written}, "bot": {"id": "bot-1"}},
    }
    body = _body(payload)

    event = recall_events.verify_and_parse(body, signed_headers(body))

    assert event.event_at == "2026-09-20T05:47:04.556000+00:00"


def test_a_later_time_sorts_after_an_earlier_one_as_text() -> None:
    """The store compares the values with SQL `<`, so the order must hold."""
    times = []
    for written in [
        "2026-09-20T05:47:04.508000Z",
        "2026-09-20T05:47:04.556000Z",
        "2026-09-20T05:48:00.000000Z",
        "2026-09-21T00:00:00.000000Z",
    ]:
        payload = {
            "event": "bot.done",
            "data": {"data": {"updated_at": written}, "bot": {"id": "bot-1"}},
        }
        body = _body(payload)
        times.append(recall_events.verify_and_parse(body, signed_headers(body)).event_at)

    assert times == sorted(times)


@pytest.mark.parametrize("bad", ["", "not a time", "2026-13-45", None, 17])
def test_a_time_that_does_not_parse_gives_none(bad: object) -> None:
    """An event with no usable time is applied, so it must not raise."""
    payload = {
        "event": "bot.in_call_recording",
        "data": {"data": {"updated_at": bad}, "bot": {"id": "bot-1"}},
    }
    body = _body(payload)

    event = recall_events.verify_and_parse(body, signed_headers(body))

    assert event.event_at is None


def test_a_payload_with_no_data_block_gives_no_time() -> None:
    """The shape of the dashboard test webhook."""
    payload = {"event": "bot.done", "data": {"bot": {"id": "bot-1"}}}
    body = _body(payload)

    event = recall_events.verify_and_parse(body, signed_headers(body))

    assert event.event_at is None
