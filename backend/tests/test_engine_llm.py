"""Tests of the OpenAI call.

These tests use the real `openai` SDK against a fake transport, so the true code
path runs. No request leaves the machine.
"""

import json

import httpx2
import openai
import pytest

from app.config import settings
from app.engine.llm import LLMError, ask_model, to_messages

# The real class. The tests patch the name `openai.OpenAI`, so a helper that
# reads the name at call time would call itself.
REAL_OPENAI = openai.OpenAI

SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}


def _transport(handler):
    """Give a fake `openai.OpenAI` that answers with the handler."""

    def make_client(**kwargs):
        kwargs["http_client"] = httpx2.Client(transport=httpx2.MockTransport(handler))
        # No retry. A test of a failure must not wait for the SDK to try again.
        kwargs["max_retries"] = 0
        return REAL_OPENAI(**kwargs)

    return make_client


def _completion(content: str, refusal: str | None = None) -> dict:
    """Give the body of one chat completion answer."""
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1,
        "model": settings.OPENAI_MODEL,
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": content,
                    "refusal": refusal,
                },
            }
        ],
    }


def test_to_messages_maps_the_two_roles() -> None:
    log = [
        {"role": "bot", "text": "What brings you in?"},
        {"role": "patient", "text": "A headache."},
    ]

    assert to_messages(log) == [
        {"role": "assistant", "content": "What brings you in?"},
        {"role": "user", "content": "A headache."},
    ]


def test_ask_model_gives_the_parsed_object(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx2.Response(200, json=_completion('{"answer": "yes"}'))

    monkeypatch.setattr(openai, "OpenAI", _transport(handler))
    result = ask_model("be short", [{"role": "user", "content": "hi"}], SCHEMA, "probe")

    assert result == {"answer": "yes"}
    assert str(seen["url"]).endswith("/chat/completions")

    body = seen["body"]
    assert body["model"] == settings.OPENAI_MODEL
    assert body["messages"] == [
        {"role": "system", "content": "be short"},
        {"role": "user", "content": "hi"},
    ]
    assert body["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "probe", "schema": SCHEMA, "strict": True},
    }


def test_ask_model_needs_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")

    def handler(request: httpx2.Request) -> httpx2.Response:
        raise AssertionError("the call must not go out with no key")

    monkeypatch.setattr(openai, "OpenAI", _transport(handler))

    with pytest.raises(LLMError, match="no OpenAI API key"):
        ask_model("s", [], SCHEMA, "probe")


def test_an_http_failure_gives_an_llm_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(500, json={"error": {"message": "server is down"}})

    monkeypatch.setattr(openai, "OpenAI", _transport(handler))

    with pytest.raises(LLMError, match="openai request failed"):
        ask_model("s", [], SCHEMA, "probe")


def test_a_network_failure_gives_an_llm_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("no route to host")

    monkeypatch.setattr(openai, "OpenAI", _transport(handler))

    with pytest.raises(LLMError, match="openai request failed"):
        ask_model("s", [], SCHEMA, "probe")


def test_an_error_does_not_show_the_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        # The worst case: the API writes the key back in its error text.
        return httpx2.Response(
            400, json={"error": {"message": f"bad key {settings.OPENAI_API_KEY}"}}
        )

    monkeypatch.setattr(openai, "OpenAI", _transport(handler))

    with pytest.raises(LLMError) as error:
        ask_model("s", [], SCHEMA, "probe")

    assert settings.OPENAI_API_KEY not in str(error.value)
    assert "***" in str(error.value)


def test_an_answer_that_is_not_json_gives_an_llm_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=_completion("I cannot do that."))

    monkeypatch.setattr(openai, "OpenAI", _transport(handler))

    with pytest.raises(LLMError, match="not JSON"):
        ask_model("s", [], SCHEMA, "probe")


def test_json_that_is_not_an_object_gives_an_llm_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=_completion("[1, 2, 3]"))

    monkeypatch.setattr(openai, "OpenAI", _transport(handler))

    with pytest.raises(LLMError, match="not an object"):
        ask_model("s", [], SCHEMA, "probe")


def test_an_empty_answer_gives_an_llm_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=_completion(""))

    monkeypatch.setattr(openai, "OpenAI", _transport(handler))

    with pytest.raises(LLMError, match="empty answer"):
        ask_model("s", [], SCHEMA, "probe")


def test_no_choice_gives_an_llm_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        body = _completion("{}")
        body["choices"] = []
        return httpx2.Response(200, json=body)

    monkeypatch.setattr(openai, "OpenAI", _transport(handler))

    with pytest.raises(LLMError, match="no answer"):
        ask_model("s", [], SCHEMA, "probe")


def test_a_refusal_gives_an_llm_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=_completion("", refusal="I cannot help."))

    monkeypatch.setattr(openai, "OpenAI", _transport(handler))

    with pytest.raises(LLMError, match="openai refused"):
        ask_model("s", [], SCHEMA, "probe")
