"""The OpenAI text-to-speech call."""

from __future__ import annotations

import logging

import openai

from app.config import settings

logger = logging.getLogger(__name__)


class TTSError(Exception):
    """A TTS call failed. `app/modes/voice.py` makes it a `ModeError`."""


def _redact(text: str) -> str:
    """Take the API key out of text that goes in an error message or a log."""
    key = settings.OPENAI_API_KEY
    return text.replace(key, "***") if key else text


def speak(text: str) -> bytes:
    """Make the mp3 of one text. Give the bytes."""
    words = text.strip()
    if not words:
        raise TTSError("the text is empty, no audio was made")
    if not settings.OPENAI_API_KEY:
        raise TTSError("no OpenAI API key")

    # `instructions` is for `gpt-4o-mini-tts`. `tts-1` and `tts-1-hd` refuse it.
    extra = (
        {"instructions": settings.OPENAI_TTS_INSTRUCTIONS}
        if settings.OPENAI_TTS_INSTRUCTIONS
        else {}
    )

    try:
        # The client is made per call, as in `app/engine/llm.py`.
        client = openai.OpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=settings.OPENAI_TIMEOUT_SECONDS,
        )
        response = client.audio.speech.create(
            model=settings.OPENAI_TTS_MODEL,
            voice=settings.OPENAI_TTS_VOICE,
            input=words,
            response_format="mp3",
            **extra,
        )
        audio = response.content
    except openai.OpenAIError as error:
        raise TTSError(f"openai tts failed: {_redact(str(error))[:200]}") from error

    if not audio:
        # Silence in the meeting looks like a hang to the patient.
        raise TTSError("openai tts gave no audio")

    logger.info(
        "tts %s made %s bytes for %s characters",
        settings.OPENAI_TTS_MODEL,
        len(audio),
        len(words),
    )
    return bytes(audio)
