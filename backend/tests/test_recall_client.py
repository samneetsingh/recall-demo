"""Tests of the create-bot call and of the send-chat-message call."""

import json

import httpx
import pytest

from app.config import settings
from app.recall import client as recall_client
from app.recall.client import CONSENT_NOTICE, RecallError
from tests.conftest import mock_httpx_client as _transport

BOT_ID = "bot-abc"


def test_body_has_the_v111_shape() -> None:
    body = recall_client.build_request_body("https://meet.google.com/abc-defg-hij", "s1")

    assert body["meeting_url"] == "https://meet.google.com/abc-defg-hij"
    assert body["bot_name"] == settings.RECALL_BOT_NAME
    assert body["metadata"] == {"session_id": "s1"}

    config = body["recording_config"]
    assert config["participant_events"] == {}
    assert "recallai_streaming" in config["transcript"]["provider"]

    hook = body["chat"]["on_bot_join"]
    assert hook["send_to"] == "everyone"
    assert hook["message"] == CONSENT_NOTICE
    assert hook["pin"] is True

    endpoint = config["realtime_endpoints"][0]
    assert endpoint["type"] == "webhook"
    assert endpoint["url"] == "https://recall-api.example.test/webhooks/recall"
    assert set(endpoint["events"]) == {
        "participant_events.chat_message",
        "transcript.data",
    }


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

    assert f"recall http {code}" in str(error.value)


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
    # Google Meet takes the recipient `everyone` only.
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
