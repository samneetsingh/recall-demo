"""Tests of the create-bot call and of the send-chat-message call."""

import json

import httpx
import pytest

from app.config import settings
from app.recall import client as recall_client
from app.modes.base import CONSENT_NOTICE
from app.recall.client import RecallError
from tests.conftest import mock_httpx_client as _transport

BOT_ID = "bot-abc"


@pytest.fixture(autouse=True)
def instant_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """Take the real wait out of the retry backoff."""
    monkeypatch.setattr(recall_client, "_LEAVE_RETRY_SECONDS", 0)


def test_body_has_the_v111_shape() -> None:
    body = recall_client.build_request_body("https://meet.google.com/abc-defg-hij", "s1")

    assert body["meeting_url"] == "https://meet.google.com/abc-defg-hij"
    assert body["bot_name"] == settings.RECALL_BOT_NAME
    assert body["metadata"] == {"session_id": "s1"}

    config = body["recording_config"]
    assert config["participant_events"] == {}

    # No `chat.on_bot_join`. The backend sends the notice, so the order is
    # exact: the notice, then the first question.
    assert "chat" not in body

    endpoint = config["realtime_endpoints"][0]
    assert endpoint["type"] == "webhook"
    assert endpoint["url"] == "https://recall-api.example.test/webhooks/recall"


def test_chat_mode_retains_no_media() -> None:
    """Null retention is the documented zero-data-retention setting."""
    config = recall_client.build_request_body(
        "https://meet.google.com/abc-defg-hij", "s1"
    )["recording_config"]

    assert "retention" in config
    assert config["retention"] is None

    # Recall applies its own video defaults for each key that the body leaves
    # out, so the body must not name one.
    assert not [key for key in config if key.startswith("video")]


def test_chat_mode_asks_for_no_transcript() -> None:
    """A streaming transcript bills every session, and chat mode reads none of it."""
    config = recall_client.build_request_body(
        "https://meet.google.com/abc-defg-hij", "s1"
    )["recording_config"]

    assert "transcript" not in config
    assert config["realtime_endpoints"][0]["events"] == [
        "participant_events.chat_message"
    ]


def test_voice_mode_asks_for_the_streaming_transcript() -> None:
    config = recall_client.build_request_body(
        "https://meet.google.com/abc-defg-hij", "s1", "voice"
    )["recording_config"]

    provider = config["transcript"]["provider"]["recallai_streaming"]
    # Zero data retention supports this mode only.
    assert provider["mode"] == "prioritize_low_latency"
    assert config["retention"] is None
    assert set(config["realtime_endpoints"][0]["events"]) == {
        "participant_events.chat_message",
        "transcript.data",
    }


def test_the_body_sets_automatic_leave() -> None:
    leave = recall_client.build_request_body(
        "https://meet.google.com/abc-defg-hij", "s1"
    )["automatic_leave"]

    # The default is 2 seconds, and the leave is irreversible.
    assert leave["everyone_left_timeout"]["timeout"] > 2
    # The default is 1200 seconds of billing for a session nobody joins.
    assert leave["noone_joined_timeout"] < 1200


def test_create_bot_sends_the_mode_to_the_body(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.read())
        return httpx.Response(201, json={"id": "bot-123"})

    monkeypatch.setattr(httpx, "Client", _transport(handler))
    recall_client.create_bot("https://meet.google.com/abc-defg-hij", "s1", "voice")

    config = seen["body"]["recording_config"]  # type: ignore[index]
    assert "recallai_streaming" in config["transcript"]["provider"]


def test_create_bot_gives_the_bot_id(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        return httpx.Response(201, json={"id": "bot-123"})

    monkeypatch.setattr(httpx, "Client", _transport(handler))
    bot_id = recall_client.create_bot("https://meet.google.com/abc-defg-hij", "s1")

    assert bot_id == "bot-123"
    assert seen["url"] == "https://us-west-2.recall.ai/api/v1/bot/"
    assert seen["auth"] == "Token test-recall-api-key"


def test_no_api_key_raises_before_a_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "RECALL_API_KEY", "")

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("the client sent a request with no API key")

    monkeypatch.setattr(httpx, "Client", _transport(handler))
    with pytest.raises(RecallError, match="no Recall API key"):
        recall_client.create_bot("https://meet.google.com/abc-defg-hij", "s1")


@pytest.mark.parametrize("code", [400, 401, 404, 500])
def test_an_http_error_raises_recall_error(
    monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(code, text="invalid token")

    monkeypatch.setattr(httpx, "Client", _transport(handler))
    with pytest.raises(RecallError) as error:
        recall_client.create_bot("https://meet.google.com/abc-defg-hij", "s1")

    # The message format goes in the `error_reason` column. It must not change.
    assert f"recall http {code}" in str(error.value)
    assert error.value.status == code


def test_an_error_with_no_http_answer_has_no_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("too slow")

    monkeypatch.setattr(httpx, "Client", _transport(handler))
    with pytest.raises(RecallError) as error:
        recall_client.create_bot("https://meet.google.com/abc-defg-hij", "s1")

    assert error.value.status is None


def test_the_reason_has_no_api_key_in_it(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="Invalid token: test-recall-api-key is wrong")

    monkeypatch.setattr(httpx, "Client", _transport(handler))
    with pytest.raises(RecallError) as error:
        recall_client.create_bot("https://meet.google.com/abc-defg-hij", "s1")

    # The body of the answer can hold the key. The message must not.
    assert settings.RECALL_API_KEY not in str(error.value)


def test_a_network_error_raises_recall_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("too slow")

    monkeypatch.setattr(httpx, "Client", _transport(handler))
    with pytest.raises(RecallError, match="recall request failed: ConnectTimeout"):
        recall_client.create_bot("https://meet.google.com/abc-defg-hij", "s1")


def test_an_answer_with_no_id_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"status": "ok"})

    monkeypatch.setattr(httpx, "Client", _transport(handler))
    with pytest.raises(RecallError, match="no bot id"):
        recall_client.create_bot("https://meet.google.com/abc-defg-hij", "s1")


def test_the_consent_notice_fits_in_a_meet_chat_message() -> None:
    """Google Meet refuses a chat message of more than 500 characters."""
    assert 0 < len(CONSENT_NOTICE) <= 500


def test_send_chat_message_posts_to_the_bot(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.read())
        return httpx.Response(200, json={"id": BOT_ID})

    monkeypatch.setattr(httpx, "Client", _transport(handler))
    recall_client.send_chat_message(BOT_ID, "Where is the pain?")

    assert seen["url"] == f"https://us-west-2.recall.ai/api/v1/bot/{BOT_ID}/send_chat_message/"
    assert seen["auth"] == "Token test-recall-api-key"
    # Google Meet takes the recipient `everyone` only. The `pin` key is absent
    # unless a caller asks for it.
    assert seen["body"] == {"to": "everyone", "message": "Where is the pain?"}


def test_send_chat_message_with_no_api_key_raises_before_a_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "RECALL_API_KEY", "")

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("the client sent a request with no API key")

    monkeypatch.setattr(httpx, "Client", _transport(handler))
    with pytest.raises(RecallError, match="no Recall API key"):
        recall_client.send_chat_message(BOT_ID, "Where is the pain?")


@pytest.mark.parametrize("code", [400, 404, 500])
def test_a_failed_send_raises_recall_error(
    monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(code, text="the bot is not in a call")

    monkeypatch.setattr(httpx, "Client", _transport(handler))
    with pytest.raises(RecallError) as error:
        recall_client.send_chat_message(BOT_ID, "Where is the pain?")

    assert f"recall http {code}" in str(error.value)


def test_a_failed_send_has_no_api_key_in_the_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="Invalid token: test-recall-api-key is wrong")

    monkeypatch.setattr(httpx, "Client", _transport(handler))
    with pytest.raises(RecallError) as error:
        recall_client.send_chat_message(BOT_ID, "Where is the pain?")

    assert settings.RECALL_API_KEY not in str(error.value)


def test_a_network_error_on_a_send_raises_recall_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("too slow")

    monkeypatch.setattr(httpx, "Client", _transport(handler))
    with pytest.raises(RecallError, match="recall request failed: ConnectTimeout"):
        recall_client.send_chat_message(BOT_ID, "Where is the pain?")


def test_a_pinned_message_carries_the_pin_key(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.read())
        return httpx.Response(200, json={"id": BOT_ID})

    monkeypatch.setattr(httpx, "Client", _transport(handler))
    recall_client.send_chat_message(BOT_ID, CONSENT_NOTICE, pin=True)

    assert seen["body"] == {"to": "everyone", "message": CONSENT_NOTICE, "pin": True}


def test_leave_call_posts_to_the_bot(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["method"] = request.method
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.read())
        return httpx.Response(200, json={"id": BOT_ID})

    monkeypatch.setattr(httpx, "Client", _transport(handler))
    recall_client.leave_call(BOT_ID)

    assert seen["url"] == f"https://us-west-2.recall.ai/api/v1/bot/{BOT_ID}/leave_call/"
    assert seen["method"] == "POST"
    assert seen["auth"] == "Token test-recall-api-key"
    # The endpoint takes no body.
    assert seen["body"] == {}


def test_leave_call_with_no_api_key_raises_before_a_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "RECALL_API_KEY", "")

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("the client sent a request with no API key")

    monkeypatch.setattr(httpx, "Client", _transport(handler))
    with pytest.raises(RecallError, match="no Recall API key"):
        recall_client.leave_call(BOT_ID)


@pytest.mark.parametrize("code", [400, 404, 500])
def test_a_failed_leave_raises_recall_error(
    monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(code, text="the bot is not in a call")

    monkeypatch.setattr(httpx, "Client", _transport(handler))
    with pytest.raises(RecallError) as error:
        recall_client.leave_call(BOT_ID)

    assert f"recall http {code}" in str(error.value)


def test_a_failed_leave_has_no_api_key_in_the_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="Invalid token: test-recall-api-key is wrong")

    monkeypatch.setattr(httpx, "Client", _transport(handler))
    with pytest.raises(RecallError) as error:
        recall_client.leave_call(BOT_ID)

    assert settings.RECALL_API_KEY not in str(error.value)


def test_a_network_error_on_the_leave_raises_recall_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr(httpx, "Client", _transport(handler))
    with pytest.raises(RecallError, match="recall request failed"):
        recall_client.leave_call(BOT_ID)


@pytest.mark.parametrize("code", [429, 500, 502, 503])
def test_leave_call_retries_once_after_a_transient_failure(
    monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) == 1:
            return httpx.Response(code, text="try again")
        return httpx.Response(200, json={"id": BOT_ID})

    monkeypatch.setattr(httpx, "Client", _transport(handler))
    recall_client.leave_call(BOT_ID)

    assert len(attempts) == 2


def test_leave_call_retries_once_after_a_network_fault(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) == 1:
            raise httpx.ConnectError("no route to host")
        return httpx.Response(200, json={"id": BOT_ID})

    monkeypatch.setattr(httpx, "Client", _transport(handler))
    recall_client.leave_call(BOT_ID)

    assert len(attempts) == 2


def test_leave_call_gives_up_after_the_one_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return httpx.Response(503, text="unavailable")

    monkeypatch.setattr(httpx, "Client", _transport(handler))
    with pytest.raises(RecallError, match="recall http 503"):
        recall_client.leave_call(BOT_ID)

    assert len(attempts) == 2


@pytest.mark.parametrize("code", [400, 401, 404])
def test_leave_call_does_not_retry_a_permanent_failure(
    monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    """A bot that is gone stays gone. A second attempt cannot change the answer."""
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return httpx.Response(code, text="the bot is not in a call")

    monkeypatch.setattr(httpx, "Client", _transport(handler))
    with pytest.raises(RecallError):
        recall_client.leave_call(BOT_ID)

    assert len(attempts) == 1
