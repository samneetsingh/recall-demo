"""Tests of the OpenAI text-to-speech call.

These tests use the real `openai` SDK against a fake transport, so the true
code path runs. No request leaves the machine.
"""

import json

import httpx2
import openai
import pytest

from app.config import settings
from app.tts.openai_tts import TTSError, speak

# The real class. The tests patch the name `openai.OpenAI`, so a helper that
# reads the name at call time would call itself.
REAL_OPENAI = openai.OpenAI

MP3 = b"ID3\x04\x00fake mp3 bytes"


def _transport(handler):
    """Give a fake `openai.OpenAI` that answers with the handler."""

    def make_client(**kwargs):
        kwargs["http_client"] = httpx2.Client(transport=httpx2.MockTransport(handler))
        # No retry. A test of a failure must not wait for the SDK to try again.
        kwargs["max_retries"] = 0
        return REAL_OPENAI(**kwargs)

    return make_client


def _audio(body: bytes = MP3):
    """Give a handler that answers with mp3 bytes, and keeps the request."""
    seen: dict[str, object] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.read())
        return httpx2.Response(
            200, content=body, headers={"content-type": "audio/mpeg"}
        )

    return handler, seen


def test_speak_gives_the_mp3_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    handler, seen = _audio()
    monkeypatch.setattr(openai, "OpenAI", _transport(handler))

    assert speak("Where is the pain?") == MP3
    assert seen["url"] == "https://api.openai.com/v1/audio/speech"


def test_the_request_has_the_model_the_voice_and_the_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Recall's output audio endpoint takes mp3 only."""
    handler, seen = _audio()
    monkeypatch.setattr(openai, "OpenAI", _transport(handler))

    speak("Where is the pain?")

    body = seen["body"]
    assert body["model"] == settings.OPENAI_TTS_MODEL
    assert body["voice"] == settings.OPENAI_TTS_VOICE
    assert body["response_format"] == "mp3"
    assert body["input"] == "Where is the pain?"


def test_the_instructions_go_in_the_request(monkeypatch: pytest.MonkeyPatch) -> None:
    handler, seen = _audio()
    monkeypatch.setattr(openai, "OpenAI", _transport(handler))

    speak("Where is the pain?")

    assert seen["body"]["instructions"] == settings.OPENAI_TTS_INSTRUCTIONS


def test_an_empty_instruction_is_not_in_the_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`tts-1` and `tts-1-hd` refuse the parameter, so an empty text drops it."""
    monkeypatch.setattr(settings, "OPENAI_TTS_INSTRUCTIONS", "")
    handler, seen = _audio()
    monkeypatch.setattr(openai, "OpenAI", _transport(handler))

    speak("Where is the pain?")

    assert "instructions" not in seen["body"]


def test_the_text_is_trimmed(monkeypatch: pytest.MonkeyPatch) -> None:
    handler, seen = _audio()
    monkeypatch.setattr(openai, "OpenAI", _transport(handler))

    speak("  Where is the pain?\n")

    assert seen["body"]["input"] == "Where is the pain?"


@pytest.mark.parametrize("text", ["", "   ", "\n\t"])
def test_an_empty_text_raises_before_a_request(
    monkeypatch: pytest.MonkeyPatch, text: str
) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise AssertionError("the client sent a request for an empty text")

    monkeypatch.setattr(openai, "OpenAI", _transport(handler))
    with pytest.raises(TTSError, match="the text is empty"):
        speak(text)


def test_no_api_key_raises_before_a_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")

    def handler(request: httpx2.Request) -> httpx2.Response:
        raise AssertionError("the client sent a request with no API key")

    monkeypatch.setattr(openai, "OpenAI", _transport(handler))
    with pytest.raises(TTSError, match="no OpenAI API key"):
        speak("Where is the pain?")


@pytest.mark.parametrize("code", [400, 401, 429, 500])
def test_an_http_error_raises_tts_error(
    monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(code, json={"error": {"message": "no"}})

    monkeypatch.setattr(openai, "OpenAI", _transport(handler))
    with pytest.raises(TTSError, match="openai tts failed"):
        speak("Where is the pain?")


def test_a_network_error_raises_tts_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("no route to host")

    monkeypatch.setattr(openai, "OpenAI", _transport(handler))
    with pytest.raises(TTSError, match="openai tts failed"):
        speak("Where is the pain?")


def test_the_reason_has_no_api_key_in_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """`error_reason` is shown to the user, so the key must never reach it."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            401,
            json={"error": {"message": f"Invalid key {settings.OPENAI_API_KEY}"}},
        )

    monkeypatch.setattr(openai, "OpenAI", _transport(handler))
    with pytest.raises(TTSError) as error:
        speak("Where is the pain?")

    assert settings.OPENAI_API_KEY not in str(error.value)


def test_an_empty_answer_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Silence in the meeting looks like a hang to the patient."""
    handler, _ = _audio(body=b"")
    monkeypatch.setattr(openai, "OpenAI", _transport(handler))

    with pytest.raises(TTSError, match="gave no audio"):
        speak("Where is the pain?")
