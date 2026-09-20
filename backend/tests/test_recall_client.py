"""Tests of the create-bot call, the chat send, the leave and the audio send."""

import base64
import json

import httpx
import pytest

from app.config import settings
from app.recall import client as recall_client
from app.modes.base import CONSENT_NOTICE
from app.recall.client import RecallError
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

    # No `chat.on_bot_join`. The backend sends the notice, so the order is
    # exact: the notice, then the first question. See session log 09.
    assert "chat" not in body

    # A chat bot says nothing, so it needs no audio configuration.
    assert "automatic_audio_output" not in body

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


def test_a_voice_body_carries_the_automatic_audio_output() -> None:
    """The output audio endpoint gives HTTP 400 without this configuration."""
    body = recall_client.build_request_body(
        "https://meet.google.com/abc-defg-hij", "s1", "voice"
    )

    data = body["automatic_audio_output"]["in_call_recording"]["data"]
    assert data["kind"] == "mp3"
    assert data["b64_data"] == recall_client.SILENT_MP3_B64
    # The bot must say nothing by itself. It speaks from the endpoint only.
    assert "replay_on_participant_join" not in body["automatic_audio_output"]["in_call_recording"]


def test_the_silent_mp3_is_an_mp3() -> None:
    """A value that is not valid base64, or not an mp3, gives a bot that fails."""
    audio = base64.b64decode(recall_client.SILENT_MP3_B64, validate=True)

    # An MPEG audio frame starts with 11 bits that are set.
    assert audio[0] == 0xFF
    assert audio[1] & 0xE0 == 0xE0


def test_a_voice_body_keeps_the_rest_of_the_chat_body() -> None:
    chat_body = recall_client.build_request_body(
        "https://meet.google.com/abc-defg-hij", "s1", "chat"
    )
    voice_body = recall_client.build_request_body(
        "https://meet.google.com/abc-defg-hij", "s1", "voice"
    )

    assert voice_body["recording_config"] == chat_body["recording_config"]
    assert set(voice_body) - set(chat_body) == {"automatic_audio_output"}


def test_create_bot_gives_the_mode_to_the_body(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.read())
        return httpx.Response(201, json={"id": "bot-123"})

    monkeypatch.setattr(httpx, "Client", _transport(handler))
    recall_client.create_bot("https://meet.google.com/abc-defg-hij", "s1", "voice")

    assert "automatic_audio_output" in seen["body"]


def test_send_output_audio_posts_to_the_bot(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["method"] = request.method
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.read())
        return httpx.Response(200, json={})

    monkeypatch.setattr(httpx, "Client", _transport(handler))
    recall_client.send_output_audio(BOT_ID, b"fake mp3 bytes")

    assert seen["url"] == f"https://us-west-2.recall.ai/api/v1/bot/{BOT_ID}/output_audio/"
    assert seen["method"] == "POST"
    assert seen["auth"] == "Token test-recall-api-key"
    assert seen["body"] == {
        "kind": "mp3",
        "b64_data": base64.b64encode(b"fake mp3 bytes").decode("ascii"),
    }


def test_the_audio_goes_out_as_base64(monkeypatch: pytest.MonkeyPatch) -> None:
    """The bytes of an mp3 are not text. The body is JSON, so they go as base64."""
    audio = bytes(range(256))
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.read())
        return httpx.Response(200, json={})

    monkeypatch.setattr(httpx, "Client", _transport(handler))
    recall_client.send_output_audio(BOT_ID, audio)

    assert base64.b64decode(seen["body"]["b64_data"]) == audio


def test_send_output_audio_with_no_api_key_raises_before_a_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "RECALL_API_KEY", "")

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("the client sent a request with no API key")

    monkeypatch.setattr(httpx, "Client", _transport(handler))
    with pytest.raises(RecallError, match="no Recall API key"):
        recall_client.send_output_audio(BOT_ID, b"fake mp3 bytes")


@pytest.mark.parametrize("code", [400, 404, 500])
def test_a_failed_audio_send_raises_recall_error(
    monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(code, text="the bot has no automatic_audio_output")

    monkeypatch.setattr(httpx, "Client", _transport(handler))
    with pytest.raises(RecallError) as error:
        recall_client.send_output_audio(BOT_ID, b"fake mp3 bytes")

    assert f"recall http {code}" in str(error.value)


def test_a_failed_audio_send_has_no_api_key_in_the_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="Invalid token: test-recall-api-key is wrong")

    monkeypatch.setattr(httpx, "Client", _transport(handler))
    with pytest.raises(RecallError) as error:
        recall_client.send_output_audio(BOT_ID, b"fake mp3 bytes")

    assert settings.RECALL_API_KEY not in str(error.value)


def test_a_network_error_on_the_audio_send_raises_recall_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr(httpx, "Client", _transport(handler))
    with pytest.raises(RecallError, match="recall request failed"):
        recall_client.send_output_audio(BOT_ID, b"fake mp3 bytes")
