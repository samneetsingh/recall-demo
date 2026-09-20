"""The OpenAI call of the engine."""

from __future__ import annotations

import json
import logging
from typing import Any

import openai

from app.config import settings

logger = logging.getLogger(__name__)

# The role of a log entry, in the names of the OpenAI API.
_ROLES = {"bot": "assistant", "patient": "user"}


class LLMError(Exception):
    """An LLM call failed. The message goes in the `error_reason` column."""


def _redact(text: str) -> str:
    """Take the API key out of text that goes in an error message or a log.

    The `error_reason` column is shown to the user, so the key must never reach
    it.
    """
    key = settings.OPENAI_API_KEY
    return text.replace(key, "***") if key else text


def to_messages(log: list[dict[str, str]]) -> list[dict[str, str]]:
    """Change the conversation log into the messages of the API."""
    return [
        {"role": _ROLES[turn["role"]], "content": turn["text"]} for turn in log
    ]


def ask_model(
    system: str,
    messages: list[dict[str, str]],
    schema: dict[str, Any],
    schema_name: str,
) -> dict[str, Any]:
    """Call the model and give the parsed JSON object."""
    if not settings.OPENAI_API_KEY:
        raise LLMError("no OpenAI API key")

    try:
        # The client is made per call, as in `app/recall/client.py`
        client = openai.OpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=settings.OPENAI_TIMEOUT_SECONDS,
        )
        response = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[{"role": "system", "content": system}, *messages],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "schema": schema,
                    "strict": True,
                },
            },
        )
    except openai.OpenAIError as error:
        raise LLMError(f"openai request failed: {_redact(str(error))[:200]}") from error

    if not response.choices:
        raise LLMError("openai gave no answer")

    message = response.choices[0].message
    if message.refusal:
        raise LLMError(f"openai refused: {_redact(message.refusal)[:200]}")
    if not message.content:
        raise LLMError("openai gave an empty answer")

    try:
        answer = json.loads(message.content)
    except ValueError as error:
        raise LLMError("openai gave an answer that is not JSON") from error

    if not isinstance(answer, dict):
        raise LLMError("openai gave JSON that is not an object")

    logger.info("model %s answered for %s", settings.OPENAI_MODEL, schema_name)
    return answer
